// Small DOM/text helpers shared across modules.

export const $ = (id) => document.getElementById(id);

// Escape user/LLM text before inserting into innerHTML.
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[c]));

export const nowTime = () =>
  new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
