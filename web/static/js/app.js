import { icon } from './icons.js';
import { $, $$, esc, toast, avatar } from './ui.js';
import { api } from './api.js';
import { store, setBudget, setPlanner } from './state.js';

import { renderDashboard } from './views/dashboard.js';
import { renderKols } from './views/kols.js';
import { renderContent } from './views/content.js';
import { renderMonitor } from './views/monitor.js';
import { renderLeads } from './views/leads.js';
import { renderReports } from './views/reports.js';
import { renderSettings } from './views/settings.js';
import { renderTiers } from './views/tiers.js';
import { renderOutreach } from './views/outreach.js';
import { renderLibrary } from './views/library.js';
import { renderCompliance } from './views/compliance.js';
import { renderBudget } from './views/budget.js';
import { renderStrategy } from './views/strategy.js';
import { initMotion } from './motion.js';

const NAV = [
  { label: '', items: [{ key: 'dashboard', text: '工作台', icon: 'home' }] },
  {
    label: '达人管理',
    items: [
      { key: 'leads', text: '线索入库', icon: 'inbox' },
      { key: 'kols', text: '达人筛选与评分', icon: 'user-search' },
      { key: 'tiers', text: '达人分层', icon: 'layers' },
      { key: 'outreach', text: '邀约管理', icon: 'message' },
    ],
  },
  {
    label: '内容运营',
    items: [
      { key: 'content', text: '内容复写', icon: 'edit' },
      { key: 'compliance', text: '合规检查', icon: 'shield' },
      { key: 'library', text: '内容库', icon: 'book' },
    ],
  },
  {
    label: '投放管理',
    items: [
      { key: 'strategy', text: '投放策略', icon: 'target' },
      { key: 'budget', text: '预算管理', icon: 'dollar' },
      { key: 'monitor', text: '数据复盘', icon: 'chart' },
    ],
  },
  {
    label: '数据监测',
    items: [
      { key: 'monitor', focus: 'alerts', text: '异常告警', icon: 'alert' },
      { key: 'dashboard', focus: 'trend', text: '数据看板', icon: 'activity' },
    ],
  },
  {
    label: '日报中心',
    items: [
      { key: 'reports', text: '日报生成', icon: 'file-text' },
      { key: 'reports', focus: 'history', text: '历史记录', icon: 'clock' },
    ],
  },
];

const ROUTES = {
  dashboard: renderDashboard,
  kols: renderKols,
  tiers: renderTiers,
  outreach: renderOutreach,
  content: renderContent,
  compliance: renderCompliance,
  library: renderLibrary,
  strategy: renderStrategy,
  budget: renderBudget,
  monitor: renderMonitor,
  leads: renderLeads,
  reports: renderReports,
  settings: renderSettings,
};

let current = { key: 'dashboard', focus: '' };

/* ---------------- 侧边栏 ---------------- */

function renderSidebar() {
  const groups = NAV.map((g, gi) => {
    const items = g.items.map((it) => navButton(it)).join('');
    if (!g.label) return items;
    return `<div class="nav-group open" data-group="${gi}">
      <button class="nav-item group-toggle" type="button">
        ${icon(groupIcon(g.label), 17)}<span>${esc(g.label)}</span>
        <span class="chev">${icon('chevron-down', 13)}</span>
      </button>
      <div class="nav-sub">${items}</div>
    </div>`;
  }).join('');

  $('#sidebar').innerHTML = `
    <div class="brand">
      <span class="brand-mark">${icon('activity', 17)}</span>
      <div>
        <div class="brand-name">KOL Operations</div>
        <div class="brand-sub">达人运营智能体 · v1.5</div>
      </div>
    </div>
    <div class="side-scroll">${groups}</div>
    <div class="side-foot">
      <div class="status-card" id="sideStatus"></div>
      <button class="nav-item" data-route="settings">${icon('settings', 17)}<span>系统设置</span></button>
    </div>`;

  $$('.nav-group .group-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const group = btn.closest('.nav-group');
      // 有选中项的分组默认展开，点击只做折叠切换
      group.classList.toggle('open');
    });
  });

  $$('#sidebar [data-route]').forEach((el) => {
    el.addEventListener('click', () => {
      const focus = el.dataset.focus || '';
      go(el.dataset.route, focus);
    });
  });

  refreshSideStatus();
}

function groupIcon(label) {
  return ({
    达人管理: 'users', 内容运营: 'edit', 投放管理: 'megaphone', 数据监测: 'activity', 日报中心: 'file-text',
  })[label] || 'folder';
}

function navButton(it) {
  const active = current.key === it.key && (it.focus || '') === current.focus;
  return `<button class="nav-item ${active ? 'active' : ''}" data-route="${it.key}" data-focus="${it.focus || ''}">
    ${icon(it.icon, 17)}<span>${esc(it.text)}</span></button>`;
}

async function refreshSideStatus() {
  const el = $('#sideStatus');
  if (!el) return;
  try {
    if (!store.llm) store.llm = await api.llmStatus();
    if (!store.ds) store.ds = await api.datasource();
    const on = !!store.llm.available;
    el.innerHTML = `
      <div class="row1"><span class="status-dot ${on ? '' : 'off'}"></span>${on ? 'AI 已连接' : '离线规则模式'}</div>
      <div class="row2">${on ? esc(store.llm.model || 'LLM') : '未配置 Key，可跑全流程'}<br>数据源 ${esc(store.ds.source || 'csv').toUpperCase()} · 合成样例</div>`;
  } catch {
    el.innerHTML = '<div class="row1"><span class="status-dot off"></span>后端未连接</div>';
  }
}

/* ---------------- 顶栏 ---------------- */

function renderTopbar() {
  $('#topbar').innerHTML = `
    <div class="flex" style="gap:10px;min-width:0">
      <select class="select" id="plannerSel" style="width:118px;height:28px;font-size:11.5px;border-radius:8px">
        <option value="auto">自动规划</option>
        <option value="rule">规则规划</option>
        <option value="llm">LLM 规划</option>
      </select>
      <span class="badge" id="aiChip">检测中</span>
      <span class="muted tiny nowrap">预算 ${Number(store.budget).toLocaleString()} 元</span>
    </div>
    <div class="search">
      ${icon('search', 15)}
      <input id="globalSearch" placeholder="搜索达人、账号、任务…" autocomplete="off">
    </div>
    <button class="icon-btn" id="bellBtn" title="告警" aria-label="告警">${icon('bell', 17)}<span class="dot hidden"></span></button>
    <button class="avatar" id="userBtn" title="当前账号">CC</button>`;

  const plannerSel = $('#plannerSel');
  plannerSel.value = store.planner;
  plannerSel.addEventListener('change', () => {
    setPlanner(plannerSel.value);
    if (plannerSel.value === 'llm' && store.llm && !store.llm.available) {
      toast('还没配置 DEEPSEEK_API_KEY，LLM 规划会回退到规则基线', 'err');
    } else {
      toast('规划器已切换为 ' + ({ auto: '自动', rule: '规则', llm: 'LLM' })[plannerSel.value]);
    }
  });
  refreshAiChip();

  $('#globalSearch').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const q = e.target.value.trim();
      go('kols', '', { q });
    }
  });
  $('#bellBtn').addEventListener('click', () => {
    const o = store.overview;
    if (!o) { toast('告警加载中…'); return; }
    const p0 = o.monitor?.p0 || 0, p1 = o.monitor?.p1 || 0;
    toast(`当前 ${p0} 条 P0、${p1} 条 P1 告警，可在「数据监测」查看`);
    go('monitor', 'alerts');
  });
  $('#userBtn').addEventListener('click', () => {
    toast(`当前规划器：${store.planner} · 数据源：${store.ds?.source || 'csv'}`);
  });
}

async function refreshAiChip() {
  const el = $('#aiChip');
  if (!el) return;
  try {
    if (!store.llm) store.llm = await api.llmStatus();
    if (store.llm.available) {
      el.className = 'badge green dot';
      el.textContent = 'AI 已连接';
      el.title = store.llm.model || 'LLM';
    } else {
      el.className = 'badge amber dot';
      el.textContent = '离线规则';
      el.title = '未配置 API Key';
    }
  } catch {
    el.className = 'badge gray';
    el.textContent = 'AI 未知';
  }
}

async function refreshBell() {
  try {
    store.overview = store.overview || await api.overview(store.budget);
    const n = (store.overview.monitor?.p0 || 0) + (store.overview.monitor?.p1 || 0);
    const dot = $('#bellBtn .dot');
    if (dot) dot.classList.toggle('hidden', !n);
  } catch { /* 忽略 */ }
}

/* ---------------- 路由 ---------------- */

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [pathPart, queryPart] = raw.split('?');
  const key = (pathPart || 'dashboard').split('/')[0] || 'dashboard';
  const params = new URLSearchParams(queryPart || '');
  return { key, focus: params.get('focus') || '', params };
}

export function go(key, focus = '', extra = {}) {
  const params = new URLSearchParams();
  if (focus) params.set('focus', focus);
  for (const [k, v] of Object.entries(extra)) if (v) params.set(k, v);
  const q = params.toString();
  location.hash = `#/${key}${q ? '?' + q : ''}`;
}

async function route() {
  const { key, focus, params } = parseHash();
  current = { key: ROUTES[key] ? key : 'dashboard', focus };
  renderSidebar();
  renderTopbar();
  refreshBell();

  const view = $('#view');
  view.innerHTML = `<div class="empty"><span class="spin dark"></span><div style="margin-top:10px">加载中…</div></div>`;
  window.scrollTo({ top: 0 });
  try {
    await ROUTES[current.key](view, { focus, params });
  } catch (err) {
    view.innerHTML = `<div class="card"><div class="card-b">
      <div class="notice red">${icon('alert', 16)}<div><b>页面加载失败：</b>${esc(err.message)}<br>
      <span class="tiny">请确认后端已启动：python web/server.py</span></div></div>
    </div></div>`;
  }
  initMotion(view);
  if (focus) {
    setTimeout(() => {
      const target = document.getElementById('section-' + focus);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 120);
  }
}

/* ---------------- 启动 ---------------- */

let motionFrame = 0;
function scheduleMotion() {
  if (motionFrame) return;
  motionFrame = requestAnimationFrame(() => {
    motionFrame = 0;
    initMotion($('#view'));
  });
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', () => {
  if (!location.hash) location.hash = '#/dashboard';
  route();
  const view = $('#view');
  new MutationObserver(scheduleMotion).observe(view, { childList: true, subtree: true });
});

// 供其他视图使用
export { store, setBudget, setPlanner };
