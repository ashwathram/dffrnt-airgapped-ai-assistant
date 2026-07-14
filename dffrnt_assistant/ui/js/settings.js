// "Thinking" toggle pill above the composer. Controls whether a reasoning
// model's chain-of-thought is rendered as a block or hidden behind a
// "Thinking???" label. The choice persists in localStorage.
import { $ } from './util.js';
import { state } from './state.js';
import { renderMessages } from './chat.js';

function syncThinking() {
  const on = state.showThinking;
  $('thinkingSwitch').classList.toggle('on', on);
  $('thinkingToggle').classList.toggle('on', on);
  $('thinkingText').textContent = on ? 'Thinking on' : 'Thinking off';
  $('thinkingToggle').title = on
    ? 'Thinking is on ??? click to turn off'
    : 'Thinking is off ??? click to turn on';
}

export function initSettings() {
  syncThinking();
  $('thinkingToggle').onclick = () => {
    state.showThinking = !state.showThinking;
    localStorage.setItem('showThinking', state.showThinking ? '1' : '0');
    syncThinking();
    renderMessages(); // reflect the change on existing messages immediately
  };
}
