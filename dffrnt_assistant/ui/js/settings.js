// Composer settings dropdown. Currently: a "Show thinking" toggle that controls
// whether a reasoning model's chain-of-thought is rendered as a block or hidden
// behind a "Thinking…" label. The choice persists in localStorage.
import { $ } from './util.js';
import { state } from './state.js';
import { renderMessages } from './chat.js';

function syncSwitch() {
  $('thinkingSwitch').classList.toggle('on', state.showThinking);
}

export function initSettings() {
  syncSwitch();
  const menu = $('settingsMenu');

  $('settingsBtn').onclick = (e) => {
    e.stopPropagation();
    menu.classList.toggle('hidden');
  };

  $('toggleThinking').onclick = () => {
    state.showThinking = !state.showThinking;
    localStorage.setItem('showThinking', state.showThinking ? '1' : '0');
    syncSwitch();
    renderMessages(); // reflect the change on existing messages immediately
  };

  // Close the menu when clicking anywhere outside the composer settings group.
  document.addEventListener('click', (e) => {
    if (!menu.classList.contains('hidden') && !e.target.closest('.row-left')) {
      menu.classList.add('hidden');
    }
  });
}
