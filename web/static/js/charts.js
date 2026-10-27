// 纯 SVG 图表，无第三方依赖
import { esc } from './ui.js';

function niceMax(v) {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

function smoothPath(points) {
  if (!points.length) return '';
  if (points.length === 1) return `M${points[0][0]},${points[0][1]}`;
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] || points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] || p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`;
  }
  return d;
}

/**
 * 折线图
 * @param {HTMLElement} el
 * @param {{dates:string[], series:{label:string,values:number[],color:string}[], height?:number}} data
 */
export function lineChart(el, { dates = [], series = [], height = 240 }) {
  if (!el) return;
  const W = 820, H = height;
  const pad = { l: 46, r: 12, t: 14, b: 26 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  if (!dates.length || !series.length) {
    el.innerHTML = '<div class="empty">暂无趋势数据</div>';
    return;
  }

  const max = niceMax(Math.max(...series.flatMap((s) => s.values), 1));
  const x = (i) => pad.l + (dates.length <= 1 ? iw / 2 : (i / (dates.length - 1)) * iw);
  const y = (v) => pad.t + ih - (v / max) * ih;

  const ticks = 4;
  let grid = '';
  for (let i = 0; i <= ticks; i++) {
    const gy = pad.t + (ih / ticks) * i;
    const val = max - (max / ticks) * i;
    grid += `<line x1="${pad.l}" y1="${gy}" x2="${W - pad.r}" y2="${gy}" stroke="#eef2f8" stroke-width="1"/>`;
    grid += `<text x="${pad.l - 9}" y="${gy + 4}" text-anchor="end" font-size="10" fill="#9aa8bd">${fmtAxis(val)}</text>`;
  }

  let xLabels = '';
  const step = Math.max(1, Math.ceil(dates.length / 7));
  dates.forEach((d, i) => {
    if (i % step !== 0 && i !== dates.length - 1) return;
    xLabels += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="#9aa8bd">${esc(fmtDate(d))}</text>`;
  });

  let paths = '';
  series.forEach((s, si) => {
    const pts = s.values.map((v, i) => [x(i), y(v)]);
    const d = smoothPath(pts);
    if (si === 0) {
      const area = `${d} L${x(dates.length - 1)},${pad.t + ih} L${pad.l},${pad.t + ih} Z`;
      paths += `<defs><linearGradient id="area-g" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="${s.color}" stop-opacity=".18"/>
        <stop offset="1" stop-color="${s.color}" stop-opacity="0"/>
      </linearGradient></defs>`;
      paths += `<path d="${area}" fill="url(#area-g)" class="chart-area"/>`;
    }
    paths += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" pathLength="100" class="chart-line"/>`;
    const last = pts[pts.length - 1];
    paths += `<circle cx="${last[0]}" cy="${last[1]}" r="3.5" fill="#fff" stroke="${s.color}" stroke-width="2"/>`;
  });

  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none" role="img" aria-label="趋势图">
    ${grid}${paths}${xLabels}
  </svg>`;
}

function fmtAxis(v) {
  if (v >= 1e8) return (v / 1e8).toFixed(v % 1e8 === 0 ? 0 : 1) + '亿';
  if (v >= 1e4) return (v / 1e4).toFixed(v % 1e4 === 0 ? 0 : 1) + 'w';
  if (v >= 1000) return (v / 1000).toFixed(v % 1000 === 0 ? 0 : 1) + 'k';
  return String(Math.round(v));
}

function fmtDate(d) {
  const s = String(d);
  const m = s.match(/\d{4}-(\d{2})-(\d{2})/);
  return m ? `${m[1]}/${m[2]}` : s;
}

/**
 * 环形图
 * @param {HTMLElement} el
 * @param {{label:string, value:number, color:string}[]} segments
 */
export function donut(el, segments = [], { size = 132, thickness = 14, center = '' } = {}) {
  if (!el) return;
  const total = segments.reduce((a, s) => a + Number(s.value || 0), 0);
  const r = (size - thickness) / 2;
  const c = size / 2;
  const circumference = 2 * Math.PI * r;

  if (!total) {
    el.innerHTML = `<div class="empty" style="padding:10px">暂无分布</div>`;
    return;
  }

  let offset = 0;
  const arcs = segments.map((s) => {
    const len = (Number(s.value) / total) * circumference;
    const dash = `${Math.max(len - 2, 0)} ${circumference - Math.max(len - 2, 0)}`;
    const arc = `<circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${thickness}"
      stroke-dasharray="${dash}" stroke-dashoffset="${-offset}" stroke-linecap="round"
      transform="rotate(-90 ${c} ${c})"/>`;
    offset += len;
    return arc;
  }).join('');

  el.innerHTML = `
    <svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img">
      <circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="#f1f5fb" stroke-width="${thickness}"/>
      ${arcs}
      ${center ? `<text x="${c}" y="${c - 2}" text-anchor="middle" font-size="18" font-weight="700" fill="#101828">${esc(center)}</text>` : ''}
    </svg>`;
}

/** 迷你趋势线 */
export function sparkline(values, color = '#2563eb', w = 90, h = 26) {
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const pts = values.map((v, i) => [
    (i / Math.max(values.length - 1, 1)) * w,
    h - ((v - min) / span) * (h - 3) - 1.5,
  ]);
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" fill="none">
    <path d="${smoothPath(pts)}" stroke="${color}" stroke-width="1.8" stroke-linecap="round"/>
  </svg>`;
}
