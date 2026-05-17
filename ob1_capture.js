// ============================================================
// ob1_capture.js — OB1 Memory System
// JSG Labs / Geldrich Corp
//
// Standalone Chrome micro-extension content script.
// Runs on claude.ai only.
//
// What it does:
//   - Watches the claude.ai DOM via MutationObserver
//   - Detects per-turn completion via data-is-streaming attribute
//   - Captures user turns on submission (data-user-message-bubble)
//   - POSTs each completed turn to OB1 server at 192.168.1.41:5150/turn
//   - Fires /flush when ATR-style context warning threshold is crossed
//   - Silent — no UI, no widget, no interference with claude.ai
//
// DOM signals confirmed by Claude in Chrome DevTools recon 2026-05-17:
//   Assistant turn complete : div[data-is-streaming] flips to "false"
//   Assistant turn body     : div[class*="font-claude-response"]
//   User turn present       : div[data-testid="user-message"]
//   Turn role discriminator : h2.sr-only text prefix
//                             "Claude responded:" = assistant
//                             "You said:"        = user
//
// Server:
//   Home:      http://192.168.1.41:5150
//   Tailscale: http://100.105.169.111:5150
//   Endpoint:  POST /turn  { role, text, model, session_id, timestamp }
//   Flush:     POST /flush { reason }
//   Status:    GET  /status
// ============================================================

// ---------------------------------------------------------------------------
// CONFIG
// ---------------------------------------------------------------------------

const OB1_HOME      = 'http://192.168.1.41:5150';
const OB1_TAILSCALE = 'http://100.105.169.111:5150';
const OB1_FLUSH_PCT = 0.40;   // fire /flush when context load hits 40%

// How long to wait after data-is-streaming flips before capturing
// (gives React time to finish rendering the full response body)
const CAPTURE_DELAY_MS = 800;

// ---------------------------------------------------------------------------
// STATE
// ---------------------------------------------------------------------------

let ob1BaseUrl      = OB1_HOME;       // will switch to Tailscale if home fails
let sessionId       = _generateSessionId();
let capturedTurnIds = new Set();      // prevent duplicate captures
let flushFired      = false;          // only fire /flush once per session
let serverReachable = false;          // confirmed on first successful POST

// ---------------------------------------------------------------------------
// UTILITIES
// ---------------------------------------------------------------------------

function _generateSessionId() {
  const now = new Date();
  return `claude_${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${Date.now()}`;
}

function _timestamp() {
  return new Date().toISOString().replace('T', ' ').substring(0, 19);
}

function _log(msg) {
  console.log(`[OB1] ${msg}`);
}

function _warn(msg) {
  console.warn(`[OB1] ${msg}`);
}

// ---------------------------------------------------------------------------
// SERVER COMMUNICATION
// ---------------------------------------------------------------------------

async function _post(endpoint, payload) {
  // Try home IP first, fall back to Tailscale on failure
  const urls = [OB1_HOME, OB1_TAILSCALE];

  for (const base of urls) {
    try {
      const res = await fetch(`${base}${endpoint}`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
        signal:  AbortSignal.timeout(3000),  // 3 second timeout
      });

      if (res.ok) {
        if (base !== ob1BaseUrl) {
          ob1BaseUrl = base;
          _log(`Server reached at ${base}`);
        }
        serverReachable = true;
        return await res.json();
      }
    } catch (err) {
      // Try next URL
    }
  }

  _warn('OB1 server unreachable on home and Tailscale. Turn buffered locally.');
  return null;
}

async function _checkServerStatus() {
  try {
    const res = await fetch(`${OB1_HOME}/status`, {
      signal: AbortSignal.timeout(2000)
    });
    if (res.ok) {
      serverReachable = true;
      _log(`Server online. Session: ${sessionId}`);
      return true;
    }
  } catch (_) {}

  // Try Tailscale
  try {
    const res = await fetch(`${OB1_TAILSCALE}/status`, {
      signal: AbortSignal.timeout(2000)
    });
    if (res.ok) {
      ob1BaseUrl = OB1_TAILSCALE;
      serverReachable = true;
      _log(`Server online via Tailscale. Session: ${sessionId}`);
      return true;
    }
  } catch (_) {}

  _warn('OB1 server not reachable at startup. Will retry on each turn.');
  return false;
}

// ---------------------------------------------------------------------------
// TURN CAPTURE
// ---------------------------------------------------------------------------

function _extractAssistantText(streamingEl) {
  const bodyEl = streamingEl.querySelector('div[class*="font-claude-response"]');
  return bodyEl ? (bodyEl.innerText || '').trim() : '';
}

function _extractUserText() {
  // Get all user messages, return the last one (most recent submission)
  const userEls = document.querySelectorAll('[data-testid="user-message"]');
  if (!userEls.length) return '';
  const last = userEls[userEls.length - 1];
  return (last.innerText || '').trim();
}

function _getTurnId(el) {
  // Build a stable ID from element position + text length
  // Avoids capturing the same turn twice from multiple mutations
  const allStreaming = [...document.querySelectorAll('div[data-is-streaming]')];
  const idx = allStreaming.indexOf(el);
  const textLen = (el.innerText || '').length;
  return `turn_${idx}_${textLen}`;
}

async function captureAssistantTurn(streamingEl) {
  // Debounce — wait for render to settle
  await new Promise(r => setTimeout(r, CAPTURE_DELAY_MS));

  // Verify it's still completed (not mid-stream due to retry)
  if (streamingEl.getAttribute('data-is-streaming') !== 'false') return;

  const turnId = _getTurnId(streamingEl);
  if (capturedTurnIds.has(turnId)) return;
  capturedTurnIds.add(turnId);

  const text = _extractAssistantText(streamingEl);
  if (!text || text.length < 5) return;

  const turn = {
    role:       'assistant',
    text:       text,
    model:      'claude',
    session_id: sessionId,
    timestamp:  _timestamp(),
  };

  _log(`Assistant turn captured (${text.length} chars). Sending to OB1...`);
  const result = await _post('/turn', turn);
  if (result) {
    _log(`Turn accepted. Buffer: ${result.buffer_size}`);
  }
}

async function captureUserTurn() {
  // Small delay to let the DOM settle after submission
  await new Promise(r => setTimeout(r, 300));

  const text = _extractUserText();
  if (!text || text.length < 3) return;

  // Use text hash as ID to avoid duplicate captures
  const turnId = `user_${text.length}_${text.substring(0, 20)}`;
  if (capturedTurnIds.has(turnId)) return;
  capturedTurnIds.add(turnId);

  const turn = {
    role:       'user',
    text:       text,
    model:      'claude',
    session_id: sessionId,
    timestamp:  _timestamp(),
  };

  _log(`User turn captured (${text.length} chars). Sending to OB1...`);
  const result = await _post('/turn', turn);
  if (result) {
    _log(`Turn accepted. Buffer: ${result.buffer_size}`);
  }
}

// ---------------------------------------------------------------------------
// CONTEXT LOAD MONITORING
// ---------------------------------------------------------------------------

function _estimateContextLoad() {
  // Mirror ATR's scoring logic from content.js
  // Lightweight version — word count + code block detection
  let score = 0;
  const maxScore = 400; // Claude's ATR max

  const userEls = document.querySelectorAll('[data-testid="user-message"]');
  const assistantEls = document.querySelectorAll('div[data-is-streaming="false"]');
  const allEls = [...userEls, ...assistantEls];

  allEls.forEach(el => {
    const text = el.innerText || '';
    const wc = text.split(/\s+/).filter(w => w.length > 0).length;
    if (wc > 500) score += 2; else if (wc > 0) score += 1;
    score += el.querySelectorAll('pre, code').length * 3;
  });

  return Math.min(score / maxScore, 1.0);
}

async function _checkContextLoad() {
  if (flushFired) return;

  const load = _estimateContextLoad();
  if (load >= OB1_FLUSH_PCT) {
    flushFired = true;
    _log(`Context load at ${Math.round(load * 100)}%. Firing OB1 flush.`);
    await _post('/flush', {
      reason:       `context_load_${Math.round(load * 100)}pct`,
      session_id:   sessionId,
      context_load: load,
    });
  }
}

// ---------------------------------------------------------------------------
// MUTATION OBSERVER
// Based on Claude in Chrome DevTools recon — 2026-05-17
// Signal: data-is-streaming attribute flip "true" → "false"
// ---------------------------------------------------------------------------

function _initObserver() {
  const observer = new MutationObserver((mutations) => {
    for (const m of mutations) {

      // --- ASSISTANT TURN COMPLETE ---
      // data-is-streaming flips to "false" = response finished rendering
      if (
        m.type === 'attributes' &&
        m.attributeName === 'data-is-streaming' &&
        m.target.getAttribute('data-is-streaming') === 'false'
      ) {
        captureAssistantTurn(m.target);
        _checkContextLoad();
      }

      // --- USER TURN SUBMITTED ---
      // New node added to feed containing data-user-message-bubble
      if (m.type === 'childList') {
        for (const node of m.addedNodes) {
          if (node.nodeType !== 1) continue;

          // Check if new node is or contains a user message bubble
          const userBubble = node.matches?.('[data-user-message-bubble="true"]')
            ? node
            : node.querySelector?.('[data-user-message-bubble="true"]');

          if (userBubble) {
            captureUserTurn();
          }

          // Check if new node contains a streaming assistant turn starting
          const streamingEl = node.matches?.('[data-is-streaming]')
            ? node
            : node.querySelector?.('[data-is-streaming]');

          if (streamingEl && streamingEl.getAttribute('data-is-streaming') === 'true') {
            _log('New assistant turn streaming...');
          }
        }
      }
    }
  });

  // Observe document.body with subtree for full coverage
  // Narrowing to div[data-autoscroll-container="true"] is faster
  // but risks missing turns if Claude updates that selector
  observer.observe(document.body, {
    attributes:      true,
    attributeFilter: ['data-is-streaming'],
    subtree:         true,
    childList:       true,
  });

  _log('MutationObserver active. Watching for turns...');
  return observer;
}

// ---------------------------------------------------------------------------
// CAPTURE EXISTING TURNS ON LOAD
// If extension loads mid-conversation, capture what's already there
// ---------------------------------------------------------------------------

async function _captureExistingTurns() {
  const completedTurns = document.querySelectorAll('div[data-is-streaming="false"]');
  if (!completedTurns.length) return;

  _log(`Found ${completedTurns.length} existing completed turns. Capturing...`);

  // Capture all at once as a batch — send to /flush after
  for (const el of completedTurns) {
    const text = _extractAssistantText(el);
    if (!text || text.length < 5) continue;

    const turnId = _getTurnId(el);
    if (capturedTurnIds.has(turnId)) continue;
    capturedTurnIds.add(turnId);

    const turn = {
      role:       'assistant',
      text:       text,
      model:      'claude',
      session_id: sessionId,
      timestamp:  _timestamp(),
    };

    await _post('/turn', turn);
  }

  // Also capture all user turns
  const userEls = document.querySelectorAll('[data-testid="user-message"]');
  for (const el of userEls) {
    const text = (el.innerText || '').trim();
    if (!text || text.length < 3) continue;

    const turnId = `user_${text.length}_${text.substring(0, 20)}`;
    if (capturedTurnIds.has(turnId)) continue;
    capturedTurnIds.add(turnId);

    const turn = {
      role:       'user',
      text:       text,
      model:      'claude',
      session_id: sessionId,
      timestamp:  _timestamp(),
    };

    await _post('/turn', turn);
  }

  _log(`Existing turns captured. Requesting digest flush.`);
  await _post('/flush', {
    reason:     'load_existing_turns',
    session_id: sessionId,
  });
}

// ---------------------------------------------------------------------------
// INIT
// ---------------------------------------------------------------------------

async function init() {
  _log(`OB1 Capture initializing... Session: ${sessionId}`);

  // Wait for DOM to be ready
  await new Promise(r => setTimeout(r, 2000));

  // Check server reachability
  await _checkServerStatus();

  // Capture any existing turns (mid-conversation load)
  if (serverReachable) {
    await _captureExistingTurns();
  }

  // Start observer
  _initObserver();

  _log('OB1 Capture active.');
}

// Only run on claude.ai conversation pages
if (window.location.hostname === 'claude.ai') {
  init();
}
