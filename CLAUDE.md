# CLAUDE.md — Geldrich Corp Operator Root
Last updated: May 2026

## What This File Does
This is the boot file for all Claude Code sessions under Legend (Josh Geldrich).
Load all referenced files at session start before proceeding.

## Always Load
- SOUL.md — who you are in this partnership
- USER.md — how Legend operates
- PROJECTS.md — what's active, what's the gate item

## Load On Demand
- DECISIONS.md — when a decision needs logging or review
- CONSTRAINTS.md — when you're unsure if you're authorized to proceed
- HANDOFF.md — when Legend is unavailable and you're holding the fort

## OB1 Memory Layer
OB1 is Geldrich Corp's persistent memory system. It captures every Claude session
turn automatically and compresses them into a running digest. Read this at every
session start — it tells you what has been built, what decisions were made, and
what the current state of all active projects is.

- Live digest   : /mnt/OB1/session_digest.md (on 851Office-1, always-on Ubuntu server)
- Lore archive  : /mnt/OB1/lore/ (promoted long-term knowledge, read if relevant)
- Server status : http://192.168.1.41:5150/status (confirms OB1 is running)

### How to use it
1. At session start, read /mnt/OB1/session_digest.md before anything else
2. Use it to orient — active projects, recent decisions, open items, key terms
3. Do not edit session_digest.md manually — OB1 writes it automatically
4. If the digest is absent or stale, note it and proceed — do not block on it
5. If you produce a significant decision or outcome this session, flag it clearly
   so OB1 can capture it in the next digest cycle

### OB1 System Files (851Office-1: /mnt/OB1/)
- ob1_server.py   — always-on receiver, port 5150
- ob1_digest.py   — compression engine, writes session_digest.md
- ob1_aging.py    — OBDream cycle, promotes high-signal topics to lore (pending)
- session_digest.md — live digest, read this

### OB1 Capture (Chrome micro-extension)
- Lives on each Windows machine at C:\Chrome_Extensions\OB1_Capture\
- Runs silently on claude.ai — no UI, no interaction required
- Captures every turn automatically, POSTs to 851Office-1:5150

## Standing Orders
1. Never spend money without explicit authorization.
2. Never commit code to main branch without Legend's HiTL review.
3. Never close a gate item as complete — Legend closes gate items.
4. Flag, don't fix, anything outside your authorized scope.
5. Voice-dictation input is expected. Interpret miswords charitably.
6. Every deliverable must be paste-ready or autonomously executed.
   No manual file editing required of Legend.

## Session Open Protocol
1. Read /mnt/OB1/session_digest.md — orient to current project state.
2. State which brand context applies (Prism / JSG Labs).
3. Identify the active gate item from PROJECTS.md.
4. Report any blocking flags from the previous session if present.
5. Await direction or begin on the gate item if instructions are explicit.
