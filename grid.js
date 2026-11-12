'use strict';
// Draws a regular lat/lon grid of coloured squares as one image, in Web Mercator so it lines up with
// the map tiles. Row edges are rounded to whole pixels once and shared by neighbouring rows, so
// semi-transparent squares neither overlap nor leave gaps. Shared by the map and comparison pages.
window.GridLayer = function (map, lat0, lon0, dlat, dlon, rc, px = 8) {
  const NR = Math.max(...rc.map(r => r[0])) + 1, NC = Math.max(...rc.map(r => r[1])) + 1;
  const merc = la => Math.log(Math.tan(Math.PI / 4 + la * Math.PI / 360));
  const M0 = merc(lat0), M1 = merc(lat0 + NR * dlat), H = NR * px;
  const rowY = Array.from({ length: NR + 1 }, (_, r) => Math.round((M1 - merc(lat0 + r * dlat)) / (M1 - M0) * H));
  const bounds = [[lat0, lon0], [lat0 + NR * dlat, lon0 + NC * dlon]];
  let img = null;
  return {
    draw(colorOf) {
      const cv = document.createElement('canvas');
      cv.width = NC * px; cv.height = H;
      const ctx = cv.getContext('2d');
      rc.forEach(([r, c], i) => {
        const s = colorOf(i);
        if (!s) return;
        ctx.fillStyle = s;
        ctx.fillRect(c * px, rowY[r + 1], px, rowY[r] - rowY[r + 1]);
      });
      this.clear();
      img = L.imageOverlay(cv.toDataURL(), bounds, { className: 'grid-img', interactive: false }).addTo(map);
    },
    clear() { if (img) map.removeLayer(img); img = null; },
    get visible() { return !!img; },
  };
};
window.rgba = (hex, a) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a})`;
window.pick = (scale, n) => scale.reduce((c, [t, col]) => (n >= t ? col : c), scale[0][1]);
window.esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
window.b64 = (s, T) => new T(Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer);
