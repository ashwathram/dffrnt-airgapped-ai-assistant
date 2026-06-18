// Chat view: empty state, message rendering, sending, and the composer.
import { $, esc, nowTime } from './util.js';
import { svg } from './icons.js';
import { state, SUGGESTIONS } from './state.js';
import { renderMarkdown } from './markdown.js';
import { queryStream, createConversation, updateConversation, getConversation } from './api.js';
import { loadConversations, renderSidebar } from './sidebar.js';

let nextId = 0;
const mkId = () => 'm' + (++nextId);  // stable per-message id for actions/targeting
let abortController = null;           // in-flight stream, so the Stop button can cancel it

// Turn "[1]" markers into clickable citation chips mapped to sources by index.
// Operates on already-escaped text so it can be reused as the Markdown inline
// hook (it then only ever sees non-code text, leaving code spans untouched).
function citeChips(sources) {
  return (escaped) => escaped.replace(/\[(\d+)\]/g, (m, n) => {
    const i = parseInt(n, 10);
    if (sources && i >= 1 && i <= sources.length) {
      return `<span class="cite-chip" title="${esc(sources[i - 1].filename)}">${i}</span>`;
    }
    return m;
  });
}

// User turns: plain escaped text + citation chips (no Markdown).
function renderContent(text, sources) {
  return citeChips(sources)(esc(text));
}

// Assistant answers: render Markdown to safe HTML, with citation chips applied
// to the plain-text runs. .md scopes the styling and resets the bubble's
// pre-wrap (see styles/markdown.css).
function renderAnswer(text, sources) {
  return `<div class="md">${renderMarkdown(text, { inline: citeChips(sources) })}</div>`;
}

// Sources panel — collapses to the first 2 with a "+N more / Show less" toggle.
function sourcesHtml(m) {
  const sources = m.sources || [];
  if (!sources.length) return '';
  const visible = m.sourcesExpanded ? sources : sources.slice(0, 2);
  // Each source links to the stored file (served from data_dir by the backend).
  const row = (s, i) => `
    <a class="source" href="/api/documents/${encodeURIComponent(s.filename)}/raw" target="_blank" rel="noopener" title="Open ${esc(s.filename)}">
      <span class="num">${i + 1}</span>
      <span class="body">
        <span class="fn">${esc(s.filename)}</span>
        <span class="meta">${s.page ? 'p. ' + esc(s.page) : ''}${s.score != null ? ' · score ' + s.score : ''}</span>
      </span>
      ${svg('externalLink')}
    </a>`;
  const toggle = sources.length > 2
    ? `<button class="src-toggle" data-srctoggle="${m.id}">${m.sourcesExpanded ? 'Show less' : '+' + (sources.length - 2) + ' more'}</button>`
    : '';
  return `
    <div class="sources">
      <div class="src-head"><span class="lbl">SOURCES</span>${toggle}</div>
      ${visible.map(row).join('')}
    </div>`;
}

function emptyStateHtml() {
  return `
    <div class="empty">
      <div>
        <div class="orb">${svg('sparkles')}</div>
        <h2>How can I help you today?</h2>
        <p>Ask questions about your documents. The assistant answers only from your knowledge base.</p>
      </div>
      <div class="suggestions">
        ${SUGGESTIONS.map((s, i) => `<button class="suggestion" data-suggest="${i}">${svg(s.icon)}${esc(s.text)}</button>`).join('')}
      </div>
    </div>`;
}

// Stylized, collapsible reasoning block — shown when "Show thinking" is on.
// Open while streaming so the user can watch it think; collapsed once done.
function thinkingBlockHtml(m) {
  const openAttr = m.streaming ? ' open' : '';
  const cursor = (m.streaming && !m.content) ? '<span class="stream-cursor"></span>' : '';
  return `<details class="thinking-block"${openAttr}>`
    + `<summary>${svg('brain')} Thinking</summary>`
    + `<div class="thinking-body">${esc(m.thinking)}${cursor}</div>`
    + '</details>';
}

// Inner HTML of an assistant bubble — reused for live streaming updates.
// Sources are shown only once streaming is complete (they arrive first, but
// reading the answer first matches the prototype).
function bubbleInner(m) {
  let html = '';
  // Reasoning: a full block (toggle on) or a plain "Thinking…" label (toggle off).
  if (state.showThinking && m.thinking) {
    html += thinkingBlockHtml(m);
  } else if (!state.showThinking && m.streaming && !m.content) {
    html += '<span class="thinking-label">Thinking…</span>';
  }
  // Answer text (Markdown + citation chips) + a caret while it streams.
  if (m.content) {
    html += renderAnswer(m.content, m.sources);
    if (m.streaming) html += '<span class="stream-cursor"></span>';
  }
  if (!m.streaming) html += sourcesHtml(m);
  return html;
}

// Hover action row under a finished assistant message.
function actionRowHtml(m) {
  return `
    <div class="msg-actions">
      <button class="ma" data-msg-action="copy" data-id="${m.id}" title="Copy">${svg('copy')}</button>
      <button class="ma${m.feedback === 'up' ? ' on' : ''}" data-msg-action="up" data-id="${m.id}" title="Good response">${svg('thumbsUp')}</button>
      <button class="ma${m.feedback === 'down' ? ' on' : ''}" data-msg-action="down" data-id="${m.id}" title="Bad response">${svg('thumbsDown')}</button>
      <button class="ma" data-msg-action="regenerate" data-id="${m.id}" title="Regenerate">${svg('refresh')}</button>
      ${m.ts ? `<span class="ma-ts">${esc(m.ts)}</span>` : ''}
    </div>`;
}

function messageHtml(m) {
  if (m.role === 'notice') {
    return `<div class="notice">${svg('alert')}<span>${esc(m.content)}</span></div>`;
  }
  const isUser = m.role === 'user';
  const bubbleId = m.streaming ? ' id="streamBubble"' : '';
  let footer = '';
  if (isUser) footer = m.ts ? `<div class="ts">${esc(m.ts)}</div>` : '';
  else if (!m.streaming) footer = actionRowHtml(m);
  return `
    <div class="msg ${isUser ? 'user' : 'assistant'}">
      ${isUser ? '' : '<div class="avatar">AI</div>'}
      <div class="col">
        <div class="bubble"${bubbleId}>${isUser ? renderContent(m.content, m.sources) : bubbleInner(m)}</div>
        ${footer}
      </div>
    </div>`;
}

const typingHtml = `
  <div class="msg assistant">
    <div class="avatar">AI</div>
    <div class="col"><div class="bubble"><span class="typing"><span></span><span></span><span></span></span></div></div>
  </div>`;

export function renderMessages() {
  const box = $('messages');
  if (!state.messages.length && !state.busy) {
    box.innerHTML = emptyStateHtml();
    box.querySelectorAll('[data-suggest]').forEach((b) => {
      b.onclick = () => sendMessage(SUGGESTIONS[+b.dataset.suggest].text);
    });
    return;
  }
  box.innerHTML = '<div class="messages-inner">'
    + state.messages.map(messageHtml).join('')
    + (state.busy ? typingHtml : '')
    + '</div>';
  box.querySelectorAll('.cite-chip').forEach((c) => {
    c.onclick = () => c.classList.toggle('active');
  });
  box.querySelectorAll('[data-msg-action]').forEach((b) => {
    b.onclick = () => onMessageAction(b.dataset.msgAction, b.dataset.id, b);
  });
  box.querySelectorAll('[data-srctoggle]').forEach((b) => {
    b.onclick = () => {
      const m = state.messages.find((x) => x.id === b.dataset.srctoggle);
      if (m) { m.sourcesExpanded = !m.sourcesExpanded; renderMessages(); }
    };
  });
  box.scrollTop = box.scrollHeight;
}

// Patch just the streaming bubble between full re-renders (cheap, per token).
function updateStreamingBubble(m) {
  const el = $('streamBubble');
  if (!el) return;
  el.innerHTML = bubbleInner(m);
  const tb = el.querySelector('.thinking-body');
  if (tb) tb.scrollTop = tb.scrollHeight; // keep the live reasoning scrolled to newest
  const box = $('messages');
  box.scrollTop = box.scrollHeight;
}

export async function sendMessage(text) {
  text = (text || '').trim();
  if (!text || state.busy) return;
  state.messages.push({ id: mkId(), role: 'user', content: text, ts: nowTime() });
  $('topbarTitle').textContent = 'Conversation';
  await runQuery();
}

// Persist the current conversation to the server (create on first turn, then
// update). Only real turns are stored — thinking and UI flags are dropped.
async function persist() {
  const msgs = state.messages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ role: m.role, content: m.content, sources: m.sources || [], ts: m.ts || '' }));
  if (!msgs.length) return;
  if (!state.conversationId) {
    const title = (state.messages.find((m) => m.role === 'user') || {}).content || 'New conversation';
    const { ok, data } = await createConversation({ title: title.slice(0, 80), messages: msgs });
    if (ok) state.conversationId = data.id;
  } else {
    await updateConversation(state.conversationId, { messages: msgs });
  }
  loadConversations();
}

// Load a saved conversation into the chat view (or clear it when id is null).
export async function loadConversation(id) {
  if (abortController) abortController.abort();
  if (!id) { clearChat(); return; }
  const { ok, data } = await getConversation(id);
  if (!ok) { clearChat(); return; }
  state.conversationId = id;
  state.busy = false;
  state.messages = (data.messages || []).map((m) => ({
    id: mkId(), role: m.role, content: m.content, sources: m.sources || [], ts: m.ts || '', feedback: null,
  }));
  renderMessages();
  refreshSendBtn();
  renderSidebar();
  $('topbarTitle').textContent = 'Conversation';
}

// Answer the most recent user turn. Used for both a fresh send and Regenerate,
// so neither needs to re-add the user message.
async function runQuery() {
  const turns = state.messages.filter((m) => m.role === 'user' || m.role === 'assistant');
  const last = turns[turns.length - 1];
  if (!last || last.role !== 'user') return;
  const question = last.content;
  const history = turns.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));

  state.busy = true; // guard concurrent sends + show the typing indicator + Stop button
  renderMessages();
  refreshSendBtn();

  const assistant = { id: mkId(), role: 'assistant', content: '', thinking: '', sources: [], streaming: true, feedback: null };
  let started = false;
  // Add the assistant bubble on the first thinking/answer token, replacing the
  // standalone typing indicator.
  const ensureStarted = () => {
    if (started) return;
    started = true;
    state.busy = false;
    state.messages.push(assistant);
    renderMessages();
    refreshSendBtn();
  };

  abortController = new AbortController();
  try {
    for await (const ev of queryStream(question, history, abortController.signal, state.chatScope)) {
      if (ev.type === 'sources') {
        assistant.sources = ev.sources || [];
      } else if (ev.type === 'thinking') {
        assistant.thinking += ev.text;
        ensureStarted();
        if (state.showThinking) updateStreamingBubble(assistant); // OFF: static "Thinking…"
      } else if (ev.type === 'token') {
        assistant.content += ev.text;
        ensureStarted();
        updateStreamingBubble(assistant);
      } else if (ev.type === 'error') {
        if (!started) state.messages.push({ id: mkId(), role: 'notice', content: ev.detail });
        break;
      }
      // 'done' needs no action; the loop simply ends.
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      // User pressed Stop — keep whatever streamed so far.
    } else if (!started) {
      state.messages.push({ id: mkId(), role: 'notice', content: 'Could not reach the assistant. Check the server connection.' });
    }
  } finally {
    abortController = null;
  }

  state.busy = false;
  assistant.streaming = false;
  if (started) {
    assistant.ts = nowTime();
    // If Stop hit before anything streamed, drop the empty bubble.
    if (!assistant.content.trim() && !assistant.thinking.trim()) {
      const i = state.messages.indexOf(assistant);
      if (i >= 0) state.messages.splice(i, 1);
    }
  }
  renderMessages();
  refreshSendBtn();
  persist();
}

function stopStreaming() {
  if (abortController) abortController.abort();
}

// -- Message actions (copy / feedback / regenerate) ------------------------
function onMessageAction(action, id, btn) {
  const m = state.messages.find((x) => x.id === id);
  if (!m) return;
  if (action === 'copy') { copyText(m.content, btn); return; }
  if (action === 'up' || action === 'down') {
    m.feedback = m.feedback === action ? null : action; // local only (no backend)
    renderMessages();
    return;
  }
  if (action === 'regenerate') regenerate(id);
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const el = document.createElement('textarea');
    el.value = text; el.style.position = 'fixed'; el.style.opacity = '0';
    document.body.appendChild(el); el.select();
    try { document.execCommand('copy'); } finally { el.remove(); }
  }
  if (btn) { const html = btn.innerHTML; btn.textContent = '✓'; setTimeout(() => { btn.innerHTML = html; }, 1200); }
}

function regenerate(assistantId) {
  if (state.busy) return;
  const idx = state.messages.findIndex((m) => m.id === assistantId);
  if (idx < 0) return;
  state.messages = state.messages.slice(0, idx); // drop this answer (and anything after)
  renderMessages();
  runQuery();
}

// Toggle the composer button between Send and Stop based on stream state.
function refreshSendBtn() {
  const btn = $('sendBtn');
  if (!btn) return;
  if (state.busy) {
    btn.innerHTML = svg('square');
    btn.classList.add('stop', 'ready');
    btn.title = 'Stop';
  } else {
    btn.innerHTML = svg('send');
    btn.classList.remove('stop');
    btn.classList.toggle('ready', ($('composer').value || '').trim().length > 0);
    btn.title = 'Send (Enter)';
  }
}

export function clearChat() {
  if (abortController) abortController.abort();
  state.messages = [];
  state.busy = false;
  state.conversationId = null;
  renderMessages();
  renderSidebar();
  refreshSendBtn();
  $('topbarTitle').textContent = 'New conversation';
}

export function initComposer() {
  const composer = $('composer');
  const sync = () => {
    composer.style.height = 'auto';
    composer.style.height = Math.min(composer.scrollHeight, 160) + 'px';
    const len = composer.value.trim().length;
    $('charCount').textContent = len ? String(len) : '';
    refreshSendBtn();
  };
  const submit = () => { const v = composer.value; composer.value = ''; sync(); sendMessage(v); };

  composer.addEventListener('input', sync);
  composer.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!state.busy) submit(); }
  });
  $('sendBtn').onclick = () => { if (state.busy) stopStreaming(); else submit(); };
  sync();
}
