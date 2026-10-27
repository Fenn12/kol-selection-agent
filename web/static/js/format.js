// 数字 / 时间 / 文本格式化
export const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export function num(v, d = 0) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return Number(v).toLocaleString('zh-CN', {
    minimumFractionDigits: d, maximumFractionDigits: d,
  });
}

export function compact(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(1).replace(/\.0$/, '') + '亿';
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(1).replace(/\.0$/, '') + 'w';
  return num(n);
}

export function pct(v, d = 1) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return Number(v).toFixed(d) + '%';
}

export function money(v, d = 0) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  return '¥' + num(v, d);
}

export function ratio(v, d = 1) {
  if (!Number.isFinite(Number(v))) return '—';
  return Number(v).toFixed(d);
}

export function dateTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts);
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getMonth() + 1}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function duration(ms) {
  const n = Number(ms) || 0;
  if (n < 1000) return `${n}ms`;
  if (n < 60000) return (n / 1000).toFixed(1) + 's';
  return Math.floor(n / 60000) + 'm' + Math.round((n % 60000) / 1000) + 's';
}

export function shortDate(s) {
  if (!s) return '';
  const m = String(s).match(/^\d{4}-(\d{2})-(\d{2})/);
  return m ? `${m[1]}/${m[2]}` : String(s);
}

export function initials(name) {
  const s = String(name || '?').replace(/[_\s]/g, '');
  return s.slice(0, 2).toUpperCase();
}

// 按字符串稳定取色，用于头像底色
const AVATAR_COLORS = [
  ['#eef4ff', '#2563eb'], ['#e8f8f1', '#059669'], ['#fff6e6', '#b45309'],
  ['#f3eeff', '#7c3aed'], ['#fef0f0', '#dc2626'], ['#e6f8fb', '#0891b2'],
];
export function avatarColor(name) {
  let h = 0;
  for (const ch of String(name || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function truncate(s, n = 80) {
  const str = String(s ?? '');
  return str.length > n ? str.slice(0, n) + '…' : str;
}
