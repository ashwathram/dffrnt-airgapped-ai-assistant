// Thin wrappers over the FastAPI backend (dffrnt_assistant/api/app.py).
// Each returns { ok, data } so callers handle success/error uniformly.

async function asJson(promise) {
  const r = await promise;
  const data = await r.json().catch(() => ({}));
  return { ok: r.ok, data };
}

// Stream an answer as an async iterator of events from /api/query/stream.
// Yields { type:'sources', sources } then many { type:'token', text },
// then { type:'done' }, or { type:'error', detail } on failure.
export async function* queryStream(question, history, signal, tags) {
  const r = await fetch('/api/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, conversation_history: history, tags: tags || [] }),
    signal,
  });
  if (!r.ok || !r.body) {
    const data = await r.json().catch(() => ({}));
    yield { type: 'error', detail: data.detail || 'Request failed.' };
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl;
    while ((nl = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) yield JSON.parse(line);
    }
  }
  const tail = buffer.trim();
  if (tail) yield JSON.parse(tail);
}

// Render an answer's Markdown to a PDF server-side. Returns the PDF as a Blob
// ({ ok:false } on failure) — unlike the JSON helpers, since the body is binary.
export async function exportAnswerPdf(content, title) {
  const r = await fetch('/api/export/pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, title: title || '' }),
  });
  if (!r.ok) return { ok: false };
  return { ok: true, blob: await r.blob() };
}

export function listDocuments() {
  return asJson(fetch('/api/documents'));
}

export function uploadFile(file, tags, description, force) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('tags', tags);
  fd.append('description', description || '');
  fd.append('force', force ? 'true' : 'false');
  return asJson(fetch('/api/upload', { method: 'POST', body: fd }));
}

// Streaming upload: reports real progress via XHR. `onEvent` receives
//   { stage:'transfer', loaded, total }                 while bytes upload
//   { stage:'received' | 'parsing' | 'chunking' | 'storing' }
//   { stage:'embedding', done, total }                  per embed batch
// Resolves { ok, data } where data is the final result (done), the duplicate
// descriptor, or { detail } on error — matching uploadFile's shape.
export function uploadFileStream(file, tags, description, force, onEvent) {
  return new Promise((resolve) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('tags', tags);
    fd.append('description', description || '');
    fd.append('force', force ? 'true' : 'false');

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload/stream');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onEvent({ stage: 'transfer', loaded: e.loaded, total: e.total });
    };

    // Parse newline-delimited JSON incrementally out of the growing responseText.
    let offset = 0;
    let last = null;
    const drain = () => {
      const text = xhr.responseText;
      let nl;
      while ((nl = text.indexOf('\n', offset)) >= 0) {
        const line = text.slice(offset, nl).trim();
        offset = nl + 1;
        if (!line) continue;
        try { const ev = JSON.parse(line); last = ev; onEvent(ev); } catch (_) { /* partial */ }
      }
    };
    xhr.onprogress = drain;
    xhr.onload = () => {
      drain();
      if (last && last.stage === 'done') resolve({ ok: true, data: last.result });
      else if (last && last.stage === 'duplicate') {
        const d = { ...last }; delete d.stage; resolve({ ok: true, data: d });
      } else if (last && last.stage === 'error') resolve({ ok: false, data: { detail: last.detail } });
      else resolve({ ok: false, data: { detail: 'Upload failed' } });
    };
    xhr.onerror = () => resolve({ ok: false, data: { detail: 'Network error during upload' } });
    xhr.send(fd);
  });
}

export function deleteDocument(filename) {
  return asJson(fetch('/api/documents/' + encodeURIComponent(filename), { method: 'DELETE' }));
}
export function updateDocTags(filename, tags) {
  return sendJson('/api/documents/' + encodeURIComponent(filename) + '/tags', 'PUT', { tags });
}
export function updateDocDescription(filename, description) {
  return sendJson('/api/documents/' + encodeURIComponent(filename) + '/description', 'PUT', { description });
}

// -- Tag taxonomy ----------------------------------------------------------
function sendJson(url, method, body) {
  return asJson(fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }));
}

export function getTags() {
  return asJson(fetch('/api/tags'));
}
export function addTagType(body) {
  return sendJson('/api/tags/types', 'POST', body);
}
export function updateTagType(id, body) {
  return sendJson('/api/tags/types/' + encodeURIComponent(id), 'PUT', body);
}
export function deleteTagType(id) {
  return asJson(fetch('/api/tags/types/' + encodeURIComponent(id), { method: 'DELETE' }));
}
export function addTag(body) {
  return sendJson('/api/tags/tags', 'POST', body);
}
export function deleteTag(id) {
  return asJson(fetch('/api/tags/tags/' + encodeURIComponent(id), { method: 'DELETE' }));
}
export function importTags() {
  return asJson(fetch('/api/tags/import', { method: 'POST' }));
}

// -- Conversations ---------------------------------------------------------
export function listConversations() {
  return asJson(fetch('/api/conversations'));
}
export function getConversation(id) {
  return asJson(fetch('/api/conversations/' + encodeURIComponent(id)));
}
export function createConversation(body) {
  return sendJson('/api/conversations', 'POST', body);
}
export function updateConversation(id, body) {
  return sendJson('/api/conversations/' + encodeURIComponent(id), 'PUT', body);
}
export function deleteConversation(id) {
  return asJson(fetch('/api/conversations/' + encodeURIComponent(id), { method: 'DELETE' }));
}
export function clearConversations() {
  return asJson(fetch('/api/conversations', { method: 'DELETE' }));
}
