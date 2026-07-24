// DFFRNT Control Panel — behavior. A direct port of the retired Tk views'
// logic: the single-job busy lock, the confirm-before-mutate flows
// (install / reingest preview→apply / model switch / delete), and streamed
// consoles. All rendering uses textContent — command output is untrusted.
//
// Auth: the server mints a per-session token embedded in the URL it opens.
// fetch() sends it as a header; EventSource can't set headers, so SSE URLs
// carry it as a query parameter (accepted server-side for exactly this).

const token = new URLSearchParams(location.search).get('token') || '';
const $ = (id) => document.getElementById(id);

let state = null;        // /api/state payload
let modelsData = null;   // /api/models payload
let busy = false;
let jobSource = null;    // EventSource for the active job
let logSource = null;    // EventSource for log follow

// ---- tiny API layer ---------------------------------------------------------
async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { 'X-DFFRNT-Token': token, 'Content-Type': 'application/json',
               ...(opts.headers || {}) },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `${res.status} ${res.statusText}`);
  return body;
}
const sseUrl = (path, params = {}) =>
  path + '?' + new URLSearchParams({ ...params, token }).toString();

// ---- console ----------------------------------------------------------------
function appendConsole(el, line, isError = false) {
  const span = document.createElement('span');
  span.textContent = line + '\n';
  if (isError) span.className = 'err-line';
  el.appendChild(span);
  el.scrollTop = el.scrollHeight;
}
const jobConsole = () => $('jobConsole');

// ---- confirm modal ----------------------------------------------------------
function confirmModal(title, body) {
  return new Promise((resolve) => {
    $('modalTitle').textContent = title;
    $('modalBody').textContent = body;
    $('modalOverlay').classList.remove('hidden');
    const done = (answer) => {
      $('modalOverlay').classList.add('hidden');
      $('modalConfirm').onclick = $('modalCancel').onclick = null;
      resolve(answer);
    };
    $('modalConfirm').onclick = () => done(true);
    $('modalCancel').onclick = () => done(false);
  });
}

// ---- busy lock (the Tk _set_busy port) --------------------------------------
function setBusy(value) {
  busy = value;
  document.querySelectorAll('[data-verb], #installBtn, #applyModelBtn, ' +
      '#importBtn, #exportBtn, #reingestBtn, #modelRows button')
    .forEach((btn) => { btn.disabled = value; });
}

// ---- job runner -------------------------------------------------------------
// POST the verb, then stream its output into the shared console. onDone
// runs only on success (mirrors _run_action's on_success).
async function runAction(verb, params = {}, onDone = null) {
  if (busy) return;
  appendConsole(jobConsole(), `$ ${verb}`);
  try {
    await api('/api/action', { method: 'POST', body: JSON.stringify({ verb, ...params }) });
  } catch (err) {
    appendConsole(jobConsole(), `!! ${err.message}`, true);
    return;
  }
  setBusy(true);
  attachJobStream(onDone);
}

function attachJobStream(onDone = null) {
  if (jobSource) jobSource.close();
  jobSource = new EventSource(sseUrl('/api/job/events'));
  jobSource.onmessage = (e) => appendConsole(jobConsole(), JSON.parse(e.data).line);
  jobSource.addEventListener('done', (e) => {
    jobSource.close(); jobSource = null;
    const { error } = JSON.parse(e.data);
    if (error) appendConsole(jobConsole(), `!! ${error}`, true);
    setBusy(false);
    refreshData();                    // status/models may all have changed
    if (!error && onDone) onDone();
  });
  jobSource.onerror = () => {         // server went away mid-stream
    if (jobSource) { jobSource.close(); jobSource = null; setBusy(false); }
  };
}

// ---- rendering --------------------------------------------------------------
function pill(kind, text) {
  const el = document.createElement('span');
  el.className = `pill ${kind}`;
  el.textContent = text;
  return el;
}

function renderPrereqs(target, checks) {
  target.replaceChildren();
  for (const c of checks) {
    const row = document.createElement('div');
    row.className = 'row';
    row.appendChild(pill(c.ok ? 'ok' : 'err', c.ok ? 'OK' : 'MISSING'));
    const label = document.createElement('span');
    label.className = 'grow';
    label.textContent = c.name + (c.detail ? ` — ${c.detail}` : '');
    row.appendChild(label);
    target.appendChild(row);
  }
}

function renderServices(services) {
  const target = $('serviceRows');
  target.replaceChildren();
  const ports = { Qdrant: state?.config.qdrant_port, Ollama: state?.config.ollama_port,
                  API: state?.config.api_port };
  for (const s of services) {
    const kind = !s.running ? 'err' : s.healthy === false ? 'warn'
               : s.healthy === true ? 'ok' : 'muted';
    const row = document.createElement('div');
    row.className = 'row';
    row.appendChild(pill(kind, s.detail || (s.running ? 'up' : 'down')));
    const label = document.createElement('span');
    label.className = 'grow';
    label.textContent = s.name + (ports[s.name] ? `  ·  localhost:${ports[s.name]}` : '');
    row.appendChild(label);
    target.appendChild(row);
  }
}

function renderModels() {
  const { models, llm_model, embed_model, offline } = modelsData;
  const rows = $('modelRows');
  rows.replaceChildren();
  if (!models.length) {
    const empty = document.createElement('div');
    empty.className = 'row dim';
    empty.textContent = offline ? 'No models in the store yet — import one below.'
                                : 'No models in the store yet — they arrive on first start or via Import.';
    rows.appendChild(empty);
  }
  const roleView = { llm: ['ok', 'LLM'], embedder: ['ok', 'embedder'],
                     imported: ['muted', 'imported'], prunable: ['warn', 'prunes on restart'] };
  for (const m of models) {
    const row = document.createElement('div');
    row.className = 'row';
    row.appendChild(pill(...roleView[m.role]));
    const label = document.createElement('span');
    label.className = 'grow';
    label.textContent = `${m.name}  ·  ${m.size_h}`;
    row.appendChild(label);
    if (m.role === 'imported' || m.role === 'prunable') {
      const del = document.createElement('button');
      del.className = 'btn-ghost btn-sm';
      del.textContent = 'Delete';
      del.disabled = busy;
      del.onclick = () => deleteModel(m.name);
      row.appendChild(del);
    }
    rows.appendChild(row);
  }

  // Swap candidates: everything that isn't the embedder / embedder-shaped.
  const candidates = models.filter((m) => m.role !== 'embedder' && !m.embedder_like)
                           .map((m) => m.name);
  $('llmList').replaceChildren(...candidates.map((n) => new Option(n)));
  $('allModelList').replaceChildren(...models.map((m) => new Option(m.name)));
  if (!$('swapModel').value) $('swapModel').value = llm_model;
  $('swapModel').readOnly = false;
  $('swapHint').textContent = offline
    ? 'Pick from the models in this machine’s store and Apply & restart. This is an ' +
      'offline deployment: new models arrive via Import below, never by pulling. The ' +
      'previous model is removed at restart to reclaim disk (getting it back needs a ' +
      're-import or re-install).'
    : 'Pick an installed model — or type any Ollama model name (e.g. qwen3:8b) to pull ' +
      'it during the restart. The previous model is removed at restart to reclaim disk.';
  $('embedNote').textContent = `Embedder: ${embed_model || '(unset)'} — switching it ` +
    'requires a full re-ingest, so it is deliberately config.toml-only.';
  $('exportHint').textContent = offline
    ? 'Pack a model from this store into a single .tar for another machine. (Offline ' +
      'deployment: only already-present models can be exported.)'
    : 'Run this on the NETWORKED staging machine: pick an installed model or type any ' +
      'Ollama name — it is pulled first if absent (the stack must be started) — then ' +
      'packed into a single .tar to carry to the air-gapped machine on a USB drive. ' +
      'Plain tar, uncompressed: model weights don’t compress. The drive must not be ' +
      'FAT32 (4 GiB file limit); use exFAT.';
}

function renderState() {
  const p = state.platform;
  $('platformFooter').textContent = `${p.os} · ${p.pathway}`;
  $('platformDetail').textContent =
    `${p.os}  ·  ${p.arch}  ·  pathway: ${p.pathway}` +
    (p.gpu_detected ? '  ·  GPU detected' : '') +
    (p.docker_present ? '' : '  ·  docker not on PATH');
  $('installStatusText').textContent = state.installed
    ? `An installed stack was found at ${state.app_root}. Installing again updates it ` +
      'in place (the running stack is stopped first, and you choose whether your ' +
      'edited config.toml is kept).'
    : 'No installed stack found. Select the dffrnt-*.tar.gz bundle (produced by ' +
      'deploy/package.sh) and a destination, then Install.';
  $('bundleList').replaceChildren(...state.bundles.map((b) => new Option(b)));
  if (!$('bundlePath').value && state.bundles.length) $('bundlePath').value = state.bundles[0];
  if (!$('destPath').value) $('destPath').value = state.installed ? state.app_root
                                                                  : state.default_dest;
}

async function refreshData() {
  try {
    state = await api('/api/state');
    renderState();
  } catch (err) { appendConsole(jobConsole(), `!! ${err.message}`, true); return; }
  api('/api/prereqs').then((p) => {
    renderPrereqs($('installPrereqs'), p.install);
    renderPrereqs($('managePrereqs'), p.manage);
  }).catch(() => {});
  api('/api/status').then((s) => renderServices(s.services || [])).catch(() => {});
  api('/api/models').then((m) => { modelsData = m; renderModels(); }).catch(() => {});
}

// ---- actions ----------------------------------------------------------------
async function install() {
  const bundle = $('bundlePath').value.trim();
  const dest = $('destPath').value.trim();
  if (!bundle) return void appendConsole(jobConsole(), '!! Select a bundle first.', true);
  if (!dest) return void appendConsole(jobConsole(), '!! Choose an install destination.', true);
  const ok = await confirmModal('Confirm install',
    `Install ${bundle.split('/').pop()} into ${dest}?\n\nAny running stack there will be ` +
    'stopped and its images replaced, then the new stack is started.');
  if (!ok) return;
  runAction('install', { bundle, dest, overwrite_config: $('overwriteConfig').checked });
}

async function reingest() {
  // The two-phase Tk flow: preview job → confirm dialog → apply job.
  runAction('reingest_preview', {}, async () => {
    const ok = await confirmModal('Confirm re-ingestion',
      'Proceed with re-ingestion of the files listed in the console output above?\n\n' +
      'This can take a while and, once started, will not stop partway through.');
    if (ok) runAction('reingest_apply');
    else appendConsole(jobConsole(), '>> Aborted — nothing changed.');
  });
}

async function applyModel() {
  const name = $('swapModel').value.trim();
  if (!name) return void appendConsole(jobConsole(), '!! Pick or enter a model first.', true);
  const current = modelsData?.llm_model || '';
  const offline = modelsData?.offline;
  const present = (modelsData?.models || []).some((m) => m.name === name ||
    m.name === `${name}:latest`);
  const lines = [`Switch the active LLM from ${current || '(unset)'} to ${name}?`, ''];
  if (!present) lines.push(`• ${name} is not cached yet — it will be pulled during ` +
                           'the restart (needs network).');
  if (current) lines.push(`• ${current} will be REMOVED from the store at restart ` +
    'to reclaim disk' + (offline ? ' — on this offline machine, getting it back later ' +
    'means importing it again from a tarball.' : '.'));
  lines.push('• The stack restarts now; the assistant is briefly unavailable.');
  if (!(await confirmModal('Confirm model switch', lines.join('\n')))) return;
  runAction('model_use', { name });
}

async function deleteModel(name) {
  const offline = modelsData?.offline;
  const ok = await confirmModal('Delete model',
    `Remove ${name} from this machine's store?` +
    (offline ? '\n\nThis is an offline deployment — getting it back requires another ' +
               'tarball import.' : ''));
  if (ok) runAction('model_delete', { name });
}

// ---- logs view --------------------------------------------------------------
function followLogs() {
  stopLogs();
  $('logConsole').replaceChildren();
  logSource = new EventSource(sseUrl('/api/logs/events', { service: $('logService').value }));
  logSource.onmessage = (e) => appendConsole($('logConsole'), JSON.parse(e.data).line);
  logSource.addEventListener('done', () => {
    appendConsole($('logConsole'), '-- log stream ended --');
    stopLogs();
  });
  logSource.onerror = (e) => {
    // A non-running stack yields an immediate error response.
    if (logSource && logSource.readyState === EventSource.CLOSED) {
      appendConsole($('logConsole'), '!! could not follow logs — is the stack running?', true);
      stopLogs();
    }
  };
  $('followBtn').disabled = true;
  $('stopFollowBtn').disabled = false;
}
function stopLogs() {
  if (logSource) { logSource.close(); logSource = null; }
  $('followBtn').disabled = false;
  $('stopFollowBtn').disabled = true;
}

// ---- navigation -------------------------------------------------------------
const TITLES = { install: 'Install', manage: 'Manage', models: 'Models', logs: 'Logs' };
function showView(key) {
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach((b) =>
    b.classList.toggle('active', b.dataset.view === key));
  $(`view-${key}`).classList.add('active');
  $('topbarTitle').textContent = TITLES[key];
  // The shared job console serves Install/Manage/Models; Logs has its own.
  $('consoleWrap').classList.toggle('hidden', key === 'logs');
  if (key !== 'logs') stopLogs();  // mirror the Tk on_hide: follow only while visible
}

// ---- boot -------------------------------------------------------------------
document.querySelectorAll('.nav-btn').forEach((b) =>
  b.addEventListener('click', () => showView(b.dataset.view)));
document.querySelectorAll('[data-verb]').forEach((b) =>
  b.addEventListener('click', () => runAction(b.dataset.verb)));
document.querySelectorAll('[data-refresh]').forEach((b) =>
  b.addEventListener('click', refreshData));
$('installBtn').onclick = install;
$('reingestBtn').onclick = reingest;
$('applyModelBtn').onclick = applyModel;
$('importBtn').onclick = () => {
  const path = $('importPath').value.trim();
  if (!path) return void appendConsole(jobConsole(), '!! Enter the tarball path first.', true);
  runAction('model_import', { path },
    () => appendConsole(jobConsole(), '>> Select it under Active model and Apply & restart to use it.'));
};
$('exportBtn').onclick = () => {
  const name = $('exportModel').value.trim();
  const dest = $('exportDest').value.trim();
  if (!name || !dest)
    return void appendConsole(jobConsole(), '!! Enter a model and a destination path.', true);
  runAction('model_export', { name, dest });
};
$('followBtn').onclick = followLogs;
$('stopFollowBtn').onclick = stopLogs;

showView('manage');   // provisional (the common case) — corrected once state arrives
(async () => {
  await refreshData();
  showView(state && state.installed ? 'manage' : 'install');
  if (state && state.busy) {        // page (re)loaded mid-job: re-attach
    appendConsole(jobConsole(), `$ (reattached to running job: ${state.job_label})`);
    setBusy(true);
    attachJobStream();
  }
})();
