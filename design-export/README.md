# Ember design export

Plain HTML, CSS and JavaScript for the three Ember views. No build step, no framework.

```
index.html   markup for Personal, Coach and Supervisor + the view switcher
ember.css    design tokens and every component style
ember.js     render functions, status rules, CSV parser, sample data
```

Open `index.html` in Chrome. Switch views with the tabs or the URL:

- `index.html?view=personal&status=watch` (status: `baseline`, `ok`, `watch`, `act`, `paused`)
- `index.html?view=coach`
- `index.html?view=supervisor`

## Wiring in live data

Everything you need is on `window.Ember`:

```js
// one line of the firmware's serial log (after sending START)
const row = Ember.parseCsvLine(line);
const status = Ember.statusFromRow(row);   // 'paused' | 'baseline' | 'act' | 'watch' | 'ok'

Ember.renderPersonal({
  status,
  ct: row.ct_est,
  half: (row.ct_hi - row.ct_lo) / 2,       // the calibrated ± from conformal_table.h
  trend: '↑ 0.3° / 10 min', rise: '+1.0°',
  action: '...', forecast: '...', forecastNote: '...',
  breakWhen: 'Now', breakUrgent: true, breakDetail: '...',
  water: 'Now', waterUrgent: true, waterDetail: '...',
  btn: 'Start my break', hr: row.hr, motion: row.act_rms > 0.35 ? 'moving' : 'still',
  skinNow: row.skin_c.toFixed(1),
  chart: { core: [...], lo: [...], hi: [...], skin: [...] }   // last 30 min, oldest first
});
```

`renderCoach({ players, log })` and `renderSupervisor({ events, crew })` take the shapes shown in the `SAMPLE_COACH` and `SAMPLE_SUPERVISOR` objects at the bottom of `ember.js`.

## Status rules (in `statusFromRow`)

| Status | When |
| --- | --- |
| Paused | firmware state is REFUSE (2) |
| Setting up | no-baseline flag (0x20) is set |
| Act now | estimate ≥ 38.5°C (matches `CT_ALERT_C`) |
| Watch | estimate ≥ 38.0°C |
| OK | otherwise |

Never display `kalman_half`. The ± on screen comes from `ct_lo` / `ct_hi`.

## Styling

Each status is a class (`status--ok`, `status--watch`, `status--act`, `status--paused`, `status--baseline`) that sets CSS variables. Put it on any container and its children pick up the right colors. All colors live in `:root` at the top of `ember.css`.

The range bar is pure CSS: set `--lo`, `--hi` and `--est` on `.range` as plain numbers in °C.

## Placeholders to replace

- Names, numbers and the event log are sample data.
- The break schedules (20 on / 5 off, 45 on / 15 off) are placeholders. Take them from a published heat-index table (OSHA or NIOSH) before the demo.
- The "How sure is Ember?" link points nowhere yet; it is meant for the coverage table.
