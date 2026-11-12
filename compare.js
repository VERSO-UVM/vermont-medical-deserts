'use strict';
const C = window.CMP;
const $ = id => document.getElementById(id);
const val = name => document.querySelector(`input[name=${name}]:checked`).value;
const fmt = n => Math.round(n).toLocaleString();
const pct = n => n.toFixed(1) + '%';
const TIME = [[0, '#1a9850', '≤ 10 min'], [11, '#91cf60', '11–15'], [16, '#d9ef8b', '16–20'], [21, '#fee08b', '21–30'],
              [31, '#fc8d59', '31–45'], [46, '#d73027', '46–60'], [61, '#67001f', '> 60 min / none']];

// ---- controls ----
const sel = $('cat');
C.cats.forEach(([k, l]) => sel.add(new Option(l, k)));
$('thr').innerHTML = C.thresholds.map(t => `<label><input type="radio" name="thr" value="${t}"${t === 20 ? ' checked' : ''}>${t} min</label>`).join('');

// ---- map ----
const map = L.map('map', { preferCanvas: true, scrollWheelZoom: false }).setView([43.2, -71.9], 7);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 13, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
const g = C.grid, rows = b64(g.row, Uint16Array), cols = b64(g.col, Uint16Array), cellPop = b64(g.pop, Uint16Array);
const grid = GridLayer(map, g.lat0, g.lon0, g.dlat, g.dlon, Array.from(rows, (r, i) => [r, cols[i]]), 6);
L.geoJSON(C.outlines, { style: { color: '#222', weight: 1.5, fill: false }, interactive: false }).addTo(map);
map.fitBounds([[41.2, -73.6], [45.05, -69.9]]);
const minutes = {};
const mins = (c, v) => minutes[c + v] || (minutes[c + v] = b64(g.min[c][v], Uint8Array));

function render() {
  const c = sel.value, T = +val('thr'), v = val('ver'), ti = C.thresholds.indexOf(T);
  const label = C.cats.find(x => x[0] === c)[1].toLowerCase();

  $('headTitle').textContent = `Residents more than ${T} minutes from ${label === 'dental' ? 'a dentist' : 'the nearest ' + label}`;
  const res = s => C.results[c][s][v];
  const maxPct = Math.max(...C.states.map(([s]) => res(s).all[ti]), 1);
  $('head').innerHTML = '<tr><th>State</th><th>Residents beyond</th><th>% of residents</th><th>% of 65+</th><th>% under 18</th><th>Median drive</th></tr>' +
    C.states.map(([s, name]) => { const r = res(s); return `<tr class="${s === 'VT' ? 'vt' : ''}"><td>${esc(name)}</td>
      <td>${fmt(r.all_n[ti])}</td><td>${pct(r.all[ti])}<span class="bar" style="width:${Math.round(60 * r.all[ti] / maxPct)}px"></span></td>
      <td>${pct(r.o65[ti])}</td><td>${pct(r.u18[ti])}</td><td>${r.median >= 999 ? 'n/a' : r.median.toFixed(1) + ' min'}</td></tr>`; }).join('');
  $('headNote').textContent = v === 'own'
    ? 'Counting only providers in each resident’s own state.'
    : 'Counting providers anywhere in VT, NH or MA, or within 30 miles of them in NY, ME, CT or RI.';

  $('cross').innerHTML = `<tr><th>State</th><th>Beyond ${T} min, in-state only</th><th>Beyond ${T} min, incl. neighbours</th><th>Residents helped by cross-border care</th></tr>` +
    C.states.map(([s, name]) => { const o = C.results[c][s].own, r = C.results[c][s].region;
      return `<tr class="${s === 'VT' ? 'vt' : ''}"><td>${esc(name)}</td><td>${pct(o.all[ti])}</td><td>${pct(r.all[ti])}</td><td>${fmt(o.all_n[ti] - r.all_n[ti])}</td></tr>`; }).join('');

  const m = mins(c, v);
  grid.draw(i => rgba(pick(TIME, m[i]), cellPop[i] < 1 ? 0.08 : m[i] > T ? 0.8 : 0.4));
  $('legend').innerHTML = `<span style="width:auto;height:auto;margin:0">Drive time (within ${T} min lighter; faint = no residents):</span>` +
    TIME.map(([, col, l]) => `<div><span style="background:${col}"></span>${l}</div>`).join('');
}

// supply table does not depend on the controls
const S = C.supply;
const supplyRows = [
  ['Primary care clinicians per 10,000', s => S[s].pc.toFixed(1)],
  ['Mental health clinicians per 10,000', s => S[s].mh.toFixed(1)],
  ['Dentists per 10,000', s => S[s].dent.toFixed(1)],
  ['Pharmacists per 10,000', s => S[s].rx.toFixed(1)],
  ['Acute & critical-access hospitals', s => S[s].hosp],
  ['Certified hospital beds per 1,000', s => S[s].beds.toFixed(2)],
  ['Safety-net clinic sites per 100,000', s => S[s].sn.toFixed(1)],
  ['Residents in primary care shortage areas', s => pct(C.hpsa.pc[s])],
  ['Residents in dental shortage areas', s => pct(C.hpsa.dent[s])],
  ['Residents in mental health shortage areas', s => pct(C.hpsa.mh[s])],
  ['Population (2020)', s => fmt(C.states.find(x => x[0] === s)[2])],
];
$('supply').innerHTML = '<tr><th></th>' + C.states.map(([, n]) => `<th>${esc(n)}</th>`).join('') + '</tr>' +
  supplyRows.map(([l, f]) => `<tr><td>${l}</td>${C.states.map(([s]) => `<td>${f(s)}</td>`).join('')}</tr>`).join('');

sel.onchange = render;
document.querySelectorAll('input[name=thr],input[name=ver]').forEach(r => { r.onchange = render; });
render();
