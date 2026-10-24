/**
 * HelpChat.js — the "Emergency help" button (on every view) and its chat panel.
 *
 * The panel always shows the 911 call bar and the first-aid steps. They are
 * written here, not by the AI, so they are there with no key, no internet or
 * a slow answer. Below them, a chat with Claude (lib/assistant.js) walks the
 * user through it.
 *
 * Zero persistence: the conversation and the key live in memory and die with
 * the page. "New chat" clears the conversation without a reload (a reload
 * drops the Bluetooth link during the demo). No device data is sent.
 */
import { GREETING, streamReply, setApiKey, hasApiKey } from '../lib/assistant.js';

const STARTERS = [
  'They collapsed or seem confused',
  "They're dizzy or feel sick",
  'How do I cool someone down fast?',
];

const FALLBACK = "Follow the steps above, and call 911 if they're confused or collapsed.";

let _mounted = false;

export function mountHelpChat() {
  if (_mounted) return;
  _mounted = true;
  document.body.insertAdjacentHTML('beforeend', _template());

  const fab      = document.getElementById('help-fab');
  const dialog   = document.getElementById('help-chat');
  const scroller = dialog.querySelector('.help-chat__scroll');
  const steps    = dialog.querySelector('.help-chat__steps');
  const log      = dialog.querySelector('.help-chat__log');
  const starters = dialog.querySelector('.help-chat__starters');
  const keyForm  = dialog.querySelector('.help-chat__key');
  const keyInput = keyForm.querySelector('input');
  const form     = dialog.querySelector('.help-chat__form');
  const input    = form.querySelector('textarea');
  const sendBtn  = form.querySelector('button[type="submit"]');

  let history = [];   // [{ role, content }]: what the API sees
  let busy = false;   // one reply at a time
  let gen = 0;        // bumped by New chat, so a late reply can't land in the new one
  let ctrl = null;    // aborts the reply in flight

  function addMsg(kind, text) {
    const el = document.createElement('p');
    el.className = `msg msg--${kind}`;
    el.textContent = text;
    log.appendChild(el);
    return el;
  }
  const nearBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
  const toBottom   = () => { scroller.scrollTop = scroller.scrollHeight; };

  // Key form until a key is in; starters until the first message.
  function sync() {
    const ready = hasApiKey();
    keyForm.hidden  = ready;
    form.hidden     = !ready;
    starters.hidden = !ready || history.length > 0;
    sendBtn.disabled = busy;
  }

  function reset() {
    gen++;
    if (ctrl) ctrl.abort();
    ctrl = null;
    busy = false;
    history = [];
    log.replaceChildren();
    addMsg('bot', GREETING);
    steps.open = true;
    input.value = '';
    sync();
  }

  async function ask(raw) {
    const text = raw.trim();
    if (!text || busy) return;
    if (!hasApiKey()) { sync(); keyInput.focus(); return; }

    const mine = gen;
    busy = true;
    if (!history.length) steps.open = false;   // make room for the chat
    history.push({ role: 'user', content: text });
    sync();

    const userEl = addMsg('user', text);
    const bubble = addMsg('bot', '…');
    bubble.classList.add('is-waiting');
    bubble.setAttribute('aria-busy', 'true');
    toBottom();

    ctrl = new AbortController();
    let got = '';
    let stopReason = null;
    let error = null;
    try {
      ({ stopReason } = await streamReply(history, {
        signal: ctrl.signal,
        onText: chunk => {
          if (mine !== gen) return;
          got += chunk;
          const stick = nearBottom();
          bubble.classList.remove('is-waiting');
          bubble.textContent = _plain(got);
          if (stick) toBottom();
        },
      }));
    } catch (err) {
      error = err;
    }
    if (mine !== gen) return;                   // New chat already cleared everything
    busy = false;
    ctrl = null;
    bubble.removeAttribute('aria-busy');

    if (got.trim()) {
      history.push({ role: 'assistant', content: got });
      if (error) addMsg('note', `The answer was cut off. ${FALLBACK}`);
    } else {
      // Nothing came back: take the question out of the history and give it
      // back, so Send tries again without a duplicate bubble.
      history.pop();
      bubble.remove();
      userEl.remove();
      if (!input.value) { input.value = text; _fit(input); }
      if (error?.kind === 'auth') setApiKey('');
      addMsg('note', _errorText(error, stopReason));
      steps.open = true;
    }
    sync();
    toBottom();
    if (!form.hidden) input.focus();
  }

  // ── events ──────────────────────────────────────────────────────────
  fab.addEventListener('click', () => {
    sync();
    dialog.showModal();
    fab.setAttribute('aria-expanded', 'true');
  });
  dialog.addEventListener('close', () => {
    fab.setAttribute('aria-expanded', 'false');
    fab.focus();
  });
  dialog.addEventListener('click', e => {
    const action = e.target.closest('[data-help]')?.dataset.help;
    if (action === 'close') dialog.close();
    else if (action === 'new') reset();
    else if (action === 'starter') ask(e.target.closest('[data-help]').textContent);
  });

  form.addEventListener('submit', e => {
    e.preventDefault();
    if (busy) return;
    const text = input.value;
    input.value = '';
    _fit(input);
    ask(text);
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      form.requestSubmit();
    }
  });
  input.addEventListener('input', () => _fit(input));

  keyForm.addEventListener('submit', e => {
    e.preventDefault();
    setApiKey(keyInput.value);
    keyInput.value = '';
    sync();
    if (hasApiKey()) input.focus();
  });

  reset();
}

// Grow the box with the text, up to its CSS max-height.
function _fit(el) {
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight + el.offsetHeight - el.clientHeight}px`;
}

// The prompt asks for plain text; drop stray markdown if some comes back anyway.
function _plain(text) {
  return text.replace(/\*\*|__/g, '').replace(/^#{1,6}\s+/gm, '');
}

function _errorText(err, stopReason) {
  if (!err) {
    return stopReason === 'refusal'
      ? `The assistant couldn't answer that. ${FALLBACK}`
      : `The assistant didn't answer. Press Send to try again. ${FALLBACK}`;
  }
  switch (err.kind) {
    case 'auth':    return 'The API key was not accepted. Paste a new one below. The steps above still apply.';
    case 'offline': return `Can't reach the assistant. Check the internet connection, then press Send to try again. ${FALLBACK}`;
    case 'busy':    return `The assistant is busy. Press Send to try again in a moment. ${FALLBACK}`;
    default:        return `${err.message ?? 'Something went wrong.'} ${FALLBACK}`;
  }
}

function _template() {
  return `
<button type="button" id="help-fab" class="help-fab" aria-haspopup="dialog" aria-controls="help-chat" aria-expanded="false">
  <span class="help-fab__icon" aria-hidden="true">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"><path d="M12 4v16M4 12h16"/></svg>
  </span>
  Emergency help
</button>

<dialog id="help-chat" class="help-chat" aria-labelledby="help-chat-title">
  <div class="help-chat__head">
    <h2 id="help-chat-title">Emergency help</h2>
    <div class="help-chat__head-btns">
      <button type="button" class="btn btn--secondary btn-sm" data-help="new">New chat</button>
      <button type="button" class="btn btn--secondary btn-sm" data-help="close" autofocus>Close</button>
    </div>
  </div>

  <div class="help-chat__call status--act">
    <p><strong>Confused, collapsed or not making sense?</strong> Call 911 now, then start cooling them.</p>
    <a class="btn help-chat__call-btn" href="tel:911">Call 911</a>
  </div>

  <div class="help-chat__scroll">
    <details class="help-chat__steps" open>
      <summary>First aid while you wait</summary>
      <ol>
        <li>Call 911 if they are confused, collapsed or can't drink.</li>
        <li>Get them out of the sun. Take off extra layers and gear.</li>
        <li>Cool them fast: cold water up to the neck if you can. If not, soak them with cold water and fan them, with ice or cold wet towels on the neck, armpits and groin.</li>
        <li>Sips of cool water only if they are awake and can swallow.</li>
        <li>Stay with them and keep cooling until help arrives.</li>
      </ol>
      <p>Go by how they look, not by EMB.R's number. It is an estimate and can lag behind.</p>
    </details>
    <div class="help-chat__log" role="log" aria-live="polite" aria-label="Conversation"></div>
    <div class="help-chat__starters" hidden>
      ${STARTERS.map(s => `<button type="button" data-help="starter">${s}</button>`).join('')}
    </div>
  </div>

  <form class="help-chat__key" hidden>
    <p>The AI helper isn't set up on this screen yet. The steps above still apply.</p>
    <label for="help-key">Anthropic API key</label>
    <div class="help-chat__row">
      <input id="help-key" type="password" autocomplete="off" spellcheck="false" placeholder="sk-ant-…" required>
      <button type="submit" class="btn btn--primary btn-sm">Use key</button>
    </div>
    <p class="help-chat__keynote">Kept in memory until this page closes. Never saved.</p>
  </form>

  <form class="help-chat__form" hidden>
    <label for="help-input" class="sr-only">Message</label>
    <textarea id="help-input" rows="1" placeholder="Type what's happening"></textarea>
    <button type="submit" class="btn btn--primary">Send</button>
  </form>

  <p class="help-chat__fine">AI helper: it can be wrong and is not medical advice. What you type goes to Anthropic (Claude) to get an answer. Nothing is saved.</p>
</dialog>`;
}
