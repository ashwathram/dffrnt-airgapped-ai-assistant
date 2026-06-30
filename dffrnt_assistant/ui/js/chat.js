// Chat view: empty state, message rendering, sending, and the composer.
import { $, esc, nowTime } from './util.js';
import { svg } from './icons.js';
import { state, SUGGESTIONS } from './state.js';
import { renderMarkdown } from './markdown.js';
import {
  queryStream, createConversation, updateConversation, getConversation, listDocuments,
} from './api.js';
import { loadConversations, renderSidebar } from './sidebar.js';

let nextId = 0;
const mkId = () => 'm' + (++nextId);  // stable per-message id for actions/targeting
let abortController = null;           // in-flight stream, so the Stop button can cancel it

function composerPlaceholder() {
  return state.resumeMode
    ? 'Ask to tailor the selected resume to the selected uploaded RFP…'
    : 'Ask anything about your documents…';
}

function provenanceLabel(meta = {}) {
  if (meta.source_mode === 'documents' && meta.mode === 'resume') return 'Tailored only from selected uploaded files';
  if (meta.source_mode === 'documents') return 'Tailored only from uploaded files';
  if (meta.source_mode === 'mixed') return 'Tailored from uploaded files';
  return 'Needs uploaded RFP and resume files';
}

function docsByKind(kind) {
  const needle = kind.toLowerCase();
  return (state.documents || []).filter((d) => {
    const tags = (d.tags || []).map((tag) => tag.toLowerCase());
    const haystack = [d.filename, d.description || ''].join(' ').toLowerCase();
    return tags.includes(needle) || haystack.includes(needle);
  });
}

function syncSelectedFile(key, options) {
  const current = state[key];
  if (current && options.some((doc) => doc.filename === current)) return;
  state[key] = options.length === 1 ? options[0].filename : '';
}

function renderRfpSelectors() {
  const wrap = $('rfpSelectors');
  const resumeSelect = $('resumeSelect');
  const rfpSelect = $('rfpSelect');
  if (!wrap || !resumeSelect || !rfpSelect) return;

  const resumeDocs = docsByKind('resume');
  const rfpDocs = docsByKind('rfp');
  syncSelectedFile('selectedResumeFilename', resumeDocs);
  syncSelectedFile('selectedRfpFilename', rfpDocs);

  wrap.classList.toggle('hidden', !state.resumeMode);
  resumeSelect.innerHTML = '<option value="">Select resume</option>'
    + resumeDocs.map((d) => `<option value="${esc(d.filename)}">${esc(d.filename)}</option>`).join('');
  rfpSelect.innerHTML = '<option value="">Select RFP</option>'
    + rfpDocs.map((d) => `<option value="${esc(d.filename)}">${esc(d.filename)}</option>`).join('');
  resumeSelect.value = state.selectedResumeFilename || '';
  rfpSelect.value = state.selectedRfpFilename || '';
  resumeSelect.disabled = !state.resumeMode;
  rfpSelect.disabled = !state.resumeMode;
}

// Turn "[1]" markers into clickable citation chips mapped to sources by index.
// data-msg/data-cite let a click scroll to and highlight the matching source
// card (see focusSource). Operates on already-escaped text so it can be reused
// as the Markdown inline hook (it then only ever sees non-code text, leaving
// code spans untouched).
function citeChips(sources, msgId) {
  return (escaped) => escaped.replace(/\[(\d+)\]/g, (m, n) => {
    const i = parseInt(n, 10);
    if (sources && i >= 1 && i <= sources.length) {
      return `<span class="cite-chip" data-msg="${msgId}" data-cite="${i}" title="${esc(sources[i - 1].filename)}">${i}</span>`;
    }
    return m;
  });
}

// User turns: plain escaped text + citation chips (no Markdown).
function renderContent(text, sources, msgId) {
  return citeChips(sources, msgId)(esc(text));
}

// Assistant answers: render Markdown to safe HTML, with citation chips applied
// to the plain-text runs. .md scopes the styling and resets the bubble's
// pre-wrap (see styles/markdown.css).
function renderAnswer(text, sources, msgId) {
  return `<div class="md">${renderMarkdown(text, { inline: citeChips(sources, msgId) })}</div>`;
}

function provenanceHtml(m) {
  if (!m.meta || m.meta.mode !== 'resume') return '';
  return `<div class="provenance"><span class="prov-chip">${esc(provenanceLabel(m.meta))}</span></div>`;
}

// Sources panel — the answer's [n] markers tell us which sources were actually
// cited. Those lead; the rest (retrieved but unused) collapse into a dimmed
// "other retrieved sources" group so they stay auditable without crowding out
// the ones the answer relied on.
function sourcesHtml(m) {
  const sources = m.sources || [];
  if (!sources.length) return '';

  // Collect the valid citation numbers present in the final answer text.
  const cited = new Set();
  (m.content || '').replace(/\[(\d+)\]/g, (_, n) => {
    const i = parseInt(n, 10);
    if (i >= 1 && i <= sources.length) cited.add(i);
    return '';
  });

  // Each source keeps its original 1-based number, so the answer's [n] still
  // maps to badge n and the click-to-flash linkage holds; we only regroup them.
  // Title (section heading or filename stem) headlines the card; the filename,
  // page and score sit in the meta line, with a short excerpt of the cited chunk.
  const row = (s, n) => `
    <a class="source" id="src-${m.id}-${n}" href="/api/documents/${encodeURIComponent(s.filename)}/raw" target="_blank" rel="noopener" title="Open ${esc(s.filename)}">
      <span class="num">${n}</span>
      <span class="body">
        <span class="fn">${esc(s.title || s.filename)}</span>
        <span class="meta">${esc(s.filename)}${s.page ? ' · p. ' + esc(s.page) : ''}${s.score != null ? ' · score ' + s.score : ''}</span>
        ${s.excerpt ? `<span class="excerpt">“${esc(s.excerpt)}”</span>` : ''}
      </span>
      ${svg('externalLink')}
    </a>`;

  // Pair sources with their number, then split by whether the answer cited them.
  // If nothing was cited (model omitted markers), show everything as primary so
  // we never hide the whole list.
  const numbered = sources.map((s, idx) => [s, idx + 1]);
  const anyCited = numbered.some(([, n]) => cited.has(n));
  const primary = anyCited ? numbered.filter(([, n]) => cited.has(n)) : numbered;
  const secondary = anyCited ? numbered.filter(([, n]) => !cited.has(n)) : [];

  const n2 = secondary.length;
  const secondaryHtml = n2
    ? `<button class="src-toggle" data-srctoggle="${m.id}">${m.sourcesExpanded ? 'Hide' : 'Show'} ${n2} other retrieved source${n2 > 1 ? 's' : ''}</button>`
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
      <div class="suggestions">
        ${SUGGESTIONS.map((s, i) => `<button class="suggestion" data-suggest="${i}">${svg(s.icon)}${esc(s.text)}</button>`).join('')}
      </div>
    </div>`;
}

// Stylized, collapsible reasoning block — shown when "Show thinking" is on.
// Open while streaming so the user can watch it think; collapsed once done.
// The model streams free-form text; we render it as a bulleted "reasoning
// trace" by splitting on newlines, highlighting the line currently streaming.
function thinkingBlockHtml(m) {
  const openAttr = m.streaming ? ' open' : '';
  const label = m.streaming ? 'Thinking…' : 'Thought process';
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
    html += renderAnswer(m.content, m.sources, m.id);
    if (m.streaming) html += '<span class="stream-cursor"></span>';
  }
  if (!m.streaming) {
    html += provenanceHtml(m);
    html += sourcesHtml(m);
  }
  return html;
}

function renderRfpModeToggle() {
  const btn = $('rfpModeToggle');
  const txt = $('rfpModeText');
  if (!btn || !txt) return;
  txt.textContent = state.resumeMode ? 'Tailor resume to RFP mode' : 'Not tailored to RFP mode';
  btn.classList.toggle('on', state.resumeMode);
}

function syncComposerModeUi() {
  const composer = $('composer');
  if (composer) composer.placeholder = composerPlaceholder();
  renderRfpModeToggle();
  renderRfpSelectors();
}

function setResumeMode(on) {
  state.resumeMode = !!on;
  state.resumeGroundingPreference = 'documents';
  syncComposerModeUi();
}

function setGroundingPreference(value) {
  state.resumeGroundingPreference = 'documents';
  syncComposerModeUi();
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
        <div class="bubble"${bubbleId}>${isUser ? renderContent(m.content, m.sources, m.id) : bubbleInner(m)}</div>
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
  syncComposerModeUi();
}

// Clicking a "[n]" citation chip scrolls to its source card and flashes it.
// Cited sources lead the panel, so the card is normally already visible; if it
// happens to sit in the collapsed "other retrieved sources" group, expand that
// first (which re-renders, so we look the card up afterwards).
function focusSource(msgId, n) {
  const m = state.messages.find((x) => x.id === msgId);
  if (!m || !m.sources || n < 1 || n > m.sources.length) return;
  if (!document.getElementById(`src-${msgId}-${n}`) && !m.sourcesExpanded) {
    m.sourcesExpanded = true;
    renderMessages();
  }
  const card = document.getElementById(`src-${msgId}-${n}`);
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  card.classList.remove('flash');
  void card.offsetWidth; // restart the animation if the same card is re-clicked
  card.classList.add('flash');
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
  // The conversation title is its first user turn (mirrors persist() below), so
  // the top bar shows that rather than a generic label.
  $('topbarTitle').textContent = (state.messages.find((m) => m.role === 'user') || {}).content || 'Conversation';
  await runQuery();
}

// Persist the current conversation to the server (create on first turn, then
// update). Only real turns are stored — thinking and UI flags are dropped.
async function persist() {
  const msgs = state.messages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({
      role: m.role,
      content: m.content,
      sources: m.sources || [],
      ts: m.ts || '',
    }));
  if (!msgs.length) return;
  if (!state.conversationId) {
    const title = (state.messages.find((m) => m.role === 'user') || {}).content || 'New conversation';
    const { ok, data } = await createConversation({
      title: title.slice(0, 80),
      messages: msgs,
      mode: state.resumeMode ? 'resume' : 'default',
      grounding_preference: state.resumeGroundingPreference,
      selected_resume_filename: state.selectedResumeFilename,
      selected_rfp_filename: state.selectedRfpFilename,
    });
    if (ok) state.conversationId = data.id;
  } else {
    await updateConversation(state.conversationId, {
      messages: msgs,
      mode: state.resumeMode ? 'resume' : 'default',
      grounding_preference: state.resumeGroundingPreference,
      selected_resume_filename: state.selectedResumeFilename,
      selected_rfp_filename: state.selectedRfpFilename,
    });
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
  state.resumeMode = (data.mode || 'default') === 'resume';
  state.resumeGroundingPreference = 'documents';
  state.selectedResumeFilename = data.selected_resume_filename || '';
  state.selectedRfpFilename = data.selected_rfp_filename || '';
  state.messages = (data.messages || []).map((m) => ({
    id: mkId(),
    role: m.role,
    content: m.content,
    sources: m.sources || [],
    ts: m.ts || '',
    feedback: null,
  }));
  renderMessages();
  refreshSendBtn();
  renderSidebar();
  $('topbarTitle').textContent = data.title || 'Conversation';
  syncComposerModeUi();
}

// Answer the most recent user turn. Used for both a fresh send and Regenerate,
// so neither needs to re-add the user message.
async function runQuery() {
  const turns = state.messages.filter((m) => m.role === 'user' || m.role === 'assistant');
  const last = turns[turns.length - 1];
  if (!last || last.role !== 'user') return;
  const question = last.content;
  const history = turns.slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
  if (state.resumeMode && (!state.selectedResumeFilename || !state.selectedRfpFilename)) {
    state.messages.push({
      id: mkId(),
      role: 'notice',
      content: 'Select one uploaded resume and one uploaded RFP before using RFP tailoring mode.',
    });
    renderMessages();
    return;
  }

  state.busy = true; // guard concurrent sends + show the typing indicator + Stop button
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
    meta: null,
  };
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
    for await (const ev of queryStream(
      question,
      history,
      abortController.signal,
      state.chatScope,
      state.resumeMode ? 'resume' : 'default',
      state.resumeGroundingPreference,
      state.selectedResumeFilename,
      state.selectedRfpFilename,
    )) {
      if (ev.type === 'meta') {
        assistant.meta = ev.meta || null;
      } else if (ev.type === 'sources') {
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
  state.resumeMode = false;
  state.resumeGroundingPreference = 'documents';
  state.selectedResumeFilename = '';
  state.selectedRfpFilename = '';
  renderMessages();
  renderSidebar();
  refreshSendBtn();
  $('topbarTitle').textContent = 'New conversation';
  syncComposerModeUi();
}

export function initComposer() {
  const composer = $('composer');
  const rfpToggle = $('rfpModeToggle');
  const resumeSelect = $('resumeSelect');
  const rfpSelect = $('rfpSelect');
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
  rfpToggle.onclick = () => setResumeMode(!state.resumeMode);
  resumeSelect.onchange = () => {
    state.selectedResumeFilename = resumeSelect.value || '';
    persist();
  };
  rfpSelect.onchange = () => {
    state.selectedRfpFilename = rfpSelect.value || '';
    persist();
  };
  $('sendBtn').onclick = () => { if (state.busy) stopStreaming(); else submit(); };
  syncComposerModeUi();
  sync();
}

export async function refreshChatDocuments() {
  const { ok, data } = await listDocuments();
  if (!ok) return;
  state.documents = data.documents || [];
  renderRfpSelectors();
}
