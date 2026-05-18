# OB1 — Scored Digest Memory System

> Automatic Claude memory. Captures every session, distills what matters, discards the noise. Context without the token tax.

---

## What Is OB1?

OB1 is a **Scored Digest Memory System (SDMS)** built for Claude. It captures everything that happens in your Claude sessions, scores it by frequency and signal strength, compresses it through a Dream Cycle, and delivers the right context at the right time — without burning your token budget.

It is not a wiki. It is not a vector database. It is not a flat file dump.

It is a four-layer cognitive memory architecture modeled on how biological memory actually works.

---

## The Memory Stack

```
CLAUDE.md        — Non-declarative / behavioral memory
                   Who Claude is in this partnership.
                   How you work. Tone, pace, preferences.
                   Not managed by OB1. Lives in Claude settings.

ob1_hot.md       — Working memory
                   Last session context. ~500 tokens.
                   Injected automatically at session start.
                   Eliminates the recap problem entirely.

ob1_digest.md    — Declarative memory (episodic + semantic)
                   What happened. What was decided.
                   What you know. What matters.
                   Scored, compressed, and maintained
                   by the Dream Cycle.

Lore DB          — Deep factual archive
                   Promoted from digest only after passing
                   all three gate thresholds.
                   Long-term. Independently queryable.
                   Rarely injected. Always there.
```

---

## How It Works

### Capture
OB1_Capture monitors your Claude sessions via a lightweight Chrome extension. Every turn — your messages and Claude's responses — is captured automatically. No manual steps. No end-of-session rituals.

### Digest
OB1_Digest scores captured content by term frequency, recency, and signal density. High-frequency concepts strengthen. Low-signal noise fades. The output is a compressed, ranked digest file ready for context injection.

### Dream Cycle (OBDream)
The Dream Cycle runs on a scheduled basis — modeled on biological sleep consolidation. It:
- Scores all active digest entries
- Promotes high-signal entries that pass all three gates into Lore
- Retires stale or low-signal entries
- Compresses the digest to minimum viable size
- Updates ob1_hot.md with current working memory

Promotion gates (all three must pass):
- `relevancy_score >= 0.6`
- `recall_count >= 3`
- `unique_query_count >= 2`

### Inject
At session start, ob1_hot.md is injected automatically. Claude knows where you left off before you type a word.

---

## Architecture

```
OB1_Capture/          — Chrome extension
    manifest.json
    ob1_capture.js

OB1_Injector/         — Context injection layer
    manifest.json
    ob1_injector.js

OB1_Server/           — Python backend
    ob1_digest.py     — Scoring + compression engine
    ob1_server.py     — Local server + Dream Cycle scheduler
```

Runs locally. No cloud. No external dependencies beyond Python stdlib and SQLite.
Hosted on your Ubuntu headless server at `/mnt/OB1/`.

---

## Memory Layers — Detail

### Working Memory (`ob1_hot.md`)
~500 words. Last session context. What you were building, what decisions were made, what's next. Injected silently at session start. Costs less than 0.25% of Claude's context window. Returns 4–6x that in eliminated recap overhead.

### Declarative Memory (`ob1_digest.md`)
Episodic + semantic. Episodic memory covers events, experiences, and session history (what happened, when, why it mattered). Semantic memory covers concepts, decisions, patterns, and domain knowledge. The Dream Cycle keeps this layer lean and accurate.

### Deep Archive (`Lore DB`)
SQLite. Independently queryable. Promoted memories that have proven their value across multiple sessions and query contexts. Designed for future integration with NotebookLM, company KB, or RAG layer when scale demands it.

### Behavioral Memory (`CLAUDE.md`)
Non-declarative. Not managed by OB1. Lives in Claude project settings. Covers how you work, communication style, operational directives, hardware stack, priorities. The things Claude should always know without being told.

---

## Honest Shelf Life

OB1 is designed to carry you through the build phase of an AI-native operation.

**Estimated useful life: ~1 year at current session volume.**

Entropy is real. As the digest grows, compression gets lossier. As Lore expands, query precision becomes more important. When you start noticing edge-case detail dropping out of context, that's the system telling you it's time for the next layer — likely a proper vector store with embedding-based retrieval.

OB1's job is to get you to the point where you have the revenue, the usage patterns, and the real-world data to build that next layer correctly.

When that time comes, everything in Lore is already structured for RAG ingestion. The migration path is built in.

---

## What OB1 Is Not

- **Not a wiki** — OB1 doesn't require you to organize or maintain anything manually
- **Not a vector DB** — No embeddings, no Pinecone, no ChromaDB, no GPU
- **Not a RAG system** — No semantic search infrastructure (yet)
- **Not a token monster** — Designed from the ground up to minimize context cost

---

## Related Systems

**ATR (AI Thread Relay)** — The Chrome extension that monitors context window saturation and relays sessions before quality degrades. OB1 and ATR are complementary. ATR handles session continuity. OB1 handles memory persistence.

**SonglineMemory** — The predecessor graph-based memory system. Technically sophisticated, operationally heavy. Retired to the shelf. The Lore DB architecture in OB1 is directly descended from SonglineMemory's promotion/retirement model. Nothing was wasted.

---

## Future Build Triggers

You'll know it's time to invest in the next layer when:

- Digest injection starts costing meaningful tokens again
- You need sub-second semantic search across hundreds of Lore entries
- Multiple agents are querying memory simultaneously
- The Dream Cycle compression starts losing signal you need

Until then — build on OB1 with confidence.

---

## Stack

- Python 3.x — stdlib only, zero external dependencies
- SQLite — Lore DB
- Chrome Extension (Manifest V3) — Capture + Inject
- Ubuntu headless server — Runtime host
- Markdown flat files — ob1_hot.md, ob1_digest.md

---

*OB1 — JSG Labs / Geldrich Corp*
*Built for the pilot who is also the engineer.*
