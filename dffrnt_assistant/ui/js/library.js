// Document library: list documents with their tags, filter by tag, edit a
// document's tags, and delete. Tags are stored on the document (as strings) and
// coloured by matching them to the taxonomy (loaded alongside the documents).
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import { listDocuments, deleteDocument, getTags, updateDocTags } from './api.js';

let docs = [];            // documents from the server (each has a `tags` array)
let activeFilter = [];    // tag names the list is filtered by (AND)
let searchQuery = '';     // free-text filter on the filename
let editing = null;       // { filename, selected:[...] } while editing a doc's tags

// A tag's colour comes from its taxonomy type; unknown tags get a neutral grey.
function colorFor(tagName) {
  const tag = state.tags.find((t) => t.name === tagName);
  const tt = tag && state.tagTypes.find((x) => x.id === tag.typeId);
  return tt ? tt.color : '#5a6a78';
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
  $('statDocs').textContent = docRes.data.document_count;
  $('statChunks').textContent = docRes.data.total_chunks;
  // Drop filters that no longer exist in the taxonomy.
  activeFilter = activeFilter.filter((n) => state.tags.some((t) => t.name === n));
  render();
}

function render() { renderFilter(); renderList(); }

// -- Filter bar ------------------------------------------------------------
function renderFilter() {
  const bar = $('docFilter');
  if (!state.tags.length) { bar.innerHTML = ''; return; }
  bar.innerHTML = `
    <span class="df-label">${svg('tag')} Filter</span>
    ${state.tags.map((t) => {
      const on = activeFilter.includes(t.name);
      const c = colorFor(t.name);
      const style = on ? `background:${c};color:#fff;border-color:${c}` : `color:${c};border-color:${c}55`;
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
    return `<span class="doc-tag" style="background:${c}1a;color:${c};border-color:${c}40">${esc(t)}</span>`;
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

function docCardHtml(d) {
  const isEditing = editing && editing.filename === d.filename;
  return `
    <div class="doc-card">
      <div class="ficon">${svg('file')}</div>
      <div class="dinfo">
        <div class="dn">${esc(d.filename)}</div>
        <div class="dm">${esc(d.file_type)} · ${esc(d.file_size)} · ${d.chunk_count} chunks · ${esc(d.upload_date)}</div>
        <div class="doc-tags">
          ${tagPills(d)}
          <button class="doc-edittags" data-edit="${esc(d.filename)}" title="Edit tags">${svg('pencil')}</button>
        </div>
        ${isEditing ? editorHtml(d) : ''}
      </div>
      <button class="del" title="Delete" data-del="${esc(d.filename)}">${svg('trash')}</button>
    </div>`;
}

function renderList() {
  const list = $('docList');
  if (!docs.length) {
    list.innerHTML = '<p class="empty-docs">No documents ingested yet.<br>Use Upload to add files to the knowledge base.</p>';
    return;
  }
  const q = searchQuery.trim().toLowerCase();
  const shown = docs.filter((d) =>
    (!q || d.filename.toLowerCase().includes(q))
    && activeFilter.every((t) => (d.tags || []).includes(t)));
  if (!shown.length) {
    list.innerHTML = '<p class="empty-docs">No documents match your search or filters.</p>';
    return;
  }
  list.innerHTML = shown.map(docCardHtml).join('');

  list.querySelectorAll('[data-del]').forEach((b) => { b.onclick = () => onDelete(b.dataset.del); });
  list.querySelectorAll('[data-edit]').forEach((b) => {
    b.onclick = () => {
      const d = docs.find((x) => x.filename === b.dataset.edit);
      editing = { filename: d.filename, selected: [...(d.tags || [])] };
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
}

async function saveTags(filename) {
  const { ok, data } = await updateDocTags(filename, editing.selected);
  if (!ok) { alert('Failed to update tags: ' + (data.detail || 'Unknown error')); return; }
  editing = null;
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
}
