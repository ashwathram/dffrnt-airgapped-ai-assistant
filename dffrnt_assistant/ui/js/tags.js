// Tag Manager modal: CRUD over the tag taxonomy (tag types + tags), backed by
// the /api/tags endpoints (stored as a single blob in the dffrnt_tags Qdrant
// collection). The whole taxonomy is small, so each mutation returns the fresh
// taxonomy and we re-render the modal from it.
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import {
  getTags, addTagType, updateTagType, deleteTagType, addTag, deleteTag, importTags,
} from './api.js';

const PRESET_COLORS = [
  '#5D27B8', '#E72300', '#091A29', '#0a7c4a',
  '#0369a1', '#b45309', '#9d174d', '#4338ca',
];

// Transient UI state for the modal (not persisted).
const ui = { expanded: {}, editingTypeId: null, showNewType: false };

function apply(taxonomy) {
  state.tagTypes = taxonomy.tag_types || [];
  state.tags = taxonomy.tags || [];
}

// Run a tag API call; on success refresh state + re-render, else surface error.
async function mutate(promise, after) {
  const { ok, data } = await promise;
  if (!ok) { alert(data.detail || 'Request failed.'); return; }
  apply(data);
  if (after) after();
  render();
}

function colorSwatches(rowId, selected) {
  const dots = PRESET_COLORS.map((c) =>
    `<button type="button" class="swatch${c === selected ? ' sel' : ''}" data-action="swatch" data-color="${c}" style="background:${c}"></button>`
  ).join('');
  return `<div class="swatch-row" id="${rowId}" data-color="${selected}">${dots}</div>`;
}

function typeCardHtml(tt) {
  const typeTags = state.tags.filter((t) => t.typeId === tt.id);
  const expanded = !!ui.expanded[tt.id];

  if (ui.editingTypeId === tt.id) {
    return `
      <div class="tt-card">
        <div class="tt-edit">
          <input id="editName" class="tt-input" value="${esc(tt.name)}" placeholder="Type name" />
          <input id="editDesc" class="tt-input" value="${esc(tt.description || '')}" placeholder="Description (optional)" />
          ${colorSwatches('editColors', tt.color)}
          <div class="tt-actions">
            <button class="btn btn-primary btn-sm" data-action="save-edit" data-id="${tt.id}">Save</button>
            <button class="btn btn-ghost btn-sm" data-action="cancel-edit">Cancel</button>
          </div>
        </div>
      </div>`;
  }

  const tagChips = typeTags.length
    ? typeTags.map((tag) => `
        <span class="tt-chip" style="background:${tt.color}18;color:${tt.color};border-color:${tt.color}30">
          ${esc(tag.name)}
          <button data-action="delete-tag" data-id="${tag.id}" title="Remove tag">${svg('x')}</button>
        </span>`).join('')
    : '<span class="tt-empty">No tags yet</span>';

  return `
    <div class="tt-card">
      <div class="tt-head" data-action="expand" data-id="${tt.id}" style="background:${tt.color}0a">
        <span class="tt-dot" style="background:${tt.color}"></span>
        <div class="tt-meta">
          <span class="tt-name">${esc(tt.name)}</span>
          ${tt.description ? `<span class="tt-desc">${esc(tt.description)}</span>` : ''}
        </div>
        <span class="tt-count">${typeTags.length} tag${typeTags.length === 1 ? '' : 's'}</span>
        <button class="tt-icon" data-action="edit" data-id="${tt.id}" title="Edit type">${svg('pencil')}</button>
        <button class="tt-icon tt-del" data-action="delete-type" data-id="${tt.id}" title="Delete type">${svg('trash')}</button>
        <span class="tt-chevron">${svg(expanded ? 'chevronDown' : 'chevronRight')}</span>
      </div>
      ${expanded ? `
        <div class="tt-body">
          <div class="tt-chips">${tagChips}</div>
          <div class="tt-add">
            <input id="addTag-${tt.id}" class="tt-input" data-add-type="${tt.id}" placeholder="Add tag to ${esc(tt.name)}…" />
            <button class="btn btn-sm" style="background:${tt.color};color:#fff" data-action="add-tag" data-id="${tt.id}">Add</button>
          </div>
        </div>` : ''}
    </div>`;
}

function newTypeHtml() {
  if (!ui.showNewType) {
    return `<button class="tt-newbtn" data-action="show-new-type">${svg('plus')} New tag type</button>`;
  }
  return `
    <div class="tt-card tt-newform">
      <p class="tt-formtitle">New Tag Type</p>
      <div class="tt-grid">
        <input id="newTypeName" class="tt-input" placeholder="Type name (e.g. Department)" />
        <input id="newTypeDesc" class="tt-input" placeholder="Description (optional)" />
      </div>
      <div class="tt-colorrow"><span class="tt-collabel">Color</span>${colorSwatches('newTypeColors', PRESET_COLORS[0])}</div>
      <div class="tt-actions">
        <button class="btn btn-primary btn-sm" data-action="create-type">Create type</button>
        <button class="btn btn-ghost btn-sm" data-action="cancel-new-type">Cancel</button>
      </div>
    </div>`;
}

function render() {
  $('tagModalBody').innerHTML =
    state.tagTypes.map(typeCardHtml).join('') + newTypeHtml();
}

// Read the chosen color from a swatch row.
const chosenColor = (rowId) => $(rowId)?.dataset.color || PRESET_COLORS[0];

function onClick(e) {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const { action, id } = el.dataset;

  if (action === 'swatch') {
    const row = el.closest('.swatch-row');
    row.dataset.color = el.dataset.color;
    row.querySelectorAll('.swatch').forEach((s) => s.classList.toggle('sel', s === el));
    return;
  }
  if (action === 'expand') { ui.expanded[id] = !ui.expanded[id]; render(); return; }
  if (action === 'edit') { ui.editingTypeId = id; render(); return; }
  if (action === 'cancel-edit') { ui.editingTypeId = null; render(); return; }
  if (action === 'save-edit') {
    mutate(updateTagType(id, {
      name: $('editName').value,
      color: chosenColor('editColors'),
      description: $('editDesc').value,
    }), () => { ui.editingTypeId = null; });
    return;
  }
  if (action === 'delete-type') {
    if (confirm('Delete this tag type and all its tags?')) mutate(deleteTagType(id));
    return;
  }
  if (action === 'add-tag') {
    const input = $('addTag-' + id);
    if (input.value.trim()) mutate(addTag({ name: input.value, type_id: id }), () => { ui.expanded[id] = true; });
    return;
  }
  if (action === 'delete-tag') { mutate(deleteTag(id)); return; }
  if (action === 'show-new-type') { ui.showNewType = true; render(); return; }
  if (action === 'cancel-new-type') { ui.showNewType = false; render(); return; }
  if (action === 'create-type') {
    mutate(addTagType({
      name: $('newTypeName').value,
      color: chosenColor('newTypeColors'),
      description: $('newTypeDesc').value,
    }), () => { ui.showNewType = false; });
  }
}

// Enter in an "add tag" field submits it.
function onKeydown(e) {
  if (e.key !== 'Enter') return;
  const typeId = e.target.dataset.addType;
  if (typeId && e.target.value.trim()) {
    mutate(addTag({ name: e.target.value, type_id: typeId }), () => { ui.expanded[typeId] = true; });
  }
}

async function openModal() {
  ui.expanded = {}; ui.editingTypeId = null; ui.showNewType = false;
  const { ok, data } = await getTags();
  if (ok) apply(data);
  render();
  $('tagModal').classList.remove('hidden');
}

function closeModal() {
  $('tagModal').classList.add('hidden');
}

async function importFromDocuments() {
  const { ok, data } = await importTags();
  if (!ok) { alert(data.detail || 'Import failed.'); return; }
  apply(data);
  render();
  alert(`Imported ${data.imported} tag(s) into "${data.type}".`);
}

export function initTags() {
  $('manageTagsBtn').onclick = openModal;
  $('tagModalClose').onclick = closeModal;
  $('tagModalDone').onclick = closeModal;
  $('tagImportBtn').onclick = importFromDocuments;
  // Click on the dimmed backdrop (but not the dialog) closes the modal.
  $('tagModal').onclick = (e) => { if (e.target.id === 'tagModal') closeModal(); };
  const body = $('tagModalBody');
  body.addEventListener('click', onClick);
  body.addEventListener('keydown', onKeydown);
}
