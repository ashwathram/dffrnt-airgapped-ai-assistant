// Sidebar: collapse toggle, chat search, and the persisted conversation list
// (grouped by recency, with pin / rename / delete and a clear-all action).
// Selecting a conversation calls the onSelect callback wired by app.js.
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import {
  listConversations, updateConversation, deleteConversation, clearConversations,
} from './api.js';

let onSelect = () => {};
let search = '';
let menuOpenId = null;

function relTime(ts) {
  const secs = Date.now() / 1000 - ts;
  if (secs < 60) return 'just now';
  if (secs < 3600) return Math.floor(secs / 60) + 'm ago';
  if (secs < 86400) return Math.floor(secs / 3600) + 'h ago';
  const days = Math.floor(secs / 86400);
  if (days === 1) return 'yesterday';
  if (days < 7) return days + 'd ago';
  return new Date(ts * 1000).toLocaleDateString();
}

const GROUP_ORDER = ['Pinned', 'Today', 'Yesterday', 'Previous 7 days', 'Older'];

function groupOf(c) {
  if (c.pinned) return 'Pinned';
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = c.updated_at * 1000;
  if (t >= startToday) return 'Today';
  if (t >= startToday - 86400000) return 'Yesterday';
  if (t >= startToday - 7 * 86400000) return 'Previous 7 days';
  return 'Older';
}

// Re-render the list from the in-memory state.conversations (no fetch).
export function renderSidebar() {
  const box = $('chatHistory');
  const q = search.toLowerCase();
  const convos = state.conversations.filter((c) => c.title.toLowerCase().includes(q));
  if (!convos.length) {
    box.innerHTML = `<p class="hist-empty">${state.conversations.length ? 'No matches' : 'No conversations yet'}</p>`;
    return;
  }

  const groups = {};
  for (const c of convos) (groups[groupOf(c)] = groups[groupOf(c)] || []).push(c);

  let html = '';
  for (const g of GROUP_ORDER) {
    const items = groups[g];
    if (!items) continue;
    html += `<div class="hist-group"><div class="hist-glabel">${g === 'Pinned' ? '📌 ' : ''}${g}</div>`;
    for (const c of items) {
      const active = c.id === state.conversationId ? ' active' : '';
      html += `
        <div class="chat-item${active}">
          <button class="chat-open" data-open="${c.id}">
            ${svg('message')}
            <span class="ct"><span class="t">${esc(c.title)}</span><span class="s">${relTime(c.updated_at)}</span></span>
          </button>
          <button class="chat-more" data-more="${c.id}" title="More">${svg('more')}</button>
          ${menuOpenId === c.id ? `
            <div class="chat-menu">
              <button data-pin="${c.id}">${svg('pin')} ${c.pinned ? 'Unpin' : 'Pin'}</button>
              <button data-rename="${c.id}">${svg('pencil')} Rename</button>
              <button class="danger" data-del="${c.id}">${svg('trash')} Delete</button>
            </div>` : ''}
        </div>`;
    }
    html += '</div>';
  }
  box.innerHTML = html;

  box.querySelectorAll('[data-open]').forEach((b) => {
    b.onclick = () => { menuOpenId = null; onSelect(b.dataset.open); };
  });
  box.querySelectorAll('[data-more]').forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); menuOpenId = menuOpenId === b.dataset.more ? null : b.dataset.more; renderSidebar(); };
  });
  box.querySelectorAll('[data-pin]').forEach((b) => { b.onclick = () => togglePin(b.dataset.pin); });
  box.querySelectorAll('[data-rename]').forEach((b) => { b.onclick = () => rename(b.dataset.rename); });
  box.querySelectorAll('[data-del]').forEach((b) => { b.onclick = () => remove(b.dataset.del); });
}

// Fetch the list from the server, then render.
export async function loadConversations() {
  const { ok, data } = await listConversations();
  if (ok) state.conversations = data.conversations || [];
  renderSidebar();
}

async function togglePin(id) {
  const c = state.conversations.find((x) => x.id === id);
  menuOpenId = null;
  await updateConversation(id, { pinned: !(c && c.pinned) });
  loadConversations();
}

async function rename(id) {
  const c = state.conversations.find((x) => x.id === id);
  menuOpenId = null;
  const title = prompt('Rename conversation', c ? c.title : '');
  if (title && title.trim()) { await updateConversation(id, { title: title.trim() }); }
  loadConversations();
}

async function remove(id) {
  menuOpenId = null;
  if (!confirm('Delete this conversation? This cannot be undone.')) { renderSidebar(); return; }
  await deleteConversation(id);
  if (state.conversationId === id) onSelect(null); // clear the open chat
  loadConversations();
}

export function initSidebar(opts = {}) {
  onSelect = opts.onSelect || (() => {});

  const toggle = $('sidebarToggle');
  const applyCollapsed = () => {
    $('sidebar').classList.toggle('collapsed', state.collapsed);
    toggle.title = state.collapsed ? 'Expand sidebar' : 'Collapse sidebar';
  };
  toggle.onclick = () => { state.collapsed = !state.collapsed; applyCollapsed(); };
  applyCollapsed();
  $('chatSearch').oninput = (e) => { search = e.target.value; renderSidebar(); };
  $('clearHistoryBtn').onclick = async () => {
    if (!state.conversations.length) return;
    if (!confirm('Delete ALL saved conversations? This cannot be undone.')) return;
    await clearConversations();
    onSelect(null);
    loadConversations();
  };
  // Close any open row menu when clicking elsewhere.
  document.addEventListener('click', (e) => {
    if (menuOpenId && !e.target.closest('.chat-item')) { menuOpenId = null; renderSidebar(); }
  });

  loadConversations();
}
