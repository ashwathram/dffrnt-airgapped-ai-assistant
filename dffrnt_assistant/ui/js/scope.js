// Chat retrieval scope bar: pick taxonomy tags (grouped by type) to restrict
// the assistant's search to documents carrying any of them (state.chatScope,
// sent with each query). Shows how many documents fall in scope. Collapsible.
import { $, esc } from './util.js';
import { svg } from './icons.js';
import { state } from './state.js';
import { getTags, listDocuments } from './api.js';

let open = false;

// Documents matching the current scope (OR semantics, mirroring retrieval).
function docsInScope() {
  const docs = state.documents || [];
  if (!state.chatScope.length) return docs.length;
  return docs.filter((d) => state.chatScope.some((t) => (d.tags || []).includes(t))).length;
}

export function renderScope() {
  const el = $('chatScope');
  if (!state.tags.length) { el.innerHTML = ''; return; }
  // Drop scoped tags that no longer exist in the taxonomy.
  state.chatScope = state.chatScope.filter((n) => state.tags.some((t) => t.name === n));
  const n = state.chatScope.length;
  const inScope = docsInScope();

  const groups = state.tagTypes.map((tt) => {
    const tags = state.tags.filter((t) => t.typeId === tt.id);
    if (!tags.length) return '';
    const chips = tags.map((t) => {
      const on = state.chatScope.includes(t.name);
      const style = on ? `background:${tt.color};color:#fff;border-color:${tt.color}` : `color:${tt.color};border-color:${tt.color}55`;
      return `<button class="scope-chip${on ? ' on' : ''}" data-scope="tag" data-tag="${esc(t.name)}" style="${style}">${esc(t.name)}</button>`;
    }).join('');
    return `<div class="scope-group"><span class="scope-gname" style="color:${tt.color}">${esc(tt.name)}</span><div class="scope-chips">${chips}</div></div>`;
  }).join('');

  el.innerHTML = `
    <button class="scope-head" data-scope="toggle">
      ${svg('tag')}
      <span class="scope-label">${n ? `Searching ${n} tag${n > 1 ? 's' : ''}` : 'Search scope: all documents'}</span>
      ${n ? `<span class="scope-count">${n}</span>` : ''}
      <span class="scope-spacer"></span>
      <span class="scope-docs">${inScope} doc${inScope === 1 ? '' : 's'} in scope</span>
      <span class="scope-chev">${svg(open ? 'chevronUp' : 'chevronDown')}</span>
    </button>
    ${open ? `<div class="scope-body">
      ${groups}
      ${n ? '<button class="scope-clear" data-scope="clear">Clear</button>' : ''}
    </div>` : ''}`;

  el.querySelectorAll('[data-scope]').forEach((b) => {
    b.onclick = () => {
      const a = b.dataset.scope;
      if (a === 'toggle') open = !open;
      else if (a === 'tag') {
        const name = b.dataset.tag;
        state.chatScope = state.chatScope.includes(name)
          ? state.chatScope.filter((x) => x !== name) : [...state.chatScope, name];
      } else if (a === 'clear') state.chatScope = [];
      renderScope();
    };
  });
}

export async function initScope() {
  const [tagRes, docRes] = await Promise.all([getTags(), listDocuments()]);
  if (tagRes.ok) { state.tagTypes = tagRes.data.tag_types || []; state.tags = tagRes.data.tags || []; }
  if (docRes.ok) state.documents = docRes.data.documents || [];
  renderScope();
}
