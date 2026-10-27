// UI 基础组件与工具
import { icon } from './icons.js';
import { avatarColor } from './format.js';

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

export function debounce(fn, wait = 220) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), wait); };
}

/* ---------------- Toast ---------------- */

export function toast(msg, type = '') {
  const root = $('#toast-root');
  if (!root) return;
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.innerHTML = `${type === 'err' ? icon('alert', 15) : icon('check-circle', 15)}<span>${esc(msg)}</span>`;
  root.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity .2s, transform .2s';
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    setTimeout(() => el.remove(), 220);
  }, 2600);
}

/* ---------------- 弹窗 ---------------- */

let modalCount = 0;
export function openModal({ title, body, footer = '', size = '', onMount }) {
  const root = $('#modal-root');
  const mask = document.createElement('div');
  mask.className = 'modal-mask';
  mask.dataset.id = String(++modalCount);
  mask.innerHTML = `
    <div class="modal ${size}" role="dialog" aria-modal="true">
      <div class="modal-h">
        <h3>${esc(title)}</h3>
        <button class="icon-btn x" aria-label="关闭">${icon('x', 16)}</button>
      </div>
      <div class="modal-b">${body}</div>
      ${footer ? `<div class="modal-f">${footer}</div>` : ''}
    </div>`;
  root.appendChild(mask);
  const close = () => mask.remove();
  mask.addEventListener('click', (e) => { if (e.target === mask) close(); });
  $('.x', mask).addEventListener('click', close);
  const onKey = (e) => { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); } };
  document.addEventListener('keydown', onKey);
  if (onMount) onMount(mask, close);
  return { el: mask, close };
}

/* ---------------- 复制 ---------------- */

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制到剪贴板');
    return true;
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); toast('已复制到剪贴板'); return true; }
    catch { toast('复制失败，请手动选择', 'err'); return false; }
    finally { ta.remove(); }
  }
}

/* ---------------- 小组件 ---------------- */

const TIER_COLOR = { S: 'violet', A: 'blue', B: 'green', C: 'gray' };

export function tierBadge(tier) {
  const t = tier || 'C';
  return `<span class="tier-badge ${esc(t)}"><span class="tier ${esc(t)}">${esc(t)}</span>${t === 'S' ? '超头部' : t === 'A' ? '高潜' : t === 'B' ? '可投' : '观察'}</span>`;
}

export function tierPill(tier) {
  const t = tier || 'C';
  return `<span class="badge ${TIER_COLOR[t] || 'gray'}">${esc(t)} 层</span>`;
}

const PF_GLYPH = { 小红书: '红', 抖音: '抖', 视频号: '视', 快手: '快' };

export function platformTag(p) {
  const name = String(p || '其他');
  const cls = ['小红书', '抖音', '视频号', '快手'].includes(name) ? name : '';
  const glyph = PF_GLYPH[name] || name.slice(0, 1);
  return `<span class="ptag"><span class="pf ${cls}">${esc(glyph)}</span><span>${esc(name)}</span></span>`;
}

export function avatar(name, size = '') {
  const s = String(name || '?').replace(/[_\s]/g, '').slice(0, 2).toUpperCase();
  const [bg, fg] = avatarColor(name);
  return `<span class="avatar ${size}" style="background:${bg};color:${fg};border-color:transparent;box-shadow:none">${esc(s)}</span>`;
}

export function deltaTag(v, suffix = '%', invert = false) {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return `<span class="delta flat">持平</span>`;
  const up = invert ? n < 0 : n > 0;
  return `<span class="delta ${up ? 'up' : 'down'}">${n > 0 ? icon('arrow-up', 12) : icon('arrow-down', 12)}${Math.abs(n).toFixed(1)}${suffix}</span>`;
}

export function kpi({ iconName, tone = 'blue', label, value, unit = '', foot = '' }) {
  return `<div class="kpi">
    <div class="kpi-top">
      <span class="kpi-ico ${tone}">${icon(iconName, 16)}</span>
      <span class="kpi-label">${esc(label)}</span>
    </div>
    <div class="kpi-value"><span class="kpi-num">${value}</span>${unit ? `<small>${esc(unit)}</small>` : ''}</div>
    ${foot ? `<div class="kpi-foot">${foot}</div>` : ''}
  </div>`;
}

export function stepper(steps, activeIndex, doneIndex = -1) {
  return `<div class="stepper">${steps.map((s, i) => {
    const done = i <= doneIndex;
    const active = i === activeIndex && !done;
    return `<div class="step ${done ? 'done' : ''} ${active ? 'active' : ''}">
        <span class="step-no">${done ? icon('check', 12) : i + 1}</span>
        <span class="step-label">${esc(s)}</span>
      </div>${i < steps.length - 1 ? `<span class="step-line ${i < doneIndex ? 'done' : ''}"></span>` : ''}`;
  }).join('')}</div>`;
}

export function emptyState(text, iconName = 'inbox', extra = '') {
  return `<div class="empty"><div class="icon">${icon(iconName, 20)}</div>${esc(text)}${extra}</div>`;
}

export function skeletonRows(n = 3, h = 14) {
  return Array.from({ length: n }, (_, i) =>
    `<div class="skeleton" style="height:${h}px;margin:10px 0;width:${90 - i * 12}%"></div>`).join('');
}

/* ---------------- Markdown ---------------- */

export function markdownToHtml(md) {
  const src = String(md || '').replace(/\r\n/g, '\n');
  const blocks = src.split(/```/);
  let out = '';
  blocks.forEach((block, idx) => {
    if (idx % 2 === 1) {
      const lines = block.replace(/^\w*\n/, '');
      out += `<pre class="code">${esc(lines.trim())}</pre>`;
      return;
    }
    out += renderTextBlock(block);
  });
  return out;
}

function inline(s) {
  let t = esc(s);
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  t = t.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return t;
}

function renderTextBlock(block) {
  const lines = block.split('\n');
  const html = [];
  let i = 0;
  let listType = null;
  let inTable = false;
  let tableRows = [];

  const flushList = () => { if (listType) { html.push(`</${listType}>`); listType = null; } };
  const flushTable = () => {
    if (!inTable) return;
    const rows = tableRows.filter((r) => !/^\|?[\s:-]+\|/.test(r.replace(/\|/g, '|')));
    if (rows.length) {
      const cells = rows.map((r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim()));
      html.push('<table><thead><tr>' + cells[0].map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        + cells.slice(1).map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('')
        + '</tbody></table>');
    }
    inTable = false; tableRows = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const trimmed = line.trim();

    if (!trimmed) { flushList(); flushTable(); continue; }

    if (/^\|.*\|$/.test(trimmed)) {
      flushList();
      inTable = true;
      tableRows.push(trimmed);
      continue;
    }
    flushTable();

    const h = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (h) { flushList(); html.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); continue; }

    if (/^>\s?/.test(trimmed)) { flushList(); html.push(`<blockquote>${inline(trimmed.replace(/^>\s?/, ''))}</blockquote>`); continue; }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { flushList(); html.push('<hr>'); continue; }

    const ul = trimmed.match(/^[-*+]\s+(.*)$/);
    if (ul) {
      if (listType !== 'ul') { flushList(); html.push('<ul>'); listType = 'ul'; }
      html.push(`<li>${inline(ul[1])}</li>`);
      continue;
    }
    const ol = trimmed.match(/^\d+[.)]\s+(.*)$/);
    if (ol) {
      if (listType !== 'ol') { flushList(); html.push('<ol>'); listType = 'ol'; }
      html.push(`<li>${inline(ol[1])}</li>`);
      continue;
    }

    flushList();
    html.push(`<p>${inline(trimmed)}</p>`);
  }
  flushList(); flushTable();
  return html.join('');
}

export function mountMarkdown(el, md) {
  el.classList.add('markdown');
  el.innerHTML = markdownToHtml(md);
}

/* ---------------- 表单值 ---------------- */

export function formValue(form, name) {
  const el = form.querySelector(`[name="${name}"]`);
  return el ? el.value.trim() : '';
}
