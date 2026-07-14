// Entry point: hydrate icons, wire navigation, boot the default view.
//
// Module layout:
//   util.js     - DOM/text helpers
//   icons.js    - inline SVG icon set + hydration
//   state.js    - shared app state
//   api.js      - fetch wrappers for the backend
//   sidebar.js  - sidebar (collapse, chat list)
//   chat.js     - chat view (messages, composer, send)
//   library.js  - document library (list, delete)
//   upload.js   - upload modal (validation, per-file tags, dup handling)
//   settings.js - thinking toggle pill above the composer
//   tags.js     - tag manager modal (taxonomy CRUD)
//   app.js      - this file: coordinates views + boot
import { $ } from './util.js';
import { hydrateIcons } from './icons.js';
import { state } from './state.js';
import { renderMessages, initComposer, clearChat, loadConversation, initWorkflowToggles } from './chat.js';
import { initSidebar } from './sidebar.js';
import { loadDocuments, initLibrary } from './library.js';
import { initUpload } from './upload.js';
import { initSettings } from './settings.js';
import { initTags } from './tags.js';
import { initScope, renderScope } from './scope.js';
import { initConfirm } from './confirm.js';

function setView(view) {
  state.view = view;
  $('chatPanel').classList.toggle('hidden', view !== 'chat');
  $('libraryPanel').classList.toggle('hidden', view !== 'library');
  $('chatWorkflowToggles').classList.toggle('hidden', view !== 'chat');
  $('navLibrary').classList.toggle('active', view === 'library');
  $('topbarTitle').textContent = view === 'library'
    ? 'Document Library'
    : (state.messages.find((m) => m.role === 'user') || {}).content
      || (state.messages.length ? 'Conversation' : 'New conversation');
  if (view === 'library') loadDocuments();
  if (view === 'chat') renderScope(); // reflect taxonomy edits made elsewhere
}

function newChat() {
  clearChat();
  setView('chat');
}

hydrateIcons();
initSidebar({ onSelect: (id) => { setView('chat'); loadConversation(id); } });
initComposer();
initLibrary();
initUpload();
initSettings();
initTags();
initConfirm();
initScope();
initWorkflowToggles({ renderScope });

$('navNewChat').onclick = newChat;
$('navLibrary').onclick = () => setView('library');

renderMessages();
