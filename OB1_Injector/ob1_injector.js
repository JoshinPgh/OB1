// ============================================================
// ob1_injector.js — OB1 Memory System
// JSG Labs / Geldrich Corp
//
// Standalone Chrome micro-extension content script.
// Runs on claude.ai only — specifically for Claude in Chrome sessions.
//
// What it does:
//   1. Fetches current session_digest.md from OB1 server
//   2. Injects digest into window.__ob1 on the Claude tab
//   3. Also writes digest to a hidden DOM element (fallback)
//   4. Claude in Chrome reads via javascript_tool
//
// THE TEST (sandboxing detection — runs automatically):
//   If window.__ob1.test returns "hello Legend" → window scope works
//   If undefined → pivot to hidden DOM element (also injected)
//   Either way Claude in Chrome gets the memory — just via different path
//
// Claude in Chrome reads memory with:
//   window.__ob1.test          → confirms injection worked
//   window.__ob1.digest        → full session digest markdown
//   window.__ob1.summary       → compressed one-paragraph summary
//   window.__ob1.injected_at   → timestamp of last injection
//
// Fallback DOM element (if window scope is sandboxed):
//   document.getElementById('__ob1_memory').dataset.digest
//   document.getElementById('__ob1_memory').dataset.summary
//
// Server:
//   Home:      http://192.168.1.41:5150
//   Tailscale: http://100.105.169.111:5150
//   Endpoint:  GET /digest → returns { digest: "..." }
//   Endpoint:  GET /status → health check
// ============================================================

// ---------------------------------------------------------------------------
// CONFIG
// ---------------------------------------------------------------------------

const OB1_HOME        = 'http://192.168.1.41:5150';
const OB1_TAILSCALE   = 'http://100.105.169.111:5150';
const INJECT_DELAY_MS = 1500;   // wait for Claude tab to settle before injecting
const REFRESH_MINS    = 15;     // re-fetch and re-inject digest every N minutes

// ---------------------------------------------------------------------------
// UTILITIES
// ---------------------------------------------------------------------------

function _log(msg) {
  console.log(`[OB1 Injector] ${msg}`);
}

function _warn(msg) {
  console.warn(`[OB1 Injector] ${msg}`);
}

function _timestamp() {
  return new Date().toISOString().replace('T', ' ').substring(0, 19);
}

// ---------------------------------------------------------------------------
// FETCH DIGEST FROM OB1 SERVER
// Tries home IP first, falls back to Tailscale
// ---------------------------------------------------------------------------

async function _fetchDigest() {
  const endpoints = [OB1_HOME, OB1_TAILSCALE];

  for (const base of endpoints) {
    try {
      const res = await fetch(`${base}/digest`, {
        signal: AbortSignal.timeout(4000),
      });

      if (res.ok) {
        const data = await res.json();
        _log(`Digest fetched from ${base} (${data.digest?.length || 0} chars)`);
        return data.digest || null;
      }
    } catch (_) {
      // Try next
    }
  }

  _warn('Could not fetch digest — OB1 server unreachable on home and Tailscale.');
  return null;
}

// ---------------------------------------------------------------------------
// BUILD SUMMARY
// Takes full digest markdown, returns compressed one-paragraph summary
// Extracts High Signal Topics section only — keeps injection small
// ---------------------------------------------------------------------------

function _buildSummary(digestText) {
  if (!digestText) return 'No digest available.';

  const lines = digestText.split('\n');
  const topicLines = [];
  let inTopics = false;

  for (const line of lines) {
    if (line.startsWith('## High Signal Topics')) {
      inTopics = true;
      continue;
    }
    if (inTopics && line.startsWith('## ')) {
      break; // hit next section
    }
    if (inTopics && line.startsWith('- ')) {
      // Strip markdown bold markers for clean summary
      topicLines.push(line.replace(/\*\*/g, '').replace(/^- /, '').trim());
    }
  }

  if (!topicLines.length) {
    return digestText.substring(0, 500); // fallback: first 500 chars
  }

  return `OB1 Active Context: ${topicLines.slice(0, 8).join(' | ')}`;
}

// ---------------------------------------------------------------------------
// PRIMARY INJECTION — window.__ob1
// This is what Claude in Chrome reads via javascript_tool
// ---------------------------------------------------------------------------

function _injectWindowObject(digest, summary) {
  try {
    window.__ob1 = {
      test:         'hello Legend',           // sandboxing test value
      digest:       digest || 'No digest yet.',
      summary:      summary || 'No summary yet.',
      injected_at:  _timestamp(),
      source:       'OB1 Memory System — JSG Labs / Geldrich Corp',
      instructions: [
        'Read window.__ob1.summary for a quick context brief.',
        'Read window.__ob1.digest for full session history.',
        'This memory was captured automatically from your Claude sessions.',
        'You are Claude in Chrome. Use this context to operate with full project awareness.',
        'Legend = Josh Geldrich. Active company = Geldrich Corp / JSG Labs.',
      ].join(' '),
    };

    _log(`window.__ob1 injected. Test value: "${window.__ob1.test}"`);
    _log(`Summary: ${summary?.substring(0, 80)}...`);
    return true;
  } catch (err) {
    _warn(`window.__ob1 injection failed: ${err.message}`);
    return false;
  }
}

// ---------------------------------------------------------------------------
// FALLBACK INJECTION — hidden DOM element
// Used if Claude in Chrome's javascript_tool is sandboxed from window scope
// Claude reads via: document.getElementById('__ob1_memory').dataset.digest
// ---------------------------------------------------------------------------

function _injectDOMElement(digest, summary) {
  try {
    // Remove existing element if present (refresh)
    const existing = document.getElementById('__ob1_memory');
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.id = '__ob1_memory';
    el.style.cssText = 'display:none;position:absolute;width:0;height:0;overflow:hidden;';
    el.dataset.test        = 'hello Legend';
    el.dataset.digest      = digest || 'No digest yet.';
    el.dataset.summary     = summary || 'No summary yet.';
    el.dataset.injectedAt  = _timestamp();
    el.dataset.source      = 'OB1 Memory System — JSG Labs / Geldrich Corp';

    document.body.appendChild(el);
    _log(`DOM fallback element injected (#__ob1_memory)`);
    return true;
  } catch (err) {
    _warn(`DOM element injection failed: ${err.message}`);
    return false;
  }
}

// ---------------------------------------------------------------------------
// VERIFY INJECTION
// Confirms window.__ob1 is readable — logs result for DevTools inspection
// This IS the sandboxing test from the April 26 development note
// ---------------------------------------------------------------------------

function _verifyInjection() {
  try {
    const testVal = window.__ob1?.test;
    if (testVal === 'hello Legend') {
      _log('SANDBOXING TEST PASSED — window.__ob1 is readable.');
      _log('Claude in Chrome can use: window.__ob1.digest');
      _log('Claude in Chrome can use: window.__ob1.summary');
      return 'window';
    } else {
      _warn('SANDBOXING TEST — window.__ob1 not readable from this scope.');
      _warn('Claude in Chrome should use DOM fallback:');
      _warn('  document.getElementById("__ob1_memory").dataset.digest');
      return 'dom';
    }
  } catch (err) {
    _warn(`Verification error: ${err.message}`);
    return 'dom';
  }
}

// ---------------------------------------------------------------------------
// MAIN INJECTION CYCLE
// ---------------------------------------------------------------------------

async function inject() {
  _log('OB1 Injector starting...');

  const digest  = await _fetchDigest();
  const summary = _buildSummary(digest);

  // Inject both — window scope primary, DOM element fallback
  _injectWindowObject(digest, summary);
  _injectDOMElement(digest, summary);

  // Run sandboxing test — result visible in DevTools console
  const accessPath = _verifyInjection();

  _log('--- OB1 INJECTION COMPLETE ---');
  _log(`Access path confirmed: ${accessPath === 'window' ? 'window.__ob1' : '#__ob1_memory dataset'}`);
  _log('Claude in Chrome: read window.__ob1.test to confirm access.');

  return accessPath;
}

// ---------------------------------------------------------------------------
// AUTO-REFRESH
// Re-fetches digest and re-injects every REFRESH_MINS minutes
// Keeps memory current across long Claude in Chrome sessions
// ---------------------------------------------------------------------------

function _startRefreshCycle() {
  setInterval(async () => {
    _log(`Auto-refresh triggered (every ${REFRESH_MINS} min)`);
    await inject();
  }, REFRESH_MINS * 60 * 1000);
}

// ---------------------------------------------------------------------------
// INIT
// ---------------------------------------------------------------------------

async function init() {
  // Wait for Claude tab to fully load
  await new Promise(r => setTimeout(r, INJECT_DELAY_MS));

  // Only run on claude.ai
  if (!window.location.hostname.includes('claude.ai')) return;

  await inject();
  _startRefreshCycle();

  _log(`OB1 Injector active. Refreshing every ${REFRESH_MINS} minutes.`);
  _log('Open DevTools console to see injection status and test results.');
}

// ---------------------------------------------------------------------------
// BOOT
// ---------------------------------------------------------------------------

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
