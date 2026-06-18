// Upload modal: queue with client-side validation, per-file taxonomy tags,
// sequential upload, and duplicate handling (Replace / Keep both / Skip).
// Wired to /api/upload (+ DELETE for Replace). Description/folder-grouping from
// the concept are omitted (the backend stores neither).
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import { getTags, uploadFile, deleteDocument, addTag } from './api.js';
import { loadDocuments } from './library.js';

const SUPPORTED = ['pdf', 'docx', 'pptx', 'xlsx', 'csv', 'txt', 'md']; // matches backend
const MAX_MB = 50;
const MAX_BYTES = MAX_MB * 1024 * 1024;

let entries = [];        // {id, file, name, size, tags:[], status, error?, chunks?, warning?}
let uploader = 'admin';
let uid = 0;
let showNewTag = false;  // inline "create a new tag" form is open

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

function addFiles(fileList) {
  for (const file of Array.from(fileList)) {
    const error = validate(file);
    entries.push({
      id: 'u' + (++uid), file, name: file.name, size: file.size,
      tags: [], status: error ? 'invalid' : 'pending', error,
    });
  }
  render();
}

const STATUS = {
  pending: '', uploading: 'Uploading…', done: 'done', dup: '⚠ Duplicate',
  skipped: 'Skipped', error: 'error', invalid: 'Invalid',
};

function statusHtml(e) {
  if (e.status === 'done') return `<span class="up-status done">✓ ${e.chunks} chunks${e.replaced ? ' (replaced)' : ''}</span>`;
  if (e.status === 'error') return `<span class="up-status err">✗ ${esc(e.error || 'Failed')}</span>`;
  if (e.status === 'dup') return '<span class="up-status dup">⚠ Duplicate</span>';
  if (e.status === 'skipped') return '<span class="up-status muted">Skipped</span>';
  if (e.status === 'uploading') return '<span class="up-status">Uploading…</span>';
  if (e.status === 'invalid') return '<span class="up-status err">Invalid</span>';
  return '';
}

function tagChips(e) {
  if (e.status !== 'pending' || !state.tags.length) return '';
  return `<div class="up-tags">${state.tags.map((t) => {
    const on = e.tags.includes(t.name);
    const tt = state.tagTypes.find((x) => x.id === t.typeId);
    const col = tt ? tt.color : '#5a6a78';
    const style = on ? `background:${col};color:#fff;border-color:${col}` : `color:${col};border-color:${col}55`;
    return `<button class="up-tag${on ? ' on' : ''}" data-up="tag" data-id="${e.id}" data-tag="${esc(t.name)}" style="${style}">${esc(t.name)}</button>`;
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

function entryHtml(e) {
  return `
    <div class="up-row">
      <div class="up-rowtop">
        <span class="up-file">${svg('file')}<span class="up-name">${esc(e.name)}</span><span class="up-size">${fmtSize(e.size)}</span></span>
        ${statusHtml(e)}
      </div>
      ${e.error && e.status === 'invalid' ? `<div class="up-err">${esc(e.error)}</div>` : tagChips(e)}
      ${dupActions(e)}
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
  $('uploadModalBody').innerHTML = `
    <div class="up-meta">
      <label>Uploaded by</label>
      <input id="upUploader" class="tt-input" value="${esc(uploader)}" />
    </div>
    <div class="up-newtag-row">${newTagHtml()}</div>
    <div class="dropzone" id="upDrop">
      ${svg('upload')}
      <strong>Drag &amp; drop files, or click to browse</strong>
      <span>PDF, DOCX, PPTX, XLSX, CSV, TXT, MD · up to ${MAX_MB} MB</span>
      <input type="file" id="upInput" multiple />
    </div>
    ${entries.length ? `<div class="up-queue">${entries.map(entryHtml).join('')}</div>` : ''}`;

  const drop = $('upDrop');
  drop.ondragover = (ev) => { ev.preventDefault(); drop.classList.add('drag'); };
  drop.ondragleave = () => drop.classList.remove('drag');
  drop.ondrop = (ev) => { ev.preventDefault(); drop.classList.remove('drag'); addFiles(ev.dataTransfer.files); };
  refreshFoot();
}

function refreshFoot() {
  const pending = entries.filter((e) => e.status === 'pending').length;
  const done = entries.filter((e) => e.status === 'done').length;
  $('uploadStartBtn').disabled = pending === 0;
  $('uploadStartBtn').textContent = pending ? `Upload ${pending} file${pending === 1 ? '' : 's'}` : 'Upload';
  $('upSummary').textContent = done ? `${done} uploaded` : '';
}

// -- Uploading -------------------------------------------------------------
async function send(e, file, name) {
  e.status = 'uploading'; render();
  const { ok, data } = await uploadFile(file, uploader || 'admin', e.tags.join(','));
  if (data.duplicate) { e.status = 'dup'; e.warning = data.warning; }
  else if (ok && data.success) { e.status = 'done'; e.chunks = data.chunks; }
  else { e.status = 'error'; e.error = data.detail || 'Upload failed'; }
  render();
}

async function startUpload() {
  for (const e of entries) {
    if (e.status === 'pending') await send(e, e.file, e.name);
  }
  loadDocuments();
  refreshFoot();
}

async function replaceEntry(e) {
  e.status = 'uploading'; render();
  await deleteDocument(e.name);
  const { ok, data } = await uploadFile(e.file, uploader || 'admin', e.tags.join(','));
  if (ok && data.success) { e.status = 'done'; e.chunks = data.chunks; e.replaced = true; }
  else { e.status = 'error'; e.error = data.detail || 'Replace failed'; }
  render(); loadDocuments();
}

async function copyEntry(e) {
  const dot = e.name.lastIndexOf('.');
  const newName = dot <= 0 ? `${e.name} (1)` : `${e.name.slice(0, dot)} (1)${e.name.slice(dot)}`;
  const file = new File([e.file], newName, { type: e.file.type });
  e.status = 'uploading'; render();
  const { ok, data } = await uploadFile(file, uploader || 'admin', e.tags.join(','));
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
  if (el) {
    const act = el.dataset.up;
    if (act === 'newtag-open') { showNewTag = true; render(); return; }
    if (act === 'newtag-cancel') { showNewTag = false; render(); return; }
    if (act === 'newtag-create') { createNewTag(); return; }
    const e = entries.find((x) => x.id === el.dataset.id);
    if (act === 'tag' && e) {
      const t = el.dataset.tag;
      e.tags = e.tags.includes(t) ? e.tags.filter((x) => x !== t) : [...e.tags, t];
      render();
    } else if (act === 'replace' && e) replaceEntry(e);
    else if (act === 'copy' && e) copyEntry(e);
    else if (act === 'skip' && e) { e.status = 'skipped'; render(); }
    return;
  }
  if (ev.target.closest('#upDrop')) $('upInput').click();
}

async function openModal() {
  entries = []; uploader = 'admin'; showNewTag = false;
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
  body.addEventListener('change', (e) => { if (e.target.id === 'upInput') addFiles(e.target.files); });
  body.addEventListener('input', (e) => { if (e.target.id === 'upUploader') uploader = e.target.value; });
}
