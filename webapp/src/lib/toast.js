/**
 * toast.js — one short message at the bottom of the screen.
 * Used so a judge's click on a demo button gets a visible response.
 */
let _el = null;
let _timer = null;

export function toast(text, ms = 2600) {
  if (!_el) {
    _el = document.createElement('div');
    _el.className = 'toast';
    _el.setAttribute('role', 'status');
    _el.setAttribute('aria-live', 'polite');
    document.body.appendChild(_el);
  }
  _el.textContent = text;
  _el.classList.add('is-on');
  clearTimeout(_timer);
  _timer = setTimeout(() => _el.classList.remove('is-on'), ms);
}
