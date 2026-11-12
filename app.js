'use strict';
const D = window.DATA, RD = window.ROADS;
const $ = id => document.getElementById(id);
const val = name => document.querySelector(`input[name=${name}]:checked`).value;
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const b64 = (s, T) => new T(Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer);
const POP = Object.fromEntries(Object.entries(window.POP).map(([k, v]) => [k, b64(v, Uint16Array)]));
const memo = {}, cached = (k, f) => memo[k] || (memo[k] = f());

const COLORS = { mh: '#7b3294', pc: '#1a9850', dent: '#2c7bb6', rx: '#d7191c', rehab: '#fdae61', spec: '#4d4d4d',
                 hosp: '#b2182b', nurse: '#41b6c4', comm: '#a6611a', sn: '#00897b', other: '#999' };
const GROUPS = { all: 'All residents', o65: 'Age 65+', u18: 'Under 18' };
const TIME = [[0, '#1a9850', '≤ 10 min'], [11, '#91cf60', '11–15'], [16, '#d9ef8b', '16–20'], [21, '#fee08b', '21–30'],
              [31, '#fc8d59', '31–45'], [46, '#d73027', '46–60'], [61, '#67001f', '> 60 min / none']];
const OVERLAP = [[0, '#d7301f', '0 (hole)'], [1, '#fdcc8a', '1'], [2, '#c7e9c0', '2–3'], [4, '#74c476', '4–9'], [10, '#238b45', '10+']];
const AGE = [[0, '#f1eef6', 'under 30'], [30, '#d0d1e6', '30–34'], [35, '#a6bddb', '35–39'], [40, '#74a9cf', '40–44'],
             [45, '#3690c0', '45–49'], [50, '#0570b0', '50–54'], [55, '#034e7b', '55+']];
const PEOPLE = [[1,'#f9a8c9', '1–24'], [25, '#f768a1', '25–99'], [100, '#c51b8a', '100–499'], [500, '#7a0177', '500+']];
const pick = (scale, n) => scale.reduce((c, [t, col]) => (n >= t ? col : c), scale[0][1]);

// ---- controls ----
const sel = $('cat');
sel.add(new Option('All categories (NPPES)', 'all'));
D.cats.forEach(([k, l]) => sel.add(new Option(l, k)));
sel.value = 'pc';
$('thr').innerHTML = RD.thresholds.map(t => `<label><input type="radio" name="thr" value="${t}"${t === 20 ? ' checked' : ''}>${t} min</label>`).join('');
$('age').innerHTML = Object.entries(GROUPS).map(([k, l], i) => `<label><input type="radio" name="age" value="${k}"${i ? '' : ' checked'}>${l}</label>`).join('');

// ---- map ----
const map = L.map('map', { preferCanvas: true }).setView([43.9, -72.6], 8);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }).addTo(map);
const townLayer = L.geoJSON(window.TOWNS, { style: { color: '#333', weight: 0.7, fill: false }, interactive: false }).addTo(map);
const townBounds = {};
townLayer.eachLayer(l => { townBounds[l.feature.properties.name] = l.getBounds(); });
const ptLayer = L.layerGroup().addTo(map), snLayer = L.layerGroup(), hpsaLayer = L.layerGroup();
let gridImg = null;

// grid cells -> row/col of one raster drawn in Web Mercator so it lines up with the tiles
const G = D.grid, LAT0 = 42.72, LON0 = -73.44, PX = 4;
const rc = G.cells.map(([la, lo]) => [Math.round((la - LAT0) / G.dlat), Math.round((lo - LON0) / G.dlon)]);
const NR = Math.max(...rc.map(r => r[0])) + 1, NC = Math.max(...rc.map(r => r[1])) + 1;
const merc = la => Math.log(Math.tan(Math.PI / 4 + la * Math.PI / 360));
const M0 = merc(LAT0), M1 = merc(LAT0 + NR * G.dlat), H = NR * PX;
const ypx = la => (M1 - merc(la)) / (M1 - M0) * H;
const rowY = Array.from({ length: NR + 1 }, (_, r) => ypx(LAT0 + r * G.dlat));
const gridBounds = [[LAT0, LON0], [LAT0 + NR * G.dlat, LON0 + NC * G.dlon]];

function drawGrid(colorOf) {
  const cv = document.createElement('canvas');
  cv.width = NC * PX; cv.height = H;
  const ctx = cv.getContext('2d');
  rc.forEach(([r, c], i) => {
    const s = colorOf(i);
    if (!s) return;
    ctx.fillStyle = s;
    ctx.fillRect(c * PX, Math.floor(rowY[r + 1]), PX, Math.ceil(rowY[r]) - Math.floor(rowY[r + 1]));
  });
  if (gridImg) map.removeLayer(gridImg);
  gridImg = L.imageOverlay(cv.toDataURL(), gridBounds, { className: 'grid-img', interactive: false }).addTo(map);
}
const rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;

// ---- markers ----
const isSN = l => l.p[0][1] === 'sn';
function popup(l, list) {
  const items = list.slice(0, 200).map(p =>
    `<li>${esc(p[0])} <span class="muted">${esc(p[2])}${p[4] ? ` · ${p[4].toLocaleString()} Medicare patients (2024)` : ''}</span></li>`).join('');
  return `<b>${esc(l.addr)}</b>${l.t ? '<br>Town: ' + esc(l.t) : ''}${l.a ? '<br><i>approximate (ZIP centroid)</i>' : ''}` +
         `<br>${list.length} in selection${list.length > 200 ? ' (first 200 shown)' : ''}<ol class="popup-list">${items}</ol>`;
}
D.locs.filter(isSN).forEach(l => L.circleMarker(l.ll, { radius: 6, color: '#fff', weight: 1.5, fillColor: COLORS.sn, fillOpacity: 1 })
  .bindPopup(() => popup(l, l.p)).addTo(snLayer));
D.schools.forEach(s => L.circleMarker(s.ll, { radius: 5, color: COLORS.sn, weight: 2, fillOpacity: 0 })
  .bindPopup(`<b>${esc(s.name)}</b><br>${esc(s.addr)}<br><i>${esc(s.setting)}-based site</i>`).addTo(snLayer));

function keep(c, who) {
  return p => (c === 'all' ? p[1] !== 'sn' : p[1] === c) &&
    (who === 'all' || (who === 'org' ? p[3] === 2 : p[3] === 1 && (who === 'ind' || p[4] > 0)));
}

// ---- render ----
function render() {
  const c = sel.value;
  // "Billed Medicare" only where Part B data is meaningful; safety-net sites are organizations only
  const allowed = { org: true, ind: c !== 'sn', mcr: c === 'all' || D.mcrCats.includes(c) };
  document.querySelectorAll('input[name=who]').forEach(r => { r.disabled = r.value !== 'all' && !allowed[r.value]; });
  if ($('who').querySelector('input:checked').disabled) document.querySelector('input[name=who][value=all]').checked = true;
  const who = val('who'), T = +val('thr'), mode = val('mode'), age = val('age'), pop = POP[age];
  $('whoNote').textContent = who === 'mcr'
    ? 'Only clinicians who billed Medicare Part B in their own name in 2024. Clinicians at health centers, rural health clinics and hospital outpatient departments usually bill through the facility and are left out.'
    : allowed.mcr ? '' : '"Billed Medicare" is not available for this category: Medicare data says little about it.';

  const ci = RD.combos.indexOf(c + '|' + who), ti = RD.thresholds.indexOf(T);
  const near = cached('n' + ci, () => b64(RD.nearest[ci], Uint8Array));
  const cnt = cached(`c${ci}_${ti}`, () => b64(RD.counts[ci][ti], Uint8Array));

  if (mode === 'none') { if (gridImg) map.removeLayer(gridImg); gridImg = null; }
  else drawGrid(i => {
    if (mode === 'people') return near[i] > T && pop[i] >= 1 ? rgba(pick(PEOPLE, pop[i]), 0.85) : null;
    // drive time where the selected group lives; squares with nobody in the group stay faint
    if (mode === 'time') return rgba(pick(TIME, near[i]), pop[i] < 1 ? 0.07 : near[i] > T ? 0.8 : 0.35);
    if (mode === 'overlap') return rgba(pick(OVERLAP, cnt[i]), 0.55);
    if (mode === 'age') return POP.age10[i] ? rgba(pick(AGE, POP.age10[i] / 10), 0.75) : null;
    return near[i] > T ? rgba(OVERLAP[0][1], 0.55) : null;
  });

  ptLayer.clearLayers();
  const f = keep(c, who);
  let nProv = 0, nLoc = 0;
  for (const l of D.locs) {
    const list = l.p.filter(f);
    if (!list.length) continue;
    nProv += list.length; nLoc++;
    if (!$('pts').checked) continue;
    const col = COLORS[c === 'all' ? list[0][1] : c];
    L.circleMarker(l.ll, { radius: Math.min(3 + Math.sqrt(list.length) * 1.6, 16), color: '#222', weight: 0.8,
                           fillColor: col, fillOpacity: l.a ? 0 : 0.85 }).bindPopup(() => popup(l, list)).addTo(ptLayer);
  }

  const scale = { people: PEOPLE, time: TIME, overlap: OVERLAP, gaps: [OVERLAP[0]], age: AGE }[mode] || [];
  const title = { age: 'Average age of residents, 2020 Census (squares with 10+ residents)',
                  people: `${GROUPS[age]} more than ${T} min away, per 1.5 km square`,
                  time: `Drive time to nearest provider, where ${GROUPS[age].toLowerCase()} live (within ${T} min lighter)`,
                  overlap: `Provider locations within ${T} min`, gaps: `No provider within ${T} min` }[mode];
  $('legend').innerHTML = scale.length ? `<div class="muted">${title}</div>` + scale.map((o, k) => {
    const faded = mode === 'time' && (scale[k + 1] ? scale[k + 1][0] - 1 : 999) <= T;
    return `<div style="opacity:${faded ? 0.35 : 1}"><span style="background:${o[1]}"></span>${mode === 'gaps' ? 'Beyond ' + T + ' min' : o[2]}</div>`;
  }).join('') : '';

  let beyondArea = 0;
  for (let i = 0; i < near.length; i++) if (near[i] > T) beyondArea++;
  const sqmi = beyondArea * (G.dlat * 111) * (G.dlon * 111 * Math.cos(43.9 * Math.PI / 180)) / 2.59;
  const rows = Object.entries(GROUPS).map(([k, label]) => {
    let tot = 0, out = 0;
    POP[k].forEach((v, i) => { tot += v; if (near[i] > T) out += v; });
    return `<tr${k === age ? ' style="font-weight:600"' : ''}><td>${label}</td><td>${Math.round(out).toLocaleString()} · ${(100 * out / tot).toFixed(1)}%</td></tr>`;
  }).join('');
  $('summary').innerHTML = [
    [c === 'sn' ? 'Clinic sites' : 'Providers in selection', nProv.toLocaleString()],
    ['Distinct locations', nLoc.toLocaleString()],
    [`VT area beyond ${T} min`, `${(100 * beyondArea / near.length).toFixed(1)}% (≈ ${Math.round(sqmi).toLocaleString()} sq mi)`],
  ].map(([a, b]) => `<div class="stat"><span>${a}</span><b>${b}</b></div>`).join('') +
    `<table><tr class="muted"><td>More than ${T} min away</td><td>count · % of group</td></tr>${rows}</table>`;

  const town = {};
  G.town.forEach((t, i) => { const v = town[t] || (town[t] = [0, 0]); v[0] += pop[i]; if (near[i] > T) v[1] += pop[i]; });
  const worst = Object.entries(town).filter(([, v]) => v[1] >= 1).sort((a, b) => b[1][1] - a[1][1]).slice(0, 30);
  $('worst').innerHTML = worst.length
    ? '<tr class="muted"><td>Town</td><td>people · % of town</td></tr>' + worst.map(([t, v]) =>
      `<tr class="click" data-t="${esc(D.towns[t])}"><td>${esc(D.towns[t])}</td><td>${Math.round(v[1]).toLocaleString()} · ${Math.round(100 * v[1] / v[0])}%</td></tr>`).join('')
    : '<tr><td class="muted">Nobody in this group lives beyond the threshold.</td></tr>';
}

function renderHpsa() {
  hpsaLayer.clearLayers();
  const fc = window.HPSA[$('hpsaKind').value];
  $('hpsaNote').textContent = $('hpsa').checked && !fc.features.length
    ? 'No area-based designations of this type in Vermont; the only ones are attached to individual health centers.' : '';
  L.geoJSON(fc, {
    style: { color: '#6a3d9a', weight: 2, dashArray: '6 4', fillColor: '#6a3d9a', fillOpacity: 0.12 },
    onEachFeature: (ft, l) => { const p = ft.properties; l.bindPopup(
      `<b>${esc(p.name)}</b><br>${esc(p.part)}<br>${esc(p.type)} · ${esc(p.pop)}<br>Score ${esc(p.score)} · ${esc(p.status)}${p.updated ? ' · updated ' + esc(p.updated) : ''}`); },
  }).addTo(hpsaLayer);
}

const toggle = (id, layer) => { $(id).onchange = () => ($(id).checked ? layer.addTo(map) : map.removeLayer(layer)); };
toggle('towns', townLayer);
toggle('sn', snLayer);
$('hpsa').onchange = () => { renderHpsa(); $('hpsa').checked ? hpsaLayer.addTo(map) : map.removeLayer(hpsaLayer); };
$('hpsaKind').onchange = () => { if (!$('hpsa').checked) $('hpsa').click(); else renderHpsa(); };
$('worst').onclick = e => { const tr = e.target.closest('tr[data-t]'); if (tr) map.fitBounds(townBounds[tr.dataset.t]); };
$('cat').onchange = $('pts').onchange = render;
document.querySelectorAll('input[name=mode],input[name=who],input[name=thr],input[name=age]').forEach(r => { r.onchange = render; });
render();
