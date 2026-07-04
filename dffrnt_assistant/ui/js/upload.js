// Upload modal: a queue with client-side validation, per-file (or per-folder)
// taxonomy tags + description, sequential upload with a progress bar, and a
// separate ingestion-summary screen. Duplicates are detected server-side by
// SHA-256 (same name, or same content under a different name) and resolved
// inline with Replace / Keep both / Remove file. Tags are grouped by type in
// collapsible sections and a new tag can be created inline. Wired to /api/upload
// (+ DELETE for Replace). Folder uploads share tags/description across files.
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import { getTags, uploadFileStream, deleteDocument, addTag } from './api.js';
import { loadDocuments } from './library.js';

const SUPPORTED = ['pdf', 'docx', 'pptx', 'xlsx', 'csv', 'txt', 'md']; // matches backend
const MAX_MB = 50;
const MAX_BYTES = MAX_MB * 1024 * 1024;

// entries: {id, file, name, size, tags:[], desc, folder?, status, error?,
//           chunks?, warning?, dupKind?, dupExisting?, replaced?, result?}
let entries = [];
let folders = {};        // folderName -> { desc, tags:[], expanded }
let uid = 0;
let newTagFor = null;        // scope key of the section whose "create tag" form is open
let tagGroupsCollapsed = {}; // tagType id -> true when its chip group is collapsed
let uploading = false;   // a batch is in flight (drives the progress bar)
let attempted = false;   // a batch has run (drives the ingestion summary)
let progress = { done: 0, total: 0 };
let stageProg = { pct: 0, text: '' };  // live per-file stage (transfer → embed → store)

function fmtSize(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

// ISO timestamp -> "2 Jul 2026 · 10:17 PM" (matches the summary mockup).
function fmtDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const date = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  return `${date} · ${time}`;
}

function validate(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (!SUPPORTED.includes(ext)) return `Unsupported file type (.${ext || '?'}). Accepted: ${SUPPORTED.join(', ').toUpperCase()}`;
  if (file.size === 0) return 'File is empty';
  if (file.size > MAX_BYTES) return `Exceeds ${MAX_MB} MB (${fmtSize(file.size)})`;
  return null;
}

// The tag type's colour / name for a tag, used on summary pills.
function tagColor(name) {
  const tag = state.tags.find((t) => t.name === name);
  const tt = tag && state.tagTypes.find((x) => x.id === tag.typeId);
  return tt ? tt.color : '#5a6a78';
}
function tagTypeName(name) {
  const tag = state.tags.find((t) => t.name === name);
  const tt = tag && state.tagTypes.find((x) => x.id === tag.typeId);
  return tt ? tt.name : '';
}

// Queue files, inheriting a folder's shared tags/description when given.
function addFiles(fileList, folderName) {
  const fdef = folderName ? folders[folderName] : null;
  for (const file of Array.from(fileList)) {
    const error = validate(file);
    entries.push({
      id: 'u' + (++uid), file, name: file.name, size: file.size,
      tags: fdef ? [...fdef.tags] : [], desc: fdef ? fdef.desc : '',
      folder: folderName || undefined,
      status: error ? 'invalid' : 'pending', error,
    });
  }
  render();
}

function addFolder(fileList) {
  const files = Array.from(fileList);
  if (!files.length) return;
  const folderName = (files[0].webkitRelativePath || files[0].name).split('/')[0] || 'Folder';
  if (!folders[folderName]) folders[folderName] = { desc: '', tags: [], expanded: true };
  addFiles(files, folderName);
}

function removeEntry(id) {
  const e = entries.find((x) => x.id === id);
  entries = entries.filter((x) => x.id !== id);
  if (e && e.folder && !entries.some((x) => x.folder === e.folder)) delete folders[e.folder];
  render();
}

// Propagate a folder's shared tags / description to all its queued files.
function setFolderTag(folderName, tagName) {
  const f = folders[folderName];
  if (!f) return;
  f.tags = f.tags.includes(tagName) ? f.tags.filter((x) => x !== tagName) : [...f.tags, tagName];
  entries.forEach((e) => { if (e.folder === folderName && e.status === 'pending') e.tags = [...f.tags]; });
  render();
}
function setFolderDesc(folderName, value) {
  const f = folders[folderName];
  if (!f) return;
  f.desc = value;
  entries.forEach((e) => { if (e.folder === folderName && e.status === 'pending') e.desc = value; });
  // no render: keep the textarea focused while typing
}

function statusHtml(e) {
  if (e.status === 'done') return `<span class="up-status done">✓ ${e.chunks} chunks${e.replaced ? ' (replaced)' : ''}</span>`;
  if (e.status === 'error') return `<span class="up-status err">✗ ${esc(e.error || 'Failed')}</span>`;
  if (e.status === 'dup') return '<span class="up-status dup">⚠ Duplicate</span>';
  if (e.status === 'uploading') return '<span class="up-status">Uploading…</span>';
  if (e.status === 'invalid') return '<span class="up-status err">Invalid</span>';
  return '';
}

// A × that removes a queued / invalid / duplicate file from the list.
function removeBtn(e) {
  return (e.status === 'pending' || e.status === 'invalid' || e.status === 'dup')
    ? `<button class="up-remove" data-up="remove" data-id="${e.id}" title="Remove">${svg('x')}</button>` : '';
}

// Optional per-file description (standalone files only; folder files share one).
function descField(e) {
  if (e.status !== 'pending') return '';
  return `
    <div class="up-desc">
      <label>Description <span class="up-opt">(optional)</span></label>
      <textarea class="up-desc-input" rows="2" data-up="desc" data-id="${e.id}" placeholder="Brief description of this document's content or purpose…">${esc(e.desc || '')}</textarea>
    </div>`;
}

// Grouped, collapsible tag section: chips grouped by tag type, plus an inline
// "Create custom tag" control. `scope` carries the data attributes that tie a
// chip back to a file (data-up="tag") or folder (data-up="folder-tag");
// `scopeKey` is a stable id so only this section's create-tag form opens.
function tagSection(selected, scope, scopeKey) {
  if (!state.tagTypes.length) return newTagControl(scopeKey);
  const groups = state.tagTypes.map((tt) => {
    const tags = state.tags.filter((t) => t.typeId === tt.id);
    if (!tags.length) return '';
    const collapsed = !!tagGroupsCollapsed[tt.id];
    const chips = tags.map((t) => {
      const on = selected.includes(t.name);
      const style = on ? `background:${tt.color};color:#fff;border-color:${tt.color}` : `color:${tt.color};border-color:${tt.color}55`;
      return `<button class="up-tag${on ? ' on' : ''}" data-up="${scope.kind}" ${scope.attr} data-tag="${esc(t.name)}" style="${style}">${esc(t.name)}</button>`;
    }).join('');
    return `
      <div class="up-tgroup">
        <button class="up-tgname" data-up="tgroup" data-type="${esc(tt.id)}">
          <span class="up-tgdot" style="background:${tt.color}"></span>
          <span style="color:${tt.color}">${esc(tt.name)}</span>
          ${svg(collapsed ? 'chevronRight' : 'chevronDown')}
        </button>
        ${collapsed ? '' : `<div class="up-tags">${chips}</div>`}
      </div>`;
  }).join('');
  return `<div class="up-tagsec"><label class="up-tagsec-label">Tags <span class="up-opt">(applied to all files)</span></label>${groups}${newTagControl(scopeKey)}</div>`;
}

// Inline "create a custom tag" control — adds to the taxonomy so it becomes a
// selectable chip in every section.
function newTagControl(scopeKey) {
  if (!state.tagTypes.length) return ''; // a tag needs a type; manage those in Tag Manager
  if (newTagFor !== scopeKey) {
    return `<button class="up-newtag-btn" data-up="newtag-open" data-scope="${esc(scopeKey)}">${svg('plus')} Create custom tag</button>`;
  }
  const opts = state.tagTypes.map((tt) => `<option value="${tt.id}">${esc(tt.name)}</option>`).join('');
  return `
    <div class="up-newtag">
      <input id="upNewTagName" class="tt-input" placeholder="Tag name…" />
      <select id="upNewTagType" class="tt-input">${opts}</select>
      <button class="btn btn-sm btn-primary" data-up="newtag-create">Add</button>
      <button class="btn btn-sm btn-ghost" data-up="newtag-cancel">Cancel</button>
    </div>`;
}

function dupActions(e) {
  if (e.status !== 'dup') return '';
  return `
    <div class="up-dup">
      <span class="up-dupmsg">${esc(e.warning || 'Already in the knowledge base.')}</span>
      <div class="up-dupbtns">
        <button class="btn btn-sm btn-primary" data-up="replace" data-id="${e.id}">Replace</button>
        <button class="btn btn-sm" data-up="copy" data-id="${e.id}">Keep both</button>
        <button class="btn btn-sm btn-ghost" data-up="remove" data-id="${e.id}">Remove file</button>
      </div>
    </div>`;
}

// Standalone (non-folder) file row: own description + tags.
function entryHtml(e) {
  return `
    <div class="up-row">
      <div class="up-rowtop">
        <span class="up-file">${svg('file')}<span class="up-name">${esc(e.name)}</span><span class="up-size">${fmtSize(e.size)}</span></span>
        ${statusHtml(e)}${removeBtn(e)}
      </div>
      ${e.error && e.status === 'invalid' ? `<div class="up-err">${esc(e.error)}</div>` : descField(e) + tagSection(e.tags, { kind: 'tag', attr: `data-id="${e.id}"` }, `tag-${e.id}`)}
      ${dupActions(e)}
    </div>`;
}

// Folder file row: compact (tags/description come from the folder group).
function folderFileRow(e) {
  return `
    <div class="up-frow">
      <span class="up-file">${svg('file')}<span class="up-name">${esc(e.name)}</span><span class="up-size">${fmtSize(e.size)}</span></span>
      ${statusHtml(e)}${removeBtn(e)}
      ${e.error && e.status === 'invalid' ? `<div class="up-err">${esc(e.error)}</div>` : ''}
      ${dupActions(e)}
    </div>`;
}

function folderGroupHtml(fn) {
  const f = folders[fn];
  const members = entries.filter((e) => e.folder === fn);
  const hasPending = members.some((e) => e.status === 'pending');
  return `
    <div class="up-folder">
      <button class="up-folder-head" data-up="folder-toggle" data-folder="${esc(fn)}">
        ${svg('folder')}
        <span class="uf-name">${esc(fn)}</span>
        <span class="uf-count">${members.length} file${members.length === 1 ? '' : 's'}${hasPending ? ' · Tags applied to all files' : ''}</span>
        <span class="scope-spacer"></span>
        ${svg(f.expanded ? 'chevronUp' : 'chevronDown')}
      </button>
      ${f.expanded ? `
        <div class="up-folder-body">
          ${hasPending ? `
            <div class="up-desc">
              <label>Description <span class="up-opt">(applied to all files)</span></label>
              <textarea class="up-desc-input" rows="2" data-up="folder-desc" data-folder="${esc(fn)}" placeholder="Brief description of this folder's content…">${esc(f.desc)}</textarea>
            </div>
            ${tagSection(f.tags, { kind: 'folder-tag', attr: `data-folder="${esc(fn)}"` }, `folder-${fn}`)}
          ` : ''}
          <div class="up-files-title">Files in folder</div>
          <div class="up-folder-files">${members.map(folderFileRow).join('')}</div>
        </div>` : ''}
    </div>`;
}

// Red banner listing files that cannot be uploaded (unsupported / too large).
function invalidBannerHtml() {
  const bad = entries.filter((e) => e.status === 'invalid');
  if (!bad.length) return '';
  return `
    <div class="up-banner">
      <div class="up-banner-head">${svg('alert')} ${bad.length} file${bad.length === 1 ? '' : 's'} cannot be uploaded</div>
      ${bad.map((e) => `<div class="up-banner-item"><span class="up-name">${esc(e.name)}</span> — ${esc(e.error || 'Unsupported file')}</div>`).join('')}
    </div>`;
}

// Map a streamed stage event to an overall percentage + label. The weighting
// gives the slow (embedding) stage most of the bar so it moves realistically:
// transfer 0–20 %, parse/chunk 20–35 %, embedding 35–90 %, storing → 100 %.
function stageInfo(ev) {
  switch (ev.stage) {
    case 'transfer': {
      const p = ev.total ? ev.loaded / ev.total : 0;
      return { pct: 20 * p, text: `Transferring ${Math.round(p * 100)}%` };
    }
    case 'received': return { pct: 22, text: 'Uploaded — preparing…' };
    case 'parsing': return { pct: 26, text: 'Reading document…' };
    case 'chunking': return { pct: 32, text: 'Splitting into chunks…' };
    case 'embedding': {
      const p = ev.total ? ev.done / ev.total : 0;
      return { pct: 35 + 55 * p, text: `Embedding ${ev.done}/${ev.total} chunks…` };
    }
    case 'storing': return { pct: 95, text: 'Indexing…' };
    default: return null;
  }
}

// Live update: recompute the bar and patch the DOM in place (no full re-render,
// so frequent transfer/embedding events stay cheap).
function onStageEvent(ev) {
  const info = stageInfo(ev);
  if (!info) return;
  stageProg = info;
  const fill = document.getElementById('upProgFill');
  const txt = document.getElementById('upProgText');
  const pctEl = document.getElementById('upProgPct');
  if (fill) fill.style.width = info.pct + '%';
  if (txt) txt.textContent = info.text;
  if (pctEl) pctEl.textContent = Math.round(info.pct) + '%';
}

function progressHtml() {
  if (!uploading) return '';
  const cur = entries.find((e) => e.status === 'uploading');
  const name = cur ? cur.name : '';
  const batch = progress.total > 1 ? ` · file ${Math.min(progress.done + 1, progress.total)} of ${progress.total}` : '';
  return `
    <div class="up-progress">
      <div class="up-progress-top"><span id="upProgText">${esc(stageProg.text || 'Uploading…')}</span><span id="upProgPct">${Math.round(stageProg.pct)}%</span></div>
      <div class="up-progress-bar"><div class="up-progress-fill" id="upProgFill" style="width:${stageProg.pct}%"></div></div>
      <div class="up-progress-sub">${esc(name)}${batch}</div>
    </div>`;
}

// -- Ingestion summary (separate screen shown once a batch fully resolves) ----
function summaryReady() {
  return attempted && !uploading
    && !entries.some((e) => e.status === 'pending' || e.status === 'dup' || e.status === 'uploading');
}

function summaryTagsHtml(tags) {
  if (!tags || !tags.length) return '';
  const pills = tags.map((t) => {
    const c = tagColor(t);
    const tn = tagTypeName(t);
    const prefix = tn ? `<span class="dt-type">${esc(tn)} ·</span> ` : '';
    return `<span class="doc-tag" style="background:${c}1a;color:${c};border-color:${c}40">${prefix}${esc(t)}</span>`;
  }).join('');
  return `<div class="up-card-row"><span class="up-card-k">TAGS</span><span class="up-card-v"><span class="up-card-tags">${pills}</span></span></div>`;
}

function summaryCardHtml(e) {
  const ok = e.status === 'done';
  const r = e.result || {};
  const type = r.file_type || (e.name.includes('.') ? e.name.split('.').pop().toUpperCase() : '—');
  const tags = ok ? (r.tags && r.tags.length ? r.tags : e.tags) : e.tags;
  const row = (k, v) => v ? `<div class="up-card-row"><span class="up-card-k">${k}</span><span class="up-card-v">${v}</span></div>` : '';
  const statusLine = ok
    ? `<div class="up-card-status ok">${svg('checkCircle')} Ingested successfully</div>`
    : `<div class="up-card-status err">${svg('alert')} Failed: ${esc(e.error || 'Upload failed')}</div>`;
  return `
    <div class="up-card ${ok ? 'ok' : 'err'}">
      ${statusLine}
      ${row('FILE NAME', esc(e.name))}
      ${row('SIZE', esc(r.file_size || fmtSize(e.size)))}
      ${row('TYPE', esc(type))}
      ${ok ? row('UPLOADED', esc(fmtDateTime(r.upload_date))) : ''}
      ${e.folder ? row('FOLDER', `${svg('folder')} ${esc(e.folder)}`) : ''}
      ${summaryTagsHtml(tags)}
    </div>`;
}

function summaryViewHtml() {
  const okCount = entries.filter((e) => e.status === 'done').length;
  const failed = entries.filter((e) => e.status === 'error' || e.status === 'invalid').length;
  const header = failed ? 'Upload finished with errors' : 'Upload complete';
  return `
    <div class="up-summaryview">
      <div class="up-sv-head ${failed ? 'has-err' : ''}">
        ${svg(failed ? 'alert' : 'checkCircle')}
        <div class="up-sv-htext"><strong>${header}</strong><span>${okCount} successful${failed ? ` · ${failed} failed` : ''}</span></div>
      </div>
      <div class="up-sv-label">INGESTION SUMMARY · ${entries.length} FILE${entries.length === 1 ? '' : 'S'}</div>
      ${entries.map(summaryCardHtml).join('')}
    </div>`;
}

function render() {
  if (summaryReady()) {
    $('uploadModalBody').innerHTML = summaryViewHtml();
    refreshFoot();
    return;
  }
  const folderNames = Object.keys(folders).filter((fn) => entries.some((e) => e.folder === fn));
  const standalone = entries.filter((e) => !e.folder);
  $('uploadModalBody').innerHTML = `
    <div class="dropzone" id="upDrop">
      ${svg('upload')}
      <strong>Drop files or folders here</strong>
      <span>PDF, DOCX, PPTX, XLSX, CSV, TXT, MD · Max ${MAX_MB} MB per file</span>
      <div class="dz-btns">
        <button class="dz-btn dz-btn-files" data-up="browse-files">${svg('file')} Browse files</button>
        <button class="dz-btn dz-btn-folder" data-up="browse-folder">${svg('folder')} Browse folder</button>
      </div>
      <input type="file" id="upInput" multiple hidden />
      <input type="file" id="upFolderInput" hidden webkitdirectory directory />
    </div>
    ${progressHtml()}
    ${invalidBannerHtml()}
    ${folderNames.map(folderGroupHtml).join('')}
    ${standalone.length ? `<div class="up-queue">${standalone.map(entryHtml).join('')}</div>` : ''}`;

  const drop = $('upDrop');
  drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add('drag'); };
  drop.ondragleave = () => drop.classList.remove('drag');
  drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove('drag'); addFiles(ev.dataTransfer.files); };
  // Clicking the zone itself acts like "Browse files"; clicks on the browse
  // buttons are handled separately (guard against double-opening the dialog).
  drop.onclick = (ev) => { if (!ev.target.closest('[data-up]')) $('upInput').click(); };
  refreshFoot();
}

function refreshFoot() {
  const cancelBtn = $('uploadCloseBtn');
  const startBtn = $('uploadStartBtn');
  if (summaryReady()) {
    cancelBtn.classList.add('hidden');
    startBtn.disabled = false;
    startBtn.textContent = 'Done';
    $('upSummary').textContent = '';
    return;
  }
  cancelBtn.classList.remove('hidden');
  const pending = entries.filter((e) => e.status === 'pending').length;
  const done = entries.filter((e) => e.status === 'done').length;
  startBtn.disabled = uploading || pending === 0;
  startBtn.textContent = pending ? `Upload ${pending} file${pending === 1 ? '' : 's'}` : 'Upload';
  $('upSummary').textContent = done ? `${done} uploaded` : '';
}

// -- Uploading -------------------------------------------------------------
async function send(e) {
  e.status = 'uploading'; stageProg = { pct: 0, text: 'Starting…' }; render();
  const { ok, data } = await uploadFileStream(e.file, e.tags.join(','), e.desc, false, onStageEvent);
  if (data.duplicate) {
    e.status = 'dup'; e.warning = data.warning; e.dupKind = data.kind; e.dupExisting = data.existing;
  } else if (ok && data.success) {
    e.status = 'done'; e.chunks = data.chunks; e.result = data;
  } else {
    e.status = 'error'; e.error = data.detail || 'Upload failed';
  }
}

async function startUpload() {
  const pending = entries.filter((e) => e.status === 'pending');
  if (!pending.length) return;
  uploading = true;
  attempted = true;
  progress = { done: 0, total: pending.length };
  render();
  for (const e of pending) {
    await send(e);
    progress.done += 1;
    render();
  }
  uploading = false;
  render();
  loadDocuments();
}

// Replace: remove the existing document (the matched name, which may differ for
// a content duplicate), then force the upload past dedup.
async function replaceEntry(e) {
  uploading = true; progress = { done: 0, total: 1 };
  e.status = 'uploading'; stageProg = { pct: 0, text: 'Starting…' }; render();
  await deleteDocument(e.dupExisting || e.name);
  const { ok, data } = await uploadFileStream(e.file, e.tags.join(','), e.desc, true, onStageEvent);
  if (ok && data.success) { e.status = 'done'; e.chunks = data.chunks; e.replaced = true; e.result = data; }
  else { e.status = 'error'; e.error = data.detail || 'Replace failed'; }
  uploading = false; render(); loadDocuments();
}

// Keep both: upload a "(1)"-suffixed copy, forced past the content-dup check.
async function copyEntry(e) {
  const dot = e.name.lastIndexOf('.');
  const newName = dot <= 0 ? `${e.name} (1)` : `${e.name.slice(0, dot)} (1)${e.name.slice(dot)}`;
  const file = new File([e.file], newName, { type: e.file.type });
  uploading = true; progress = { done: 0, total: 1 };
  e.status = 'uploading'; stageProg = { pct: 0, text: 'Starting…' }; render();
  const { ok, data } = await uploadFileStream(file, e.tags.join(','), e.desc, true, onStageEvent);
  if (ok && data.success) { e.status = 'done'; e.chunks = data.chunks; e.name = newName; e.result = data; }
  else { e.status = 'error'; e.error = data.detail || 'Upload failed'; }
  uploading = false; render(); loadDocuments();
}

// -- Event delegation ------------------------------------------------------
async function createNewTag() {
  const name = ($('upNewTagName').value || '').trim();
  const typeId = $('upNewTagType').value;
  if (!name || !typeId) return;
  const { ok, data } = await addTag({ name, type_id: typeId });
  if (!ok) { alert(data.detail || 'Could not create tag'); return; }
  state.tagTypes = data.tag_types || state.tagTypes;
  state.tags = data.tags || state.tags;
  newTagFor = null;
  render();
}

function onBodyClick(ev) {
  const el = ev.target.closest('[data-up]');
  if (!el) return;
  const act = el.dataset.up;
  if (act === 'browse-files') { $('upInput').click(); return; }
  if (act === 'browse-folder') { $('upFolderInput').click(); return; }
  if (act === 'newtag-open') { newTagFor = el.dataset.scope; render(); return; }
  if (act === 'newtag-cancel') { newTagFor = null; render(); return; }
  if (act === 'newtag-create') { createNewTag(); return; }
  if (act === 'tgroup') { const id = el.dataset.type; tagGroupsCollapsed[id] = !tagGroupsCollapsed[id]; render(); return; }
  if (act === 'folder-toggle') { const f = folders[el.dataset.folder]; if (f) { f.expanded = !f.expanded; render(); } return; }
  if (act === 'folder-tag') { setFolderTag(el.dataset.folder, el.dataset.tag); return; }
  const e = entries.find((x) => x.id === el.dataset.id);
  if (!e) return;
  if (act === 'tag') {
    const t = el.dataset.tag;
    e.tags = e.tags.includes(t) ? e.tags.filter((x) => x !== t) : [...e.tags, t];
    render();
  } else if (act === 'remove') removeEntry(e.id);
  else if (act === 'replace') replaceEntry(e);
  else if (act === 'copy') copyEntry(e);
}

async function openModal() {
  entries = []; folders = {}; newTagFor = null; tagGroupsCollapsed = {};
  uploading = false; attempted = false; progress = { done: 0, total: 0 };
  const { ok, data } = await getTags();
  if (ok) { state.tagTypes = data.tag_types || []; state.tags = data.tags || []; }
  render();
  $('uploadModal').classList.remove('hidden');
}

function closeModal() { $('uploadModal').classList.add('hidden'); }

export function initUpload() {
  $('uploadOpenBtn').onclick = openModal;
  $('uploadModalClose').onclick = closeModal;
  $('uploadCloseBtn').onclick = closeModal;
  // The footer's primary button uploads the queue, or closes once the summary shows.
  $('uploadStartBtn').onclick = () => { if (summaryReady()) closeModal(); else startUpload(); };
  $('uploadModal').onclick = (e) => { if (e.target.id === 'uploadModal') closeModal(); };
  const body = $('uploadModalBody');
  body.addEventListener('click', onBodyClick);
  body.addEventListener('change', (e) => {
    if (e.target.id === 'upInput') { addFiles(e.target.files); e.target.value = ''; }
    else if (e.target.id === 'upFolderInput') { addFolder(e.target.files); e.target.value = ''; }
  });
  body.addEventListener('input', (e) => {
    const d = e.target.dataset || {};
    if (d.up === 'desc') { const en = entries.find((x) => x.id === d.id); if (en) en.desc = e.target.value; return; }
    if (d.up === 'folder-desc') { setFolderDesc(d.folder, e.target.value); }
  });
}
