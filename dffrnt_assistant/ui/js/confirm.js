// A styled, in-app confirmation dialog that replaces the browser's native
// confirm() so destructive actions match the rest of the design system.
// Usage: if (await confirmDialog({ title, message, confirmText, danger })) { … }
import { $ } from './util.js';

let resolver = null;

function close(result) {
  $('confirmModal').classList.add('hidden');
  const r = resolver; resolver = null;
  if (r) r(result);
}

export function confirmDialog({ title = 'Are you sure?', message = '', confirmText = 'Confirm', danger = true } = {}) {
  $('confirmTitle').textContent = title;
  $('confirmMessage').textContent = message;
  const ok = $('confirmOk');
  ok.textContent = confirmText;
  ok.classList.toggle('btn-danger', danger);
  $('confirmIcon').classList.toggle('danger', danger);
  $('confirmModal').classList.remove('hidden');
  ok.focus();
  return new Promise((resolve) => { resolver = resolve; });
}

export function initConfirm() {
  $('confirmOk').onclick = () => close(true);
  $('confirmCancel').onclick = () => close(false);
  $('confirmModal').onclick = (e) => { if (e.target.id === 'confirmModal') close(false); };
  document.addEventListener('keydown', (e) => {
    if (resolver === null) return;
    if (e.key === 'Escape') close(false);
    else if (e.key === 'Enter') close(true);
  });
}
