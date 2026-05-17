"""
ob1_digest.py — OB1 Memory System
JSG Labs / Geldrich Corp

The compression engine. Takes buffered chat turns from ob1_server.py
and produces a minimum viable session_digest.md.

Called by ob1_server.trigger_digest() — never run standalone in production.
Can be run directly for testing: python3 ob1_digest.py

Design:
    - Repurposed from SonglineMemory/compressor.py
    - Stripped of landmark/songline concepts — flat digest output only
    - Two-pass: noise strip → TF-IDF term frequency scoring
    - Merges with previous digest so nothing is lost between flush cycles
    - Output is human-readable Markdown — Claude, Cowork, Claude Code all read it

Output format:
    # OB1 Session Digest
    _Last updated: 2026-05-17 02:14:00 | Sessions tracked: 3 | Total turns: 47_

    ## High Signal Topics
    - **OB1 memory system** — local server, 851Office-1, port 5150, digest pipeline
    - **ATR Chrome extension** — auto-capture turns, flush on context warning

    ## Recent Activity
    _Last 10 turns compressed summary_

    ## Term Frequency Index
    | Term | Score | First Seen |
    ...

Zero external dependencies. Pure Python stdlib + re + string + math.
"""

import json
import math
import os
import re
import string
from collections import defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

TOP_TOPICS        = 15     # max high-signal topics in digest
TOP_TERMS         = 30     # max terms in frequency index
MIN_TERM_LENGTH   = 3      # ignore terms shorter than this
RECENT_TURNS_SHOW = 10     # how many recent turns to summarize in Recent Activity
MIN_SCORE         = 0.05   # minimum TF-IDF score to include a term

# ---------------------------------------------------------------------------
# STOP WORDS — dictation-aware, matches compressor.py baseline + extras
# ---------------------------------------------------------------------------

STOP_WORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'can', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'it', 'its', 'this', 'that', 'these',
    'those', 'i', 'we', 'you', 'he', 'she', 'they', 'my', 'our', 'your',
    'their', 'and', 'or', 'but', 'so', 'if', 'as', 'not', 'no', 'nor',
    'about', 'up', 'out', 'what', 'which', 'who', 'when', 'where', 'there',
    'here', 'just', 'also', 'then', 'than', 'into', 'go', 'get', 'got',
    'use', 'used', 'using', 'make', 'made', 'want', 'need', 'like', 'know',
    'think', 'going', 'going', 'lets', 'let', 'yes', 'okay', 'ok', 'yeah',
    'right', 'well', 'really', 'very', 'much', 'more', 'now', 'one', 'two',
    'way', 'say', 'said', 'see', 'look', 'thing', 'things', 'something',
    'anything', 'everything', 'nothing', 'um', 'uh', 'actually', 'basically',
}

# Noise patterns — verbal restarts, dictation artifacts
NOISE_PATTERNS = [
    r"\bum+\b", r"\buh+\b", r"\byou know\b", r"\bi mean\b",
    r"\bkind of\b", r"\bsort of\b", r"\bbasically\b", r"\bliterally\b",
    r"\bokay so\b", r"\bokay\b(?=\s)", r"\balright\b",
    r"\bi guess\b", r"\bi think\b", r"\byeah\b", r"\byep\b",
]

SENT_END = re.compile(r'(?<=[.!?])\s+')


# ---------------------------------------------------------------------------
# TEXT UTILITIES
# ---------------------------------------------------------------------------

def _strip_noise(text: str) -> str:
    """Remove dictation filler and verbal restarts."""
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'^[,\s]+', '', text)
    text = re.sub(r'[,\s]+$', '', text)
    return text.strip()


def _tokenize(text: str) -> list:
    """Lowercase, strip punctuation, remove stop words, enforce min length."""
    return [
        w for w in
        text.lower().translate(
            str.maketrans('', '', string.punctuation)
        ).split()
        if w not in STOP_WORDS and len(w) >= MIN_TERM_LENGTH
    ]


def _term_freq(tokens: list) -> dict:
    """Term frequency normalized by document length."""
    if not tokens:
        return {}
    counts = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens)
    return {t: c / total for t, c in counts.items()}


def _compute_idf(corpus: list) -> dict:
    """Smoothed IDF across all turns in the buffer."""
    N = len(corpus)
    df = {}
    for doc_tokens in corpus:
        for term in set(doc_tokens):
            df[term] = df.get(term, 0) + 1
    return {
        term: math.log((1 + N) / (1 + count)) + 1
        for term, count in df.items()
    }


# ---------------------------------------------------------------------------
# TOPIC EXTRACTION
# ---------------------------------------------------------------------------

def _extract_topics(turns: list) -> list:
    """
    Scores all terms across all turns using TF-IDF.
    Returns top terms as (term, score, first_seen_timestamp) tuples.
    Groups bigrams where two high-scoring adjacent terms appear together often.
    """
    if not turns:
        return []

    # Tokenize each turn
    tokenized = []
    for turn in turns:
        clean = _strip_noise(turn.get('text', ''))
        tokens = _tokenize(clean)
        tokenized.append(tokens)

    idf = _compute_idf(tokenized)

    # Aggregate TF-IDF scores across all turns, track first seen
    term_scores    = defaultdict(float)
    term_first     = {}
    bigram_counts  = defaultdict(int)

    for i, (turn, tokens) in enumerate(zip(turns, tokenized)):
        tf       = _term_freq(tokens)
        ts       = turn.get('timestamp', '')

        for term, tf_val in tf.items():
            score = tf_val * idf.get(term, 0.0)
            term_scores[term] += score
            if term not in term_first:
                term_first[term] = ts

        # Count bigrams
        for j in range(len(tokens) - 1):
            bigram = f"{tokens[j]} {tokens[j+1]}"
            bigram_counts[bigram] += 1

    # Boost terms that appear in high-frequency bigrams
    for bigram, count in bigram_counts.items():
        if count >= 3:  # bigram appeared 3+ times — meaningful phrase
            parts = bigram.split()
            for part in parts:
                if part in term_scores:
                    term_scores[part] *= 1.2  # mild boost

    # Filter and sort
    scored = [
        (term, round(score, 4), term_first.get(term, ''))
        for term, score in term_scores.items()
        if score >= MIN_SCORE
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    return scored[:TOP_TERMS]


# ---------------------------------------------------------------------------
# TOPIC CLUSTERING — group related terms into readable topic lines
# ---------------------------------------------------------------------------

def _cluster_topics(scored_terms: list, turns: list) -> list:
    """
    Groups top-scoring terms into human-readable topic phrases.
    Strategy: find sentences in turns that contain 2+ top terms,
    use those as topic labels. Falls back to term pairs if no sentence found.

    Returns list of topic strings for the High Signal Topics section.
    """
    if not scored_terms:
        return []

    top_term_set = {t[0] for t in scored_terms[:20]}
    topics       = []
    used_terms   = set()

    # Pass 1 — find sentences that contain clusters of top terms
    for turn in turns:
        clean     = _strip_noise(turn.get('text', ''))
        sentences = SENT_END.split(clean)

        for sent in sentences:
            sent_tokens  = set(_tokenize(sent))
            overlap      = sent_tokens & top_term_set - used_terms
            if len(overlap) >= 2:
                # Build a topic label from the sentence
                label_terms  = sorted(overlap, key=lambda t: next(
                    (s[1] for s in scored_terms if s[0] == t), 0
                ), reverse=True)[:4]
                label        = ' — '.join(label_terms)
                # Use the cleaned sentence as the detail
                detail       = sent.strip()
                if len(detail) > 120:
                    detail = detail[:117] + '...'
                topics.append(f"**{label}** — {detail}")
                used_terms.update(overlap)

            if len(topics) >= TOP_TOPICS:
                break
        if len(topics) >= TOP_TOPICS:
            break

    # Pass 2 — any top terms not yet covered, add as bare entries
    for term, score, first_seen in scored_terms:
        if len(topics) >= TOP_TOPICS:
            break
        if term not in used_terms:
            topics.append(f"**{term}** (score: {score})")
            used_terms.add(term)

    return topics


# ---------------------------------------------------------------------------
# RECENT ACTIVITY SUMMARY
# ---------------------------------------------------------------------------

def _summarize_recent(turns: list) -> list:
    """
    Takes the last RECENT_TURNS_SHOW turns and produces a compressed
    one-liner per turn for the Recent Activity section.
    User turns get compressed. Assistant turns get first sentence only.
    """
    recent  = turns[-RECENT_TURNS_SHOW:]
    summary = []

    for turn in recent:
        role  = turn.get('role', 'unknown')
        text  = _strip_noise(turn.get('text', ''))
        ts    = turn.get('timestamp', '')[:16]  # YYYY-MM-DD HH:MM

        if not text:
            continue

        # Take first sentence only
        sentences = SENT_END.split(text)
        first     = sentences[0].strip() if sentences else text.strip()
        if len(first) > 100:
            first = first[:97] + '...'

        role_label = '**You**' if role == 'user' else '**Claude**'
        summary.append(f"- `{ts}` {role_label}: {first}")

    return summary


# ---------------------------------------------------------------------------
# PREVIOUS DIGEST MERGER
# ---------------------------------------------------------------------------

def _load_previous_term_index(previous_digest_path: str) -> dict:
    """
    Reads the Term Frequency Index from a previous digest if it exists.
    Returns dict of term → score for merging with new scores.
    Scores from previous digest are weighted at 0.6 (decay) so fresh
    terms from the current buffer can rise above stale ones.
    """
    if not previous_digest_path or not os.path.exists(previous_digest_path):
        return {}

    try:
        with open(previous_digest_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return {}

    # Parse the term index table
    # Format: | term | score | first_seen |
    previous_terms = {}
    in_table = False
    for line in content.splitlines():
        if '| Term |' in line:
            in_table = True
            continue
        if in_table and line.startswith('|') and '---' not in line:
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 2:
                try:
                    term  = parts[0]
                    score = float(parts[1]) * 0.6  # decay factor
                    first = parts[2] if len(parts) > 2 else ''
                    previous_terms[term] = (score, first)
                except ValueError:
                    continue
        elif in_table and not line.startswith('|'):
            in_table = False

    return previous_terms


def _load_previous_meta(previous_digest_path: str) -> dict:
    """Extracts session count and total turn count from previous digest header."""
    meta = {'sessions': 1, 'total_turns': 0}
    if not previous_digest_path or not os.path.exists(previous_digest_path):
        return meta
    try:
        with open(previous_digest_path, 'r', encoding='utf-8') as f:
            header = f.read(500)
        sessions_match    = re.search(r'Sessions tracked:\s*(\d+)', header)
        total_turns_match = re.search(r'Total turns:\s*(\d+)', header)
        if sessions_match:
            meta['sessions']    = int(sessions_match.group(1)) + 1
        if total_turns_match:
            meta['total_turns'] = int(total_turns_match.group(1))
    except Exception:
        pass
    return meta


# ---------------------------------------------------------------------------
# DIGEST BUILDER — PUBLIC INTERFACE
# ---------------------------------------------------------------------------

def build_digest(turns: list, previous_digest_path: str = None) -> str:
    """
    Main entry point. Called by ob1_server.trigger_digest().

    turns: list of turn dicts from ob1_server buffer
        Each turn: { role, text, model, session_id, timestamp }

    previous_digest_path: path to existing session_digest.md for merging.
        Pass None on first run.

    Returns: complete Markdown string ready to write to session_digest.md
    """
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta     = _load_previous_meta(previous_digest_path)
    prev_idx = _load_previous_term_index(previous_digest_path)

    total_turns = meta['total_turns'] + len(turns)
    sessions    = meta['sessions']

    # Score current buffer
    current_terms = _extract_topics(turns)

    # Merge with previous term index (decayed)
    merged_terms = {}
    for term, score, first_seen in current_terms:
        merged_terms[term] = [score, first_seen]

    for term, (prev_score, first_seen) in prev_idx.items():
        if term in merged_terms:
            merged_terms[term][0] += prev_score  # accumulate
        else:
            merged_terms[term] = [prev_score, first_seen]

    # Re-sort merged
    sorted_merged = sorted(
        [(t, round(s, 4), f) for t, (s, f) in merged_terms.items()],
        key=lambda x: x[1],
        reverse=True
    )[:TOP_TERMS]

    # Cluster into readable topics
    topics  = _cluster_topics(
        [(t, s, f) for t, s, f in sorted_merged[:20]],
        turns
    )

    # Recent activity
    recent  = _summarize_recent(turns)

    # ---------------------------------------------------------------------------
    # BUILD MARKDOWN
    # ---------------------------------------------------------------------------

    lines = []

    # Header
    lines.append("# OB1 Session Digest")
    lines.append(
        f"_Last updated: {now} | "
        f"Sessions tracked: {sessions} | "
        f"Total turns: {total_turns}_"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # High Signal Topics
    lines.append("## High Signal Topics")
    lines.append("_Recurring concepts weighted by frequency and co-occurrence across all sessions._")
    lines.append("")
    if topics:
        for topic in topics:
            lines.append(f"- {topic}")
    else:
        lines.append("_No topics extracted yet — buffer may be empty._")
    lines.append("")

    # Recent Activity
    lines.append("## Recent Activity")
    lines.append(
        f"_Last {min(RECENT_TURNS_SHOW, len(turns))} turns "
        f"from this flush cycle ({len(turns)} total in buffer)._"
    )
    lines.append("")
    if recent:
        for line in recent:
            lines.append(line)
    else:
        lines.append("_No recent turns._")
    lines.append("")

    # Term Frequency Index
    lines.append("## Term Frequency Index")
    lines.append("_Merged across all sessions. Scores decay 40% per flush cycle._")
    lines.append("")
    lines.append("| Term | Score | First Seen |")
    lines.append("|------|-------|------------|")
    for term, score, first_seen in sorted_merged:
        fs = first_seen[:16] if first_seen else '—'
        lines.append(f"| {term} | {score} | {fs} |")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        f"_OB1 — JSG Labs / Geldrich Corp · "
        f"Built {now} · "
        f"{len(turns)} turns processed this cycle_"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# QUICK TEST — run directly to verify without ob1_server
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    TEST_TURNS = [
        {
            "role": "user",
            "text": "So we're building OB1, the memory system for Claude. It runs on 851Office-1, Ubuntu headless server, port 5150. ATR captures turns automatically.",
            "model": "claude",
            "session_id": "test_001",
            "timestamp": "2026-05-17 02:00:00",
        },
        {
            "role": "assistant",
            "text": "OB1 is the always-on memory layer. The server listens on 0.0.0.0:5150, receives turns from ATR, buffers them, and triggers digest compression at 20 turns or 30 minutes.",
            "model": "claude",
            "session_id": "test_001",
            "timestamp": "2026-05-17 02:00:30",
        },
        {
            "role": "user",
            "text": "ATR is the Chrome extension that captures chat turns. It was built for Claude, ChatGPT, and Gemini. It's going to the Chrome Web Store.",
            "model": "claude",
            "session_id": "test_001",
            "timestamp": "2026-05-17 02:01:00",
        },
        {
            "role": "assistant",
            "text": "The digest pipeline uses TF-IDF term frequency scoring repurposed from SonglineMemory compressor.py. Output is session_digest.md — flat Markdown, readable by Claude, Cowork, and Claude Code.",
            "model": "claude",
            "session_id": "test_001",
            "timestamp": "2026-05-17 02:01:30",
        },
        {
            "role": "user",
            "text": "MainShare on M drive is the cloud source of truth. 851Mobile-1 is primary dev machine. Geldrich Corp is the parent entity. JSG Labs is the brand for dev work.",
            "model": "claude",
            "session_id": "test_001",
            "timestamp": "2026-05-17 02:02:00",
        },
    ]

    print("=== OB1 DIGEST TEST ===\n")
    digest = build_digest(TEST_TURNS, previous_digest_path=None)
    print(digest)
    print(f"\n--- {len(digest)} chars generated ---")
