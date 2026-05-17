"""
ob1_server.py — OB1 Memory System
JSG Labs / Geldrich Corp

The receiver. Always-on local HTTP server on port 5150.
Accepts turn data from ATR (via ob1_capture.js), buffers them,
triggers digest compression at the right moments.

Endpoints:
    POST /turn          — receive a single chat turn from ATR
    POST /flush         — force a digest write now (ATR warning threshold trigger)
    GET  /status        — health check, returns buffer size and last digest time
    GET  /digest        — returns current session_digest.md contents

Trigger logic:
    Auto-digest fires when:
        1. Buffer hits BUFFER_FLUSH_TURNS (default 20 turns)
        2. ATR sends a /flush (context warning threshold crossed)
        3. BUFFER_FLUSH_MINUTES have passed since last digest (default 30 min)

Output:
    M:/Geldrich_Corp_Active/Systems_and_Specifications/OB1/session_digest.md
    (configurable via DIGEST_PATH below)

Zero external dependencies. Pure Python stdlib.
Development mode — run manually: python ob1_server.py
Production: wrap with NSSM as a Windows service when stable.
"""

import json
import os
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from ob1_digest import build_digest

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

PORT                 = 5150
BUFFER_FLUSH_TURNS   = 20      # auto-flush after this many turns
BUFFER_FLUSH_MINUTES = 30      # auto-flush after this many minutes of inactivity
DIGEST_PATH          = r"M:\Geldrich_Corp_Active\Systems_and_Specifications\OB1\session_digest.md"
LOG_PATH             = r"M:\Geldrich_Corp_Active\Systems_and_Specifications\OB1\ob1_server.log"

# ---------------------------------------------------------------------------
# SHARED STATE
# ---------------------------------------------------------------------------

turn_buffer      = []          # raw turns accumulate here between digests
buffer_lock      = threading.Lock()
last_digest_time = datetime.now()
last_flush_time  = datetime.now()


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    """Simple timestamped log to console and log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[OB1 {timestamp}] {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[OB1] Log write failed: {e}")


# ---------------------------------------------------------------------------
# DIGEST TRIGGER
# ---------------------------------------------------------------------------

def trigger_digest(reason: str = "manual") -> bool:
    """
    Compresses the current buffer and writes session_digest.md.
    Returns True on success, False on failure.
    Thread-safe — acquires buffer_lock.
    """
    global turn_buffer, last_digest_time

    with buffer_lock:
        if not turn_buffer:
            log(f"Digest triggered ({reason}) but buffer is empty. Skipping.")
            return False

        turns_to_digest = list(turn_buffer)
        turn_buffer = []  # clear buffer immediately

    log(f"Digest triggered ({reason}). Processing {len(turns_to_digest)} turns...")

    try:
        digest_md = build_digest(turns_to_digest, previous_digest_path=DIGEST_PATH)
        os.makedirs(os.path.dirname(DIGEST_PATH), exist_ok=True)
        with open(DIGEST_PATH, "w", encoding="utf-8") as f:
            f.write(digest_md)
        last_digest_time = datetime.now()
        log(f"Digest written to {DIGEST_PATH} ({len(digest_md)} chars)")
        return True
    except Exception as e:
        log(f"Digest FAILED: {e}")
        # Put turns back in buffer so we don't lose them
        with buffer_lock:
            turn_buffer = turns_to_digest + turn_buffer
        return False


# ---------------------------------------------------------------------------
# AUTO-FLUSH WATCHDOG
# ---------------------------------------------------------------------------

def watchdog_loop() -> None:
    """
    Background thread. Checks every 60 seconds whether a time-based
    flush is needed. Fires if BUFFER_FLUSH_MINUTES have passed since
    the last digest and there's something in the buffer.
    """
    while True:
        time.sleep(60)
        with buffer_lock:
            buffer_size = len(turn_buffer)

        if buffer_size > 0:
            minutes_since = (datetime.now() - last_digest_time).seconds / 60
            if minutes_since >= BUFFER_FLUSH_MINUTES:
                log(f"Watchdog: {minutes_since:.0f} min since last digest. Auto-flushing.")
                trigger_digest(reason=f"watchdog_{minutes_since:.0f}min")


# ---------------------------------------------------------------------------
# REQUEST HANDLER
# ---------------------------------------------------------------------------

class OB1Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        """Suppress default HTTPServer console noise."""
        pass

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")  # allow ATR extension
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        """Handle CORS preflight from Chrome extension."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):

        # --- POST /turn ---
        if self.path == "/turn":
            data = self._read_body()
            role = data.get("role", "").strip()
            text = data.get("text", "").strip()
            model = data.get("model", "claude").strip()
            session_id = data.get("session_id", "").strip()

            if not role or not text:
                self._send_json(400, {"error": "Missing role or text"})
                return

            turn = {
                "role":       role,
                "text":       text,
                "model":      model,
                "session_id": session_id,
                "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            with buffer_lock:
                turn_buffer.append(turn)
                buffer_size = len(turn_buffer)

            log(f"Turn received [{role}] ({len(text)} chars) — buffer: {buffer_size}")

            # Auto-flush if buffer hits threshold
            if buffer_size >= BUFFER_FLUSH_TURNS:
                log(f"Buffer hit {BUFFER_FLUSH_TURNS} turns. Auto-flushing.")
                threading.Thread(
                    target=trigger_digest,
                    args=(f"buffer_{buffer_size}turns",),
                    daemon=True
                ).start()

            self._send_json(200, {"status": "ok", "buffer_size": buffer_size})

        # --- POST /flush ---
        elif self.path == "/flush":
            data = self._read_body()
            reason = data.get("reason", "manual_flush")
            log(f"Flush requested: {reason}")
            threading.Thread(
                target=trigger_digest,
                args=(reason,),
                daemon=True
            ).start()
            self._send_json(200, {"status": "flush_queued", "reason": reason})

        else:
            self._send_json(404, {"error": "Unknown endpoint"})

    def do_GET(self):

        # --- GET /status ---
        if self.path == "/status":
            with buffer_lock:
                buffer_size = len(turn_buffer)
            digest_exists = os.path.exists(DIGEST_PATH)
            digest_age = None
            if digest_exists:
                mtime = os.path.getmtime(DIGEST_PATH)
                digest_age = round((time.time() - mtime) / 60, 1)  # minutes

            self._send_json(200, {
                "status":          "OB1 active",
                "port":            PORT,
                "buffer_turns":    buffer_size,
                "flush_at":        BUFFER_FLUSH_TURNS,
                "digest_exists":   digest_exists,
                "digest_age_min":  digest_age,
                "last_digest":     last_digest_time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        # --- GET /digest ---
        elif self.path == "/digest":
            if not os.path.exists(DIGEST_PATH):
                self._send_json(404, {"error": "No digest yet"})
                return
            try:
                with open(DIGEST_PATH, "r", encoding="utf-8") as f:
                    content = f.read()
                self._send_json(200, {"digest": content})
            except Exception as e:
                self._send_json(500, {"error": str(e)})

        else:
            self._send_json(404, {"error": "Unknown endpoint"})


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run():
    log(f"OB1 server starting on port {PORT}...")
    log(f"Digest output: {DIGEST_PATH}")
    log(f"Auto-flush: every {BUFFER_FLUSH_TURNS} turns or {BUFFER_FLUSH_MINUTES} min")

    # Start watchdog
    watchdog = threading.Thread(target=watchdog_loop, daemon=True)
    watchdog.start()
    log("Watchdog thread started.")

    # Start server
    server = HTTPServer(("localhost", PORT), OB1Handler)
    log(f"OB1 listening on http://localhost:{PORT}")
    log("Endpoints: POST /turn | POST /flush | GET /status | GET /digest")
    log("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("OB1 server stopped.")
        server.shutdown()


if __name__ == "__main__":
    run()
