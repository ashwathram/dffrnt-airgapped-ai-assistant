// Entry point: hydrate icons, wire navigation, boot the default view.
// Each sibling module owns one view/concern; this file only coordinates them.
import { $ } from './util.js';
import { hydrateIcons } from './icons.js';
import { state } from './state.js';
import { renderMessages, initComposer, clearChat, loadConversation } from './chat.js';
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

$('navNewChat').onclick = newChat;
$('navLibrary').onclick = () => setView('library');

renderMessages();
