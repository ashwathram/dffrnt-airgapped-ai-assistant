// Document library: a table of documents with their type, size, tags, and
// upload info. Supports tag-filtering, free-text search, inline tag/description
// editing, and per-row delete. Tags are stored on the document (as strings) and
// coloured by matching them to the taxonomy (loaded alongside the documents).
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import {
  listDocuments, deleteDocument, getTags, updateDocTags, updateDocDescription,
} from './api.js';

let docs = [];            // documents from the server (each has a `tags` array)
let activeFilter = [];    // tag names the list is filtered by (AND)
let searchQuery = '';     // free-text filter on name / description / uploader
let editing = null;       // { filename, selected:[...] } while editing a doc's tags
let editingDesc = null;   // { filename, value } while editing a doc's description
let menuOpen = null;      // filename whose row "⋯" menu is open

// A tag's colour comes from its taxonomy type; unknown tags get a neutral grey.
function colorFor(tagName) {
  const tag = state.tags.find((t) => t.name === tagName);
  const tt = tag && state.tagTypes.find((x) => x.id === tag.typeId);
  return tt ? tt.color : '#5a6a78';
}

// The taxonomy type name for a tag (e.g. "Department"), used as a faded prefix
// on document-row pills where tags from several types appear side by side.
function typeNameFor(tagName) {
  const tag = state.tags.find((t) => t.name === tagName);
  const tt = tag && state.tagTypes.find((x) => x.id === tag.typeId);
  return tt ? tt.name : '';
}

// Per-file-type accent + icon for the document badge (ported from the concept).
// Keyed on the lowercased extension; unknown types fall back to neutral grey.
const TYPE_COLORS = {
  pdf: '#E72300',
  docx: '#0369a1', doc: '#0369a1',
  xlsx: '#0a7c4a', xls: '#0a7c4a', csv: '#0a7c4a',
  pptx: '#C24A00', ppt: '#C24A00',
  txt: '#5a6a78', md: '#5a6a78',
};
const TYPE_ICONS = { pdf: 'fileText', docx: 'fileText', doc: 'fileText', txt: 'fileText', md: 'fileText' };
function typeMeta(d) {
  // The backend already exposes file_type as an upper-cased extension (e.g. "PDF").
  const label = (d.file_type || (d.filename.includes('.') ? d.filename.split('.').pop() : '')).toUpperCase();
  const key = label.toLowerCase();
  return { label: label || '—', color: TYPE_COLORS[key] || '#5a6a78', icon: TYPE_ICONS[key] || 'file' };
}

export async function loadDocuments() {
  const list = $('docList');
  list.innerHTML = '<p class="empty-docs">Loading…</p>';
  const [docRes, tagRes] = await Promise.all([listDocuments(), getTags()]);
  if (!docRes.ok) {
    list.innerHTML = '<p class="empty-docs" style="color:var(--destructive)">Could not load documents. Check the server connection.</p>';
    return;
  }
  docs = docRes.data.documents || [];
  state.documents = docs; // shared so the chat scope bar can count docs-in-scope
  if (tagRes.ok) { state.tagTypes = tagRes.data.tag_types || []; state.tags = tagRes.data.tags || []; }
  const n = docRes.data.document_count;
  $('libSubtitle').textContent =
    `${n} document${n === 1 ? '' : 's'} · Sorted by upload date, most recent first`;
  renderStorage(docRes.data.storage);
  // Drop filters that no longer exist in the taxonomy.
  activeFilter = activeFilter.filter((n) => state.tags.some((t) => t.name === n));
  render();
}

function render() { renderFilter(); renderList(); }

// -- AI Knowledge Storage bar ----------------------------------------------
function fmtBytes(n) {
  if (n == null) return '–';
  if (n < 1024) return n + ' B';
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return v.toFixed(v >= 100 || i === 0 ? 0 : 1) + ' ' + units[i];
}

// Binary (KiB/MiB) size a document occupies in the vector DB, e.g. "1.2KiB (stored)".
function fmtStored(n) {
  if (n == null) return '';
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let v = n, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  const num = i === 0 ? v : v.toFixed(v >= 100 ? 0 : 1);
  return `${num}${units[i]} (stored)`;
}

// Usage = vectors + chunk text + source files; cap = usage + free disk space.
// Bar turns amber past 80% and red past 90%.
function renderStorage(s) {
  const el = $('aiStorage');
  if (!s || !s.total_bytes) { el.innerHTML = ''; return; }
  const pct = Math.min(s.used_pct || 0, 100);
  const color = pct >= 90 ? 'var(--destructive)' : pct >= 80 ? '#D97706' : 'var(--primary)';
  const badge = pct >= 80
    ? `<span class="ais-badge" style="color:${color};background:${color}1a">${pct >= 90 ? 'Almost full' : 'Nearing limit'}</span>`
    : '';
  el.innerHTML = `
    <div class="ais-head">
      <div class="ais-title">${svg('database')} AI Knowledge Storage ${badge}</div>
      <div class="ais-nums">${fmtBytes(s.used_bytes)} <span class="ais-cap">/ ${fmtBytes(s.total_bytes)}</span></div>
    </div>
    <div class="ais-bar"><div class="ais-fill" style="width:${pct}%;background:${color}"></div></div>
    <div class="ais-note">Embedding vectors, chunk text and source files indexed by the assistant · ${pct.toFixed(1)}% of available space used</div>`;
}

// -- Filter bar ------------------------------------------------------------
function renderFilter() {
  const bar = $('docFilter');
  if (!state.tags.length) { bar.innerHTML = ''; return; }
  // Neutral grey, unlabeled chips (the concept reserves type colours for the
  // document-row tags; the filter is a plain pick-list).
  const GREY = '#5a6a78';
  bar.innerHTML = `
    ${state.tags.map((t) => {
      const on = activeFilter.includes(t.name);
      const style = on ? `background:${GREY};color:#fff;border-color:${GREY}` : `color:${GREY};border-color:${GREY}55`;
      return `<button class="df-chip${on ? ' on' : ''}" data-filter="${esc(t.name)}" style="${style}">${esc(t.name)}</button>`;
    }).join('')}
    ${activeFilter.length ? '<button class="df-clear" data-filter-clear>Clear</button>' : ''}`;
  bar.querySelectorAll('[data-filter]').forEach((b) => {
    b.onclick = () => {
      const n = b.dataset.filter;
      activeFilter = activeFilter.includes(n) ? activeFilter.filter((x) => x !== n) : [...activeFilter, n];
      render();
    };
  });
  const clear = bar.querySelector('[data-filter-clear]');
  if (clear) clear.onclick = () => { activeFilter = []; render(); };
}

// -- Document list ---------------------------------------------------------
function tagPills(d) {
  if (!d.tags || !d.tags.length) return '<span class="doc-notags">No tags</span>';
  return d.tags.map((t) => {
    const c = colorFor(t);
    const tn = typeNameFor(t);
    const prefix = tn ? `<span class="dt-type">${esc(tn)} ·</span> ` : '';
    return `<span class="doc-tag" style="background:${c}1a;color:${c};border-color:${c}40">${prefix}${esc(t)}</span>`;
  }).join('');
}

function editorHtml(d) {
  const groups = state.tagTypes.map((tt) => {
    const tags = state.tags.filter((t) => t.typeId === tt.id);
    if (!tags.length) return '';
    const chips = tags.map((t) => {
      const on = editing.selected.includes(t.name);
      const style = on ? `background:${tt.color};color:#fff;border-color:${tt.color}` : `color:${tt.color};border-color:${tt.color}55`;
      return `<button class="ed-chip${on ? ' on' : ''}" data-toggletag="${esc(t.name)}" style="${style}">${esc(t.name)}</button>`;
    }).join('');
    return `<div class="ed-group"><span class="ed-gname" style="color:${tt.color}">${esc(tt.name)}</span><div class="ed-chips">${chips}</div></div>`;
  }).join('');
  return `
    <div class="doc-editor">
      ${groups || '<span class="doc-notags">No tags defined yet — use Manage Tags to create some.</span>'}
      <div class="ed-actions">
        <button class="btn btn-sm btn-primary" data-savetags="${esc(d.filename)}">Save</button>
        <button class="btn btn-sm btn-ghost" data-canceltags>Cancel</button>
      </div>
    </div>`;
}

// Friendly upload date, e.g. "Jun 18, 2026", from the backend's "2026-06-18 …".
function fmtUploaded(s) {
  if (!s || s === 'Unknown') return 'Unknown';
  const datePart = s.split(' ')[0];
  const d = new Date(datePart + 'T00:00:00');
  return isNaN(d) ? datePart
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// Description cell: shows the text (or a muted placeholder) with a hover pencil,
// or an inline textarea + Save/Cancel while editing.
function descBlock(d) {
  if (editingDesc && editingDesc.filename === d.filename) {
    return `
      <div class="doc-desc-edit">
        <textarea class="doc-desc-input" rows="2" data-descinput placeholder="Describe this document's content or purpose…">${esc(editingDesc.value)}</textarea>
        <div class="ed-actions">
          <button class="btn btn-sm btn-primary" data-savedesc="${esc(d.filename)}">Save</button>
          <button class="btn btn-sm btn-ghost" data-canceldesc>Cancel</button>
        </div>
      </div>`;
  }
  const has = d.description && d.description.trim();
  return `
    <div class="doc-desc">
      ${has ? `<span class="dd-text">${esc(d.description)}</span>` : '<span class="dd-empty">No description</span>'}
      <button class="doc-editdesc" data-editdesc="${esc(d.filename)}" title="Edit description">${svg('pencil')}</button>
    </div>`;
}

function tagsCell(d) {
  const isEditing = editing && editing.filename === d.filename;
  return `
    <div class="tags-wrap">
      ${tagPills(d)}
      <button class="doc-edittags" data-edit="${esc(d.filename)}" title="Edit tags">${svg('pencil')}</button>
    </div>
    ${isEditing ? editorHtml(d) : ''}`;
}

function docRowHtml(d) {
  const m = typeMeta(d);
  const up = fmtUploaded(d.upload_date);
  return `
    <tr class="doc-row">
      <td class="c-doc">
        <div class="doc-name-cell">
          <div class="ficon" style="background:${m.color}1a;color:${m.color}">${svg(m.icon)}</div>
          <div class="doc-name-info">
            <a class="dn" href="/api/documents/${encodeURIComponent(d.filename)}/raw" target="_blank" rel="noopener" title="Open ${esc(d.filename)}">${esc(d.filename)}</a>
            ${descBlock(d)}
          </div>
        </div>
      </td>
      <td class="c-type"><span class="doc-type" style="background:${m.color}14;color:${m.color};border-color:${m.color}40">${esc(m.label)}</span></td>
      <td class="c-size">${esc(d.file_size)}</td>
      <td class="c-tags">${tagsCell(d)}</td>
      <td class="c-up">
        <div class="up-date">${esc(up)}</div>
        ${d.uploaded_by ? `<div class="up-by">${esc(d.uploaded_by)}</div>` : ''}
        <div class="up-stored">${esc(fmtStored(d.stored_bytes))}</div>
      </td>
      <td class="c-actions">
        <button class="doc-more" data-more="${esc(d.filename)}" title="More">${svg('more')}</button>
        ${menuOpen === d.filename ? `
          <div class="doc-menu">
            <button data-editdesc="${esc(d.filename)}">${svg('pencil')} Edit description</button>
            <button data-edit="${esc(d.filename)}">${svg('tag')} Edit tags</button>
            <button class="danger" data-del="${esc(d.filename)}">${svg('trash')} Delete</button>
          </div>` : ''}
      </td>
    </tr>`;
}

function renderList() {
  const list = $('docList');
  if (!docs.length) {
    list.innerHTML = '<p class="empty-docs">No documents ingested yet.<br>Use Upload to add files to the knowledge base.</p>';
    return;
  }
  const q = searchQuery.trim().toLowerCase();
  const shown = docs.filter((d) =>
    (!q
      || d.filename.toLowerCase().includes(q)
      || (d.description || '').toLowerCase().includes(q)
      || (d.uploaded_by || '').toLowerCase().includes(q))
    && activeFilter.every((t) => (d.tags || []).includes(t)));
  if (!shown.length) {
    list.innerHTML = '<p class="empty-docs">No documents match your search or filters.</p>';
    return;
  }
  list.innerHTML = `
    <table class="doc-table">
      <thead>
        <tr>
          <th class="c-doc">DOCUMENT</th>
          <th class="c-type">TYPE</th>
          <th class="c-size">RAW FILE SIZE</th>
          <th class="c-tags">TAGS</th>
          <th class="c-up">UPLOADED</th>
          <th class="c-actions"></th>
        </tr>
      </thead>
      <tbody>${shown.map(docRowHtml).join('')}</tbody>
    </table>`;

  list.querySelectorAll('[data-del]').forEach((b) => { b.onclick = () => onDelete(b.dataset.del); });
  list.querySelectorAll('[data-more]').forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      menuOpen = menuOpen === b.dataset.more ? null : b.dataset.more;
      render();
    };
  });
  // Tag editing — opening it closes any open description editor + menu.
  list.querySelectorAll('[data-edit]').forEach((b) => {
    b.onclick = () => {
      const d = docs.find((x) => x.filename === b.dataset.edit);
      editing = { filename: d.filename, selected: [...(d.tags || [])] };
      editingDesc = null; menuOpen = null;
      render();
    };
  });
  list.querySelectorAll('[data-toggletag]').forEach((b) => {
    b.onclick = () => {
      const n = b.dataset.toggletag;
      editing.selected = editing.selected.includes(n)
        ? editing.selected.filter((x) => x !== n) : [...editing.selected, n];
      render();
    };
  });
  list.querySelectorAll('[data-savetags]').forEach((b) => { b.onclick = () => saveTags(b.dataset.savetags); });
  list.querySelectorAll('[data-canceltags]').forEach((b) => { b.onclick = () => { editing = null; render(); }; });
  // Description editing.
  list.querySelectorAll('[data-editdesc]').forEach((b) => {
    b.onclick = () => {
      const d = docs.find((x) => x.filename === b.dataset.editdesc);
      editingDesc = { filename: d.filename, value: d.description || '' };
      editing = null; menuOpen = null;
      render();
      const ta = list.querySelector('[data-descinput]');
      if (ta) { ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
    };
  });
  list.querySelectorAll('[data-savedesc]').forEach((b) => { b.onclick = () => saveDesc(b.dataset.savedesc); });
  list.querySelectorAll('[data-canceldesc]').forEach((b) => { b.onclick = () => { editingDesc = null; render(); }; });
}

async function saveTags(filename) {
  const { ok, data } = await updateDocTags(filename, editing.selected);
  if (!ok) { alert('Failed to update tags: ' + (data.detail || 'Unknown error')); return; }
  editing = null;
  loadDocuments();
}

async function saveDesc(filename) {
  const ta = $('docList').querySelector('[data-descinput]');
  const value = ta ? ta.value : (editingDesc ? editingDesc.value : '');
  const { ok, data } = await updateDocDescription(filename, value);
  if (!ok) { alert('Failed to update description: ' + (data.detail || 'Unknown error')); return; }
  editingDesc = null;
  loadDocuments();
}

async function onDelete(filename) {
  if (!confirm(`Delete '${filename}' from the knowledge base?\nThis cannot be undone.`)) return;
  const { ok, data } = await deleteDocument(filename);
  if (ok) loadDocuments();
  else alert('Delete failed: ' + (data.detail || 'Unknown error'));
}

export function initLibrary() {
  $('docSearch').oninput = (e) => { searchQuery = e.target.value; renderList(); };
  // Close an open row menu when clicking elsewhere.
  document.addEventListener('click', (e) => {
    if (menuOpen && !e.target.closest('.c-actions')) { menuOpen = null; render(); }
  });
}
