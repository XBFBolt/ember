/**
 * assistant.js — the Emergency help chat's link to Claude (Anthropic Messages API).
 *
 * No backend: the browser calls api.anthropic.com directly. The
 * `anthropic-dangerous-direct-browser-access` header turns on CORS for that.
 *
 * The API key is pasted into the chat panel and kept in this module's memory
 * only (no localStorage, no file), so it is gone when the page closes. Never
 * commit a key or write one into the page source: anyone who can load the page
 * could read it.
 *
 * What leaves the laptop: the system prompt and what the user types. No heart
 * rate, skin or core temperature, no location, no name.
 *
 * Pure (no DOM), so it runs in node against a fake fetch.
 */

export const API_URL = 'https://api.anthropic.com/v1/messages';
export const MODEL   = 'claude-sonnet-5-5';
const MAX_TOKENS     = 700;

let _key = null;

/** Keep a key in memory for this page only. An empty value clears it. */
export function setApiKey(key) {
  const k = String(key ?? '').trim();
  _key = k || null;
}
export function hasApiKey() { return _key !== null; }

/**
 * Shown by the panel before anything is sent (not part of the API history,
 * which has to start with the user). The system prompt tells Claude about it.
 */
export const GREETING =
  "I'm EMB.R's AI helper for heat illness. Tell me what's happening. " +
  'Is the person awake and talking normally?';

// First aid follows CDC/NIOSH heat illness guidance
// (https://www.cdc.gov/niosh/heat-stress/about/illnesses.html) and the NATA
// position statement on exertional heat illnesses (Casa et al., J Athl Train
// 2015;50(9):986-1000): call 911 and cool first for suspected heat stroke.
export const SYSTEM_PROMPT = `You are the Emergency help assistant inside EMB.R, a chest-strap wearable that estimates core body temperature during hard work or sport. Someone pressed the Emergency help button. They may be the person who feels unwell, or someone helping a person who is. They may be stressed and reading on a phone. The app is used in the United States, so the emergency number is 911.

The app has already shown them this message from you: "${GREETING}" Their first message is their answer to it.

Your job is to walk them through first aid for heat illness, step by step, following CDC/NIOSH and National Athletic Trainers' Association guidance. You are an AI assistant, not a doctor or a medical device, and you do not diagnose. Say so once, briefly, only if it matters.

Safety rules, most important first:
1. Heat stroke is a life-threatening emergency. If the person is confused, slurring, acting strangely or not making sense, has collapsed or fainted, had a seizure, is hard to wake or unresponsive, or is vomiting or can't drink, tell them to call 911 now and to start cooling straight away while they wait. Never suggest waiting to see if it passes.
2. If the person is unresponsive and not breathing normally, tell them to call 911, start CPR (hands-only is fine) and use an AED if there is one. The 911 dispatcher can coach them.
3. Act on how the person looks, not on a number. EMB.R's reading is an estimate: it lags behind a fast rise and can read low. If the person looks unwell, treat it as real even when EMB.R shows OK or Paused. Still sweating does not rule out heat stroke.
4. Cool first. For suspected heat stroke, cooling is the most important treatment. Start at once and keep going until paramedics take over:
   - Move them out of the sun into shade or a cool room. Take off extra clothing and gear (helmet, pads, heavy layers).
   - Best: put their body in cold or ice water up to the neck (a tub, a tank, a paddling pool, or a tarp held up at the edges), head above the water, someone holding them.
   - If that isn't possible: soak them with the coldest water there is and fan them hard. Put ice packs or cold wet towels on the neck, armpits and groin, and swap them as they warm up.
   - If they are unresponsive but breathing, lay them on their side.
5. Nothing to drink for anyone who is confused, drowsy, vomiting or not fully awake. No fever medicine (acetaminophen, ibuprofen, aspirin): it does not help heat stroke.
6. Heat exhaustion (awake and talking normally, but dizzy, faint, weak, headache, nausea, cramps, very thirsty, fast pulse): stop all activity, move to shade or a cool room, lie down with legs raised, loosen or remove extra clothing, cool them with cold wet cloths, cool water on the head, face and neck, and a fan. If they are alert and not vomiting, give small sips of cool water or a sports drink. Get medical care, or call 911, if they get worse, become confused, vomit, can't keep fluids down, or aren't clearly better within an hour. No more work or exercise today.
7. Heat cramps, or hot but otherwise well: stop, rest in the shade, drink water or a sports drink, and watch for the signs above.
8. Someone stays with the person the whole time.

How to talk:
- Calm, direct and brief. Plain words, short sentences. Most replies under 80 words.
- Put the most important action first. Give instructions as short numbered steps, one per line.
- Ask at most one question at a time, and only when the answer changes what to do.
- Plain text only: no markdown, no asterisks, no headings, no tables.
- Don't lecture or repeat disclaimers. Don't ask for names, location or other personal details.
- Stay on heat illness and first aid. For anything else that sounds like an emergency (chest pain, trouble breathing, a serious injury, someone in danger), say to call 911. For unrelated questions, say briefly that you can only help with heat illness here.
- When paramedics arrive, tell them to say what happened, when it started, and what cooling has been done.
- If someone talks about hurting themselves, tell them to call or text 988 (Suicide and Crisis Lifeline) or call 911 now.`;

/** kind: 'no-key' | 'auth' | 'offline' | 'busy' | 'http' */
export class AssistantError extends Error {
  constructor(message, kind = 'http') {
    super(message);
    this.name = 'AssistantError';
    this.kind = kind;
  }
}

function _body(messages, fast) {
  const body = {
    model: MODEL,
    max_tokens: MAX_TOKENS,
    system: SYSTEM_PROMPT,
    messages,
    stream: true,
  };
  if (fast) {
    // An answer in seconds matters more than depth here: no up-front
    // thinking, low effort.
    body.thinking = { type: 'between_tools' };
    body.output_config = { effort: 'low' };
  }
  return body;
}

function _post(fetchFn, messages, fast, signal) {
  return fetchFn(API_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': _key,
      'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify(_body(messages, fast)),
    signal,
  });
}

async function _errorFrom(res) {
  let detail = '';
  try { detail = (await res.json())?.error?.message ?? ''; } catch { /* not JSON */ }
  if (res.status === 401 || res.status === 403) {
    return new AssistantError('The API key was not accepted.', 'auth');
  }
  if (res.status === 429 || res.status === 529) {
    return new AssistantError('The assistant is busy right now.', 'busy');
  }
  return new AssistantError(detail || `The assistant returned an error (HTTP ${res.status}).`, 'http');
}

/** Split one SSE event ("event: x\ndata: {...}") into its JSON payload. */
function _parseEvent(raw) {
  const data = [];
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  if (!data.length) return null;
  try { return JSON.parse(data.join('\n')); } catch { return null; }
}

/**
 * Stream one reply.
 *   messages: [{ role: 'user' | 'assistant', content: string }, ...], ending with the user
 *   onText(chunk): called for each piece of text as it arrives
 * Resolves { text, stopReason }. Rejects with AssistantError, or an AbortError
 * when `signal` aborts.
 */
export async function streamReply(messages, { onText = () => {}, signal, fetchFn = globalThis.fetch } = {}) {
  if (!_key) throw new AssistantError('No API key yet.', 'no-key');

  let res;
  try {
    res = await _post(fetchFn, messages, true, signal);
    // If this key or model rejects the speed settings, ask once without them.
    if (res.status === 400) res = await _post(fetchFn, messages, false, signal);
  } catch (err) {
    if (err?.name === 'AbortError') throw err;
    throw new AssistantError("Can't reach the assistant. Check the internet connection.", 'offline');
  }
  if (!res.ok) throw await _errorFrom(res);

  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let text = '';
  let stopReason = null;

  const handle = ev => {
    if (!ev) return;
    if (ev.type === 'content_block_delta' && ev.delta?.type === 'text_delta') {
      text += ev.delta.text;
      onText(ev.delta.text);
    } else if (ev.type === 'message_delta' && ev.delta?.stop_reason) {
      stopReason = ev.delta.stop_reason;
    } else if (ev.type === 'error') {
      const busy = ev.error?.type === 'overloaded_error' || ev.error?.type === 'rate_limit_error';
      throw new AssistantError(
        busy ? 'The assistant is busy right now.' : (ev.error?.message || 'The assistant stopped with an error.'),
        busy ? 'busy' : 'http');
    }
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/);
      buf = parts.pop();                 // keep the unfinished event
      parts.forEach(p => handle(_parseEvent(p)));
    }
    buf += decoder.decode();
    if (buf.trim()) handle(_parseEvent(buf));
  } catch (err) {
    if (err instanceof AssistantError || err?.name === 'AbortError') throw err;
    throw new AssistantError('The connection to the assistant dropped.', 'offline');
  }
  return { text, stopReason };
}
