/**
 * weather.js — fetches ambient temperature and humidity from Open-Meteo.
 *
 * Open-Meteo is free, requires no API key, and is GDPR-friendly.
 * We send only a lat/lon — no user identity.
 *
 * Refresh interval: 5 minutes.
 */

import { setWeather } from './datastore.js';

const REFRESH_MS = 5 * 60 * 1000;
let _timer = null;
let _lat = null;
let _lon = null;

/**
 * Start periodic weather fetching.
 * Coordinates default to a mid-US fallback; call with real coords for demo.
 */
export function startWeatherFetch(lat = 39.5, lon = -98.35) {
  _lat = lat;
  _lon = lon;
  _fetch();
  _timer = setInterval(_fetch, REFRESH_MS);
}

export function stopWeatherFetch() {
  if (_timer) { clearInterval(_timer); _timer = null; }
}

/**
 * Try to get the user's rough location and start fetching.
 * Gracefully falls back to the default coords if permission is denied.
 */
export function startWeatherWithGeolocation() {
  if (!navigator.geolocation) {
    startWeatherFetch();
    return;
  }
  navigator.geolocation.getCurrentPosition(
    pos => startWeatherFetch(pos.coords.latitude, pos.coords.longitude),
    _err => startWeatherFetch(), // fallback on denial
    { maximumAge: 600_000, timeout: 5000 }
  );
}

async function _fetch() {
  if (_lat === null || _lon === null) return;
  try {
    const url =
      `https://api.open-meteo.com/v1/forecast` +
      `?latitude=${_lat}&longitude=${_lon}` +
      `&current=temperature_2m,relative_humidity_2m` +
      `&temperature_unit=celsius` +
      `&wind_speed_unit=ms` +
      `&forecast_days=1`;

    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const tempC    = data?.current?.temperature_2m;
    const humidity = data?.current?.relative_humidity_2m;

    if (tempC != null && humidity != null) {
      setWeather(tempC, humidity);
    }
  } catch (err) {
    console.warn('Weather fetch failed:', err.message);
    // Non-fatal — the UI shows "—" for weather fields
  }
}
