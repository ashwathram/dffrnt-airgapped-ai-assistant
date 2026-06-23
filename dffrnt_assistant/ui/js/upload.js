// Upload modal: a queue with client-side validation, per-file (or per-folder)
// taxonomy tags + description, sequential upload with a progress bar and an
// ingestion summary, and duplicate handling. Duplicates are detected server-side
// by SHA-256 (same name, or same content under a different name) and resolved
// inline with Replace / Keep both / Skip. Wired to /api/upload (+ DELETE for
// Replace). Folder uploads share tags/description across all their files.
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import { getTags, uploadFile, deleteDocument, addTag } from './api.js';
import { loadDocuments } from './library.js';

const SUPPORTED = ['pdf', 'docx', 'pptx', 'xlsx', 'csv', 'txt', 'md']; // matches backend
const MAX_MB = 50;
const MAX_BYTES = MAX_MB * 1024 * 1024;

// entries: {id, file, name, size, tags:[], desc, folder?, status, error?,
//           chunks?, warning?, dupKind?, dupExisting?, replaced?}
let entries = [];
let folders = {};        // folderName -> { desc, tags:[], expanded }
let uploader = 'admin';
let uid = 0;
let showNewTag = false;  // inline "create a new tag" form is open
let uploading = false;   // a batch is in flight (drives the progress bar)
let attempted = false;   // a batch has run (drives the ingestion summary)
let progress = { done: 0, total: 0 };

function fmtSize(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function validate(file) {
  const ext = (file.name.split('.').pop() || '').toLowerCase();
  if (!SUPPORTED.includes(ext)) return `Unsupported type (.${ext || '?'}). Accepted: ${SUPPORTED.join(', ').toUpperCase()}`;
  if (file.size === 0) return 'File is empty';
  if (file.size > MAX_BYTES) return `Exceeds ${MAX_MB} MB (${fmtSize(file.size)})`;
  return null;
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
  if (e.status === 'skipped') return '<span class="up-status muted">Skipped</span>';
  if (e.status === 'uploading') return '<span class="up-status">Uploading…</span>';
  if (e.status === 'invalid') return '<span class="up-status err">Invalid</span>';
  return '';
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

// Tag chips — either per standalone file (data-up="tag") or per folder (data-up="folder-tag").
function tagChips(selected, scope) {
  if (!state.tags.length) return '';
  return `<div class="up-tags">${state.tags.map((t) => {
    const on = selected.includes(t.name);
    const tt = state.tagTypes.find((x) => x.id === t.typeId);
    const col = tt ? tt.color : '#5a6a78';
    const style = on ? `background:${col};color:#fff;border-color:${col}` : `color:${col};border-color:${col}55`;
    return `<button class="up-tag${on ? ' on' : ''}" data-up="${scope.kind}" ${scope.attr} data-tag="${esc(t.name)}" style="${style}">${esc(t.name)}</button>`;
  }).join('')}</div>`;
}

function dupActions(e) {
  if (e.status !== 'dup') return '';
  return `
    <div class="up-dup">
      <span class="up-dupmsg">${esc(e.warning || 'Already in the knowledge base.')}</span>
      <div class="up-dupbtns">
        <button class="btn btn-sm btn-primary" data-up="replace" data-id="${e.id}">Replace</button>
        <button class="btn btn-sm" data-up="copy" data-id="${e.id}">Keep both</button>
        <button class="btn btn-sm btn-ghost" data-up="skip" data-id="${e.id}">Skip</button>
      </div>
    </div>`;
}

// Standalone (non-folder) file row: own description + tags.
function entryHtml(e) {
  const removeBtn = e.status === 'pending'
    ? `<button class="up-remove" data-up="remove" data-id="${e.id}" title="Remove">${svg('x')}</button>` : '';
  return `
    <div class="up-row">
      <div class="up-rowtop">
        <span class="up-file">${svg('file')}<span class="up-name">${esc(e.name)}</span><span class="up-size">${fmtSize(e.size)}</span></span>
        ${statusHtml(e)}${removeBtn}
      </div>
      ${e.error && e.status === 'invalid' ? `<div class="up-err">${esc(e.error)}</div>` : descField(e) + tagChips(e.tags, { kind: 'tag', attr: `data-id="${e.id}"` })}
      ${dupActions(e)}
    </div>`;
}

// Folder file row: compact (tags/description come from the folder group).
function folderFileRow(e) {
  const removeBtn = e.status === 'pending'
    ? `<button class="up-remove" data-up="remove" data-id="${e.id}" title="Remove">${svg('x')}</button>` : '';
  return `
    <div class="up-frow">
      <span class="up-file">${svg('file')}<span class="up-name">${esc(e.name)}</span><span class="up-size">${fmtSize(e.size)}</span></span>
      ${statusHtml(e)}${removeBtn}
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
        <span class="uf-count">${members.length} file${members.length === 1 ? '' : 's'}</span>
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
            ${state.tags.length ? `<div class="up-folder-tags"><label>Tags <span class="up-opt">(applied to all files)</span></label>${tagChips(f.tags, { kind: 'folder-tag', attr: `data-folder="${esc(fn)}"` })}</div>` : ''}
          ` : ''}
          <div class="up-folder-files">${members.map(folderFileRow).join('')}</div>
        </div>` : ''}
    </div>`;
}

function progressHtml() {
  if (!uploading || !progress.total) return '';
  const pct = Math.round(progress.done / progress.total * 100);
  return `
    <div class="up-progress">
      <div class="up-progress-top"><span>Uploading… ${progress.done}/${progress.total}</span><span>${pct}%</span></div>
      <div class="up-progress-bar"><div class="up-progress-fill" style="width:${pct}%"></div></div>
    </div>`;
}

function ingestSummaryHtml() {
  if (!attempted || uploading) return '';
  const done = entries.filter((e) => e.status === 'done');
  const replaced = done.filter((e) => e.replaced).length;
  const dup = entries.filter((e) => e.status === 'dup').length;
  const skipped = entries.filter((e) => e.status === 'skipped').length;
  const failed = entries.filter((e) => e.status === 'error' || e.status === 'invalid').length;
  const chunks = done.reduce((s, e) => s + (e.chunks || 0), 0);
  const parts = [
    `${done.length} ingested`,
    replaced ? `${replaced} replaced` : '',
    dup ? `${dup} duplicate${dup === 1 ? '' : 's'} to resolve` : '',
    skipped ? `${skipped} skipped` : '',
    failed ? `${failed} failed` : '',
  ].filter(Boolean);
  const kind = failed ? 'err' : dup ? 'warn' : 'ok';
  return `
    <div class="up-ingest up-ingest-${kind}">
      <div class="ui-line">${svg(failed ? 'alert' : 'database')} Ingestion summary</div>
      <div class="ui-stats">${parts.join(' · ')}${chunks ? ` · ${chunks} chunks indexed` : ''}</div>
    </div>`;
}

// Inline "create a new tag" control — adds to the taxonomy so it becomes a
// selectable chip on every file (mirrors the concept's upload tag creator).
function newTagHtml() {
  if (!state.tagTypes.length) return ''; // a tag needs a type; manage those in Tag Manager
  if (!showNewTag) {
    return `<button class="up-newtag-btn" data-up="newtag-open">${svg('plus')} New tag</button>`;
  }
  const opts = state.tagTypes.map((tt) => `<option value="${tt.id}">${esc(tt.name)}</option>`).join('');
  return `
    <div class="up-newtag">
      <input id="upNewTagName" class="tt-input" placeholder="New tag name…" />
      <select id="upNewTagType" class="tt-input">${opts}</select>
      <button class="btn btn-sm btn-primary" data-up="newtag-create">Create</button>
      <button class="btn btn-sm btn-ghost" data-up="newtag-cancel">Cancel</button>
    </div>`;
}

function render() {
  const folderNames = Object.keys(folders).filter((fn) => entries.some((e) => e.folder === fn));
  const standalone = entries.filter((e) => !e.folder);
  $('uploadModalBody').innerHTML = `
    <div class="up-meta">
      <label>Uploaded by</label>
      <input id="upUploader" class="tt-input" value="${esc(uploader)}" />
    </div>
    <div class="up-newtag-row">${newTagHtml()}</div>
    <div class="dropzone" id="upDrop">
      ${svg('upload')}
      <strong>Drag &amp; drop files here</strong>
      <span>PDF, DOCX, PPTX, XLSX, CSV, TXT, MD · up to ${MAX_MB} MB</span>
      <div class="dz-btns">
        <button class="btn btn-sm" data-up="browse-files">Browse files</button>
        <button class="btn btn-sm" data-up="browse-folder">${svg('folder')} Browse folder</button>
      </div>
      <input type="file" id="upInput" multiple hidden />
      <input type="file" id="upFolderInput" hidden webkitdirectory directory />
    </div>
    ${progressHtml()}
    ${ingestSummaryHtml()}
    ${folderNames.map(folderGroupHtml).join('')}
    ${standalone.length ? `<div class="up-queue">${standalone.map(entryHtml).join('')}</div>` : ''}`;

  const drop = $('upDrop');
  drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add('drag'); };
  drop.ondragleave = () => drop.classList.remove('drag');
  drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove('drag'); addFiles(ev.dataTransfer.files); };
  refreshFoot();
}

function refreshFoot() {
  const pending = entries.filter((e) => e.status === 'pending').length;
  const done = entries.filter((e) => e.status === 'done').length;
  $('uploadStartBtn').disabled = uploading || pending === 0;
  $('uploadStartBtn').textContent = pending ? `Upload ${pending} file${pending === 1 ? '' : 's'}` : 'Upload';
  $('upSummary').textContent = done ? `${done} uploaded` : '';
}

// -- Uploading -------------------------------------------------------------
async function send(e) {
  e.status = 'uploading'; render();
  const { ok, data } = await uploadFile(e.file, uploader || 'admin', e.tags.join(','), e.desc, false);
  if (data.duplicate) {
    e.status = 'dup'; e.warning = data.warning; e.dupKind = data.kind; e.dupExisting = data.existing;
  } else if (ok && data.success) {
    e.status = 'done'; e.chunks = data.chunks;
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
  e.status = 'uploading'; render();
  await deleteDocument(e.dupExisting || e.name);
  const { ok, data } = await uploadFile(e.file, uploader || 'admin', e.tags.join(','), e.desc, true);
  if (ok && data.success) { e.status = 'done'; e.chunks = data.chunks; e.replaced = true; }
  else { e.status = 'error'; e.error = data.detail || 'Replace failed'; }
  render(); loadDocuments();
}

// Keep both: upload a "(1)"-suffixed copy, forced past the content-dup check.
async function copyEntry(e) {
  const dot = e.name.lastIndexOf('.');
  const newName = dot <= 0 ? `${e.name} (1)` : `${e.name.slice(0, dot)} (1)${e.name.slice(dot)}`;
  const file = new File([e.file], newName, { type: e.file.type });
  e.status = 'uploading'; render();
  const { ok, data } = await uploadFile(file, uploader || 'admin', e.tags.join(','), e.desc, true);
  if (ok && data.success) { e.status = 'done'; e.chunks = data.chunks; e.name = newName; }
  else { e.status = 'error'; e.error = data.detail || 'Upload failed'; }
  render(); loadDocuments();
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
  showNewTag = false;
  render();
}

function onBodyClick(ev) {
  const el = ev.target.closest('[data-up]');
  if (!el) return;
  const act = el.dataset.up;
  if (act === 'browse-files') { $('upInput').click(); return; }
  if (act === 'browse-folder') { $('upFolderInput').click(); return; }
  if (act === 'newtag-open') { showNewTag = true; render(); return; }
  if (act === 'newtag-cancel') { showNewTag = false; render(); return; }
  if (act === 'newtag-create') { createNewTag(); return; }
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
  else if (act === 'skip') { e.status = 'skipped'; render(); }
}

async function openModal() {
  entries = []; folders = {}; uploader = 'admin'; showNewTag = false;
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
  $('uploadStartBtn').onclick = startUpload;
  $('uploadModal').onclick = (e) => { if (e.target.id === 'uploadModal') closeModal(); };
  const body = $('uploadModalBody');
  body.addEventListener('click', onBodyClick);
  body.addEventListener('change', (e) => {
    if (e.target.id === 'upInput') { addFiles(e.target.files); e.target.value = ''; }
    else if (e.target.id === 'upFolderInput') { addFolder(e.target.files); e.target.value = ''; }
  });
  body.addEventListener('input', (e) => {
    const d = e.target.dataset || {};
    if (e.target.id === 'upUploader') { uploader = e.target.value; return; }
    if (d.up === 'desc') { const en = entries.find((x) => x.id === d.id); if (en) en.desc = e.target.value; return; }
    if (d.up === 'folder-desc') { setFolderDesc(d.folder, e.target.value); }
  });
}
