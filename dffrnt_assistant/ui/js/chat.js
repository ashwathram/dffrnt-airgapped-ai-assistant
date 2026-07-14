// Chat view: empty state, message rendering, sending, and the composer.
import { $, esc, nowTime } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import { renderMarkdown } from './markdown.js';
import { queryStream, createConversation, updateConversation, getConversation } from './api.js';
import { loadConversations, renderSidebar } from './sidebar.js';

let nextId = 0;
const mkId = () => 'm' + (++nextId);  // stable per-message id for actions/targeting
let abortController = null;           // in-flight stream, so the Stop button can cancel it
let nextModeOverride = null;          // one-shot per-send mode override for suggested RFP actions
const RFP_SOURCE_PREVIEW_LIMIT = 5;
const PARENT_SOURCE_MODES = new Set(['rfp']);

function selectedFilesInScope() {
  const docs = state.documents || [];
  if (!state.chatScope.length) return docs;
  return docs.filter((d) => state.chatScope.some((t) => (d.tags || []).includes(t)));
}

function looksLikeRfp(name) {
  const lower = String(name || '').toLowerCase();
  return lower.includes('rfp') || lower.includes('request for proposal');
}

function sourceDisplayModel(m) {
  const rawSources = m.sources || [];
  if (!rawSources.length) return { sources: [], indexMap: new Map() };

  if (!PARENT_SOURCE_MODES.has(m.mode)) {
    return {
      sources: rawSources,
      indexMap: new Map(rawSources.map((_, idx) => [idx + 1, idx + 1])),
    };
  }

  const sources = [];
  const fileToIndex = new Map();
  const indexMap = new Map();
  rawSources.forEach((source, idx) => {
    const filename = String(source.filename || `source-${idx + 1}`);
    let mapped = fileToIndex.get(filename);
    if (!mapped) {
      mapped = sources.length + 1;
      fileToIndex.set(filename, mapped);
      sources.push({
        filename,
        title: source.title || filename,
      });
    }
    indexMap.set(idx + 1, mapped);
  });
  return { sources, indexMap };
}

// Turn "[1]" markers into clickable citation chips mapped to sources by index.
// data-msg/data-cite let a click scroll to and highlight the matching source
// card (see focusSource). Operates on already-escaped text so it can be reused
// as the Markdown inline hook (it then only ever sees non-code text, leaving
// code spans untouched).
function citeChips(message) {
  const display = sourceDisplayModel(message);
  return (escaped) => escaped.replace(/\[(\d+)\]/g, (match, n) => {
    const mapped = display.indexMap.get(parseInt(n, 10));
    if (mapped && display.sources[mapped - 1]) {
      const source = display.sources[mapped - 1];
      return `<span class="cite-chip" data-msg="${message.id}" data-cite="${mapped}" title="${esc(source.filename)}">${mapped}</span>`;
    }
    return match;
  });
}

// User turns: plain escaped text + citation chips (no Markdown).
function renderContent(text, message) {
  return citeChips(message)(esc(text));
}

// Assistant answers: render Markdown to safe HTML, with citation chips applied
// to the plain-text runs. .md scopes the styling and resets the bubble's
// pre-wrap (see styles/markdown.css).
function renderAnswer(text, message) {
  return `<div class="md">${renderMarkdown(text, { inline: citeChips(message) })}</div>`;
}

// Sources panel - the answer's [n] markers tell us which sources were actually
// cited. For RFP/resume workflows, citations collapse to parent files only.
function sourcesHtml(m) {
  const display = sourceDisplayModel(m);
  const sources = display.sources;
  if (!sources.length) return '';

  const cited = new Set();
  (m.content || '').replace(/\[(\d+)\]/g, (_, n) => {
    const mapped = display.indexMap.get(parseInt(n, 10));
    if (mapped && mapped >= 1 && mapped <= sources.length) cited.add(mapped);
    return '';
  });

  const row = (s, n) => {
    const meta = PARENT_SOURCE_MODES.has(m.mode)
      ? esc(s.filename)
      : `${esc(s.filename)}${s.page ? ' · p. ' + esc(s.page) : ''}${s.score != null ? ' · score ' + s.score : ''}`;
    const excerpt = PARENT_SOURCE_MODES.has(m.mode)
      ? ''
      : (s.excerpt ? `<span class="excerpt">"${esc(s.excerpt)}"</span>` : '');
    return `
      <a class="source" id="src-${m.id}-${n}" href="/api/documents/${encodeURIComponent(s.filename)}/raw" target="_blank" rel="noopener" title="Open ${esc(s.filename)}">
        <span class="num">${n}</span>
        <span class="body">
          <span class="fn">${esc(s.title || s.filename)}</span>
          <span class="meta">${meta}</span>
          ${excerpt}
        </span>
        ${svg('externalLink')}
      </a>`;
  };

  const numbered = sources.map((s, idx) => [s, idx + 1]);
  const anyCited = numbered.some(([, n]) => cited.has(n));
  const primary = PARENT_SOURCE_MODES.has(m.mode)
    ? numbered.slice(0, RFP_SOURCE_PREVIEW_LIMIT)
    : (anyCited ? numbered.filter(([, n]) => cited.has(n)) : numbered);
  const secondary = PARENT_SOURCE_MODES.has(m.mode)
    ? numbered.slice(RFP_SOURCE_PREVIEW_LIMIT)
    : (anyCited ? numbered.filter(([, n]) => !cited.has(n)) : []);

  const n2 = secondary.length;
  const secondaryHtml = n2
    ? `<button class="src-toggle" data-srctoggle="${m.id}">${m.sourcesExpanded ? 'Hide' : (PARENT_SOURCE_MODES.has(m.mode) ? 'Check more' : 'Show')} ${n2} ${PARENT_SOURCE_MODES.has(m.mode) ? `more file${n2 > 1 ? 's' : ''}` : `other retrieved source${n2 > 1 ? 's' : ''}`}</button>`
      + (m.sourcesExpanded ? `<div class="sources-secondary">${secondary.map(([s, n]) => row(s, n)).join('')}</div>` : '')
    : '';

  return `
    <div class="sources">
      <div class="src-head"><span class="lbl">SOURCES</span></div>
      ${primary.map(([s, n]) => row(s, n)).join('')}
      ${secondaryHtml}
    </div>`;
}

function emptyStateHtml() {
  return `
    <div class="empty">
      <div>
        <div class="orb">${svg('sparkles')}</div>
        <h2>How can I help you today?</h2>
        <p>Ask questions about your documents. Use the tag filter above to focus on specific document sets.</p>
      </div>
    </div>`;
}

// Stylized, collapsible reasoning block - shown when "Show thinking" is on.
// Open while streaming so the user can watch it think; collapsed once done.
// The model streams free-form text; we render it as a bulleted "reasoning
// trace" by splitting on newlines, highlighting the line currently streaming.
function thinkingBlockHtml(m) {
  const openAttr = m.streaming ? ' open' : '';
  const label = m.streaming ? 'Thinking...' : 'Thought process';
  const cursor = m.streaming ? '<span class="stream-cursor"></span>' : '';
  const lines = (m.thinking || '').split('\n').map((l) => l.trim()).filter(Boolean);
  const line = (text, current) =>
    `<div class="trace-line${current ? ' current' : ''}">`
    + '<span class="trace-dot"></span>'
    + `<span class="trace-text">${esc(text)}${current && m.streaming ? cursor : ''}</span>`
    + '</div>';
  const items = lines.length
    ? lines.map((l, i) => line(l, i === lines.length - 1)).join('')
    : line('', true);
  return `<details class="thinking-block"${openAttr}>`
    + `<summary>${svg('brain')} ${label}</summary>`
    + `<div class="thinking-body"><p class="trace-label">Reasoning trace</p>${items}</div>`
    + '</details>';
}

// Inner HTML of an assistant bubble - reused for live streaming updates.
// Sources are shown only once streaming is complete (they arrive first, but
// reading the answer first matches the prototype).
function bubbleInner(m) {
  let html = '';
  if (state.showThinking && m.thinking) {
    html += thinkingBlockHtml(m);
  } else if (!state.showThinking && m.streaming && !m.content) {
    html += '<span class="thinking-label">Thinking...</span>';
  }
  if (m.content) {
    html += renderAnswer(m.content, m);
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
        <div class="bubble"${bubbleId}>${isUser ? renderContent(m.content, m) : bubbleInner(m)}</div>
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
    return;
  }
  box.innerHTML = '<div class="messages-inner">'
    + state.messages.map(messageHtml).join('')
    + (state.busy ? typingHtml : '')
    + '</div>';
  box.querySelectorAll('.cite-chip').forEach((c) => {
    c.onclick = () => focusSource(c.dataset.msg, parseInt(c.dataset.cite, 10));
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

// Clicking a "[n]" citation chip scrolls to its source card and flashes it.
function focusSource(msgId, n) {
  const m = state.messages.find((x) => x.id === msgId);
  const display = m ? sourceDisplayModel(m) : null;
  if (!m || !display || !display.sources.length || n < 1 || n > display.sources.length) return;
  if (!document.getElementById(`src-${msgId}-${n}`) && !m.sourcesExpanded) {
    m.sourcesExpanded = true;
    renderMessages();
  }
  const card = document.getElementById(`src-${msgId}-${n}`);
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  card.classList.remove('flash');
  void card.offsetWidth;
  card.classList.add('flash');
}

// Patch just the streaming bubble between full re-renders (cheap, per token).
function updateStreamingBubble(m) {
  const el = $('streamBubble');
  if (!el) return;
  el.innerHTML = bubbleInner(m);
  const tb = el.querySelector('.thinking-body');
  if (tb) tb.scrollTop = tb.scrollHeight;
  const box = $('messages');
  box.scrollTop = box.scrollHeight;
}

export async function sendMessage(text, modeOverride = null) {
  text = (text || '').trim();
  if (!text || state.busy) return;
  nextModeOverride = modeOverride;
  state.messages.push({ id: mkId(), role: 'user', content: text, ts: nowTime(), mode: modeOverride || state.queryMode });
  $('topbarTitle').textContent = (state.messages.find((m) => m.role === 'user') || {}).content || 'Conversation';
  await runQuery();
}

// Persist the current conversation to the server (create on first turn, then
// update). Only real turns are stored - thinking and UI flags are dropped.
async function persist() {
  const msgs = state.messages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({ role: m.role, content: m.content, sources: m.sources || [], ts: m.ts || '', mode: m.mode || 'chat' }));
  if (!msgs.length) return;
  if (!state.conversationId) {
    const title = (state.messages.find((m) => m.role === 'user') || {}).content || 'New conversation';
    const { ok, data } = await createConversation({ title: title.slice(0, 80), messages: msgs, mode: state.queryMode });
    if (ok) state.conversationId = data.id;
  } else {
    await updateConversation(state.conversationId, { messages: msgs, mode: state.queryMode });
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
  state.queryMode = 'chat';
  state.pendingAction = null;
  syncWorkflowToggles();
  state.busy = false;
  state.messages = (data.messages || []).map((m) => ({
    id: mkId(),
    role: m.role,
    content: m.content,
    sources: m.sources || [],
    ts: m.ts || '',
    feedback: null,
    mode: m.mode || 'chat',
  }));
  renderMessages();
  refreshSendBtn();
  renderSidebar();
  $('topbarTitle').textContent = data.title || 'Conversation';
}

// Answer the most recent user turn. Used for both a fresh send and Regenerate.
async function runQuery() {
  const turns = state.messages.filter((m) => m.role === 'user' || m.role === 'assistant');
  const last = turns[turns.length - 1];
  if (!last || last.role !== 'user') return;
  const question = last.content;
  const history = turns.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
  const effectiveMode = nextModeOverride || state.queryMode;
  nextModeOverride = null;

  state.busy = true;
  renderMessages();
  refreshSendBtn();

  const assistant = {
    id: mkId(),
    role: 'assistant',
    content: '',
    thinking: '',
    sources: [],
    streaming: true,
    feedback: null,
    mode: effectiveMode,
  };
  let started = false;
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
    for await (const ev of queryStream(question, history, abortController.signal, state.chatScope, effectiveMode)) {
      if (ev.type === 'sources') {
        assistant.sources = ev.sources || [];
      } else if (ev.type === 'thinking') {
        assistant.thinking += ev.text;
        ensureStarted();
        if (state.showThinking) updateStreamingBubble(assistant);
      } else if (ev.type === 'token') {
        assistant.content += ev.text;
        ensureStarted();
        updateStreamingBubble(assistant);
      } else if (ev.type === 'error') {
        if (!started) state.messages.push({ id: mkId(), role: 'notice', content: ev.detail, mode: effectiveMode });
        break;
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError' && !started) {
      state.messages.push({ id: mkId(), role: 'notice', content: 'Could not reach the assistant. Check the server connection.', mode: effectiveMode });
    }
  } finally {
    abortController = null;
  }

  state.busy = false;
  assistant.streaming = false;
  if (started) {
    assistant.ts = nowTime();
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
    m.feedback = m.feedback === action ? null : action;
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
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    try { document.execCommand('copy'); } finally { el.remove(); }
  }
  if (btn) {
    const html = btn.innerHTML;
    btn.textContent = '✓';
    setTimeout(() => { btn.innerHTML = html; }, 1200);
  }
}

function regenerate(assistantId) {
  if (state.busy) return;
  const idx = state.messages.findIndex((m) => m.id === assistantId);
  if (idx < 0) return;
  state.messages = state.messages.slice(0, idx);
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
  state.pendingAction = null;
  syncWorkflowToggles();
  renderMessages();
  renderSidebar();
  refreshSendBtn();
  $('topbarTitle').textContent = 'New conversation';
}

export function syncWorkflowToggles() {
  const rfp = $('actionRfpToggle');
  if (rfp) rfp.classList.toggle('on', state.pendingAction === 'rfp');
}

export function initWorkflowToggles({ renderScope }) {
  const rfp = $('actionRfpToggle');
  if (rfp) {
    rfp.onclick = () => {
      state.pendingAction = state.pendingAction === 'rfp' ? null : 'rfp';
      syncWorkflowToggles();
      renderScope();
      if (!state.messages.length && !state.busy) renderMessages();
    };
  }
  syncWorkflowToggles();
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
  const submit = () => {
    const v = composer.value;
    composer.value = '';
    sync();
    sendMessage(v);
  };

  composer.addEventListener('input', sync);
  composer.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!state.busy) submit();
    }
  });
  $('sendBtn').onclick = () => { if (state.busy) stopStreaming(); else submit(); };
  sync();
}
