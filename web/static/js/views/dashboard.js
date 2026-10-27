// 工作台
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, kpi, deltaTag, emptyState, openModal, toast } from '../ui.js';
import { compact, money, num, pct, dateTime, truncate } from '../format.js';
import { lineChart } from '../charts.js';
import { runWithModal } from '../run.js';

const PRESETS = [
  { label: '筛选高潜力达人', icon: 'user-search', goal: '指压板新品起量，预算 8000，筛选高潜力达人' },
  { label: '生成多平台内容', icon: 'edit', goal: '把这批内容改写成小红书、抖音、视频号三个平台版本，注意合规' },
  { label: '查看投放异常', icon: 'alert', goal: '监测一下今天有没有异常账号，需要我处理的' },
  { label: '生成今日日报', icon: 'file-text', goal: '汇总今天的投放数据和异常告警，生成日报' },
];

const TASK_TYPES = ['全部', '达人管理', '内容运营', '投放管理', '数据监测'];

function taskType(goal = '') {
  if (/复盘|归因|ROI/.test(goal)) return '投放管理';
  if (/监测|异常|告警/.test(goal)) return '数据监测';
  if (/复写|文案|合规|内容/.test(goal)) return '内容运营';
  if (/选人|达人|预算|筛选/.test(goal)) return '达人管理';
  if (/日报/.test(goal)) return '数据监测';
  return '达人管理';
}

export async function renderDashboard(root) {
  const budget = store.budget;
  const [ov, cand, trend, tasks, samples] = await Promise.all([
    api.overview(budget),
    api.candidates({ budget }),
    api.trend(30),
    api.tasks(10),
    api.samples().catch(() => ({ samples: [] })),
  ]);
  store.overview = ov;

  const alerts = ov.monitor || {};
  const review = ov.review || {};
  const overall = review.overall || {};
  const llmOn = !!ov.llm;

  root.innerHTML = `
    <section class="hero" id="section-strategy">
      <div class="hero-inner">
        <h1>早上好，<b>这是你的达人投放运营助手</b></h1>
        <p>给定一个目标，Agent 会自己写执行计划、调用工具、核对每个数字，再把结论交给你。</p>
        <div class="agent-box">
          <span class="spark">${icon('sparkles', 17)}</span>
          <input id="goalInput" placeholder="告诉我你想做什么，例如：帮我筛选 30 个达人，预算 8000，推荐合适的投放方案…">
          <span class="budget-mini">预算 <input id="budgetInput" type="number" min="0" step="500" value="${budget}"> 元</span>
          <button class="btn btn-primary" id="runBtn">${icon('play', 14)} 开始任务</button>
        </div>
        <div class="hero-tasks">
          <span class="lbl">推荐任务：</span>
          ${PRESETS.map((p) => `<button class="chip" data-goal="${esc(p.goal)}">${icon(p.icon, 13)}${esc(p.label)}</button>`).join('')}
        </div>
      </div>
      <div class="hero-art">${heroArt()}</div>
    </section>

    <div class="grid grid-5 mt-16" id="kpiRow">
      ${kpi({ iconName: 'users', tone: 'blue', label: '线索池', value: num(cand.total), unit: '位', foot: `<span class="badge blue">S/A 高潜 ${num(cand.high_tier)}</span>` })}
      ${kpi({ iconName: 'file-text', tone: 'green', label: '内容样本', value: num(samples.samples.length), unit: '条', foot: `<span class="muted">覆盖小红书 / 抖音 / 视频号</span>` })}
      ${kpi({ iconName: 'alert', tone: 'red', label: '异常告警', value: num(alerts.alert_count), unit: '条', foot: `<span class="badge red">P0 ${alerts.p0 || 0}</span> <span class="badge amber">P1 ${alerts.p1 || 0}</span>` })}
      ${kpi({ iconName: 'target', tone: 'violet', label: '平均评分', value: num(cand.avg_score, 1), unit: '分', foot: `<span class="muted">批内相对排序 · 满分 100</span>` })}
      ${kpi({ iconName: 'trending-up', tone: 'blue', label: '整体 ROI', value: overall.roi ?? '—', foot: `花费 ${money(overall.spend)} · 成交 ${money(overall.gmv)}` })}
    </div>

    <div class="split mt-16">
      <div>
        <section class="card" id="section-trend">
          <div class="card-h">
            <h2>达人投放数据概览</h2>
            <div class="right">
              <div class="segmented" id="trendSeg">
                <button data-days="7">近 7 天</button>
                <button data-days="14" class="on">近 14 天</button>
                <button data-days="30">近 30 天</button>
              </div>
            </div>
          </div>
          <div class="card-b">
            <div class="chart-stats" id="trendStats"></div>
            <div class="chart-wrap" id="trendChart"></div>
            <div class="flex" style="justify-content:space-between;margin-top:10px">
              <div class="chart-legend" id="trendLegend"></div>
              <span class="muted tiny">指数 = 各指标相对首日的变化（不是绝对值）</span>
            </div>
          </div>
        </section>

        <section class="card" id="recentTasks">
          <div class="card-h">
            <h2>最近任务</h2>
            <div class="right muted tiny">来自 traces 运行记录</div>
          </div>
          <div class="card-tools" style="padding-top:10px">
            <div class="tabs" style="border:0" id="taskTabs">
              ${TASK_TYPES.map((t, i) => `<button class="tab ${i === 0 ? 'on' : ''}" data-type="${t}">${t}</button>`).join('')}
            </div>
          </div>
          <div class="card-b flush">
            <div id="taskTable"></div>
          </div>
        </section>
      </div>

      <div>
        <section class="card" id="section-alerts">
          <div class="card-h">
            <h2>今日异常告警</h2>
            <div class="right"><button class="link-btn" data-go="monitor">全部告警 ${icon('arrow-right', 12)}</button></div>
          </div>
          <div class="card-b" id="alertsList"></div>
        </section>

        <section class="card">
          <div class="card-h">
            <h2>待处理任务</h2>
            <div class="right muted tiny">${(ov.todos || []).length} 条</div>
          </div>
          <div class="card-b" id="pendingList"></div>
        </section>

        <section class="card">
          <div class="card-h"><h2>快捷入口</h2></div>
          <div class="card-b" style="display:grid;gap:8px">
            <div class="quick" data-go="kols"><span class="qi" style="background:var(--primary-soft);color:var(--primary)">${icon('user-search', 16)}</span><div><div class="t1">筛选达人</div><div class="t2">基于四维评分，快速筛出高潜达人</div></div></div>
            <div class="quick" data-go="content"><span class="qi" style="background:var(--green-soft);color:#059669">${icon('edit', 16)}</span><div><div class="t1">内容复写</div><div class="t2">一稿多平台改写 + 合规检查</div></div></div>
            <div class="quick" data-go="reports"><span class="qi" style="background:var(--amber-soft);color:#b45309">${icon('file-text', 16)}</span><div><div class="t1">生成日报</div><div class="t2">投放数据 + 异常告警 + 结论建议</div></div></div>
            <div class="quick" data-go="monitor"><span class="qi" style="background:var(--violet-soft);color:var(--violet)">${icon('pie', 16)}</span><div><div class="t1">数据复盘</div><div class="t2">按内容类型看 ROI 与漏斗归因</div></div></div>
          </div>
        </section>
      </div>
    </div>`;

  /* ---- 交互 ---- */
  const goalInput = $('#goalInput', root);
  $('#runBtn', root).addEventListener('click', async () => {
    const goal = goalInput.value.trim();
    if (!goal) { goalInput.focus(); toast('先写一个目标，或点下面的推荐任务'); return; }
    const btn = $('#runBtn', root);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>执行中';
    try {
      await runWithModal(goal, async () => {
        const t = await api.tasks(10);
        renderTasks(t.items);
      });
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${icon('play', 14)} 开始任务`;
    }
  });
  goalInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') $('#runBtn', root).click(); });

  $$('.hero-tasks .chip', root).forEach((chip) => {
    chip.addEventListener('click', () => { goalInput.value = chip.dataset.goal; goalInput.focus(); });
  });

  $('#budgetInput', root).addEventListener('change', (e) => {
    const v = Number(e.target.value) || 8000;
    store.budget = v;
    localStorage.setItem('kol.budget', String(v));
    toast('预算已更新为 ' + money(v));
  });

  $$('[data-go]', root).forEach((el) => el.addEventListener('click', () => {
    location.hash = '#/' + el.dataset.go;
  }));

  renderAlerts(ov.todos || []);
  renderPending(ov.todos || [], tasks.items || []);
  renderTasks(tasks.items || []);
  renderTrend(trend, 14);

  $$('#trendSeg button', root).forEach((btn) => {
    btn.addEventListener('click', () => {
      $$('#trendSeg button', root).forEach((b) => b.classList.toggle('on', b === btn));
      renderTrend(trend, Number(btn.dataset.days));
    });
  });

  $$('#taskTabs .tab', root).forEach((tab) => {
    tab.addEventListener('click', () => {
      $$('#taskTabs .tab', root).forEach((t) => t.classList.toggle('on', t === tab));
      renderTasks(tasks.items || [], tab.dataset.type);
    });
  });

  function renderTrend(data, days) {
    const n = Math.min(days, data.dates.length);
    const dates = data.dates.slice(-n);
    const raw = {
      impressions: data.series.impressions.slice(-n),
      clicks: data.series.clicks.slice(-n),
      orders: data.series.orders.slice(-n),
    };
    const idx = (arr) => {
      const base = arr[0] || 1;
      return arr.map((v) => (v / base) * 100);
    };
    const series = [
      { label: '曝光量', values: idx(raw.impressions), color: '#2563eb' },
      { label: '点击量', values: idx(raw.clicks), color: '#10b981' },
      { label: '转化量', values: idx(raw.orders), color: '#8b5cf6' },
    ];
    const imp = sum(raw.impressions), clk = sum(raw.clicks), ord = sum(raw.orders);
    const gmv = sum(data.series.gmv.slice(-n)), spend = sum(data.series.spend.slice(-n)) || 1;
    $('#trendStats', root).innerHTML = `
      <div class="chart-stat"><div class="k">总曝光量</div><div class="v">${compact(imp)}</div></div>
      <div class="chart-stat"><div class="k">点击率</div><div class="v">${pct(clk / (imp || 1) * 100, 2)}</div></div>
      <div class="chart-stat"><div class="k">转化率</div><div class="v">${pct(ord / (clk || 1) * 100, 2)}</div></div>
      <div class="chart-stat"><div class="k">ROI</div><div class="v">${(gmv / spend).toFixed(2)}</div></div>`;
    lineChart($('#trendChart', root), { dates, series, height: 240 });
    $('#trendLegend', root).innerHTML = series.map((s) =>
      `<span class="legend-item"><span class="legend-dot" style="background:${s.color}"></span>${s.label}</span>`).join('');
  }

  function renderAlerts(todos) {
    const el = $('#alertsList', root);
    if (!todos.length) {
      el.innerHTML = emptyState('本期未命中告警阈值', 'shield', '<div class="tiny" style="margin-top:6px">没有告警不等于没有风险，可能是阈值过宽</div>');
      return;
    }
    el.innerHTML = todos.slice(0, 4).map((t) => `
      <div class="alert-item">
        <span class="lv ${t.level}">${t.level}</span>
        <div class="grow">
          <div class="t1">${esc(t.rule)}</div>
          <div class="t2">达人 ${esc(t.kol_id)} · ${t.delta > 0 ? '+' : ''}${t.delta}% · ${esc(truncate(t.hint, 46))}</div>
        </div>
        <span class="time">今日</span>
      </div>`).join('');
  }

  function renderPending(todos, taskItems) {
    const el = $('#pendingList', root);
    const rows = [
      ...todos.slice(0, 3).map((t) => ({
        title: t.rule, sub: `${t.kol_id} · ${truncate(t.hint, 30)}`,
        badge: t.level === 'P0' ? '<span class="badge red">待处理</span>' : '<span class="badge amber">待确认</span>',
        icon: 'alert', tone: t.level === 'P0' ? 'red' : 'amber',
      })),
      ...taskItems.slice(0, 2).map((t) => ({
        title: t.goal, sub: `${t.planner === 'llm' ? 'LLM' : '规则'} · ${t.steps} 步 · ${dateTime(t.mtime * 1000)}`,
        badge: '<span class="badge green">已完成</span>', icon: 'terminal', tone: 'blue',
      })),
    ];
    if (!rows.length) { el.innerHTML = emptyState('暂无待处理任务', 'check-circle'); return; }
    el.innerHTML = `<div class="list">${rows.map((r) => `
      <div class="list-item">
        <span class="ico" style="background:var(--${r.tone === 'red' ? 'red' : r.tone === 'amber' ? 'amber' : 'primary'}-soft);color:var(--${r.tone === 'red' ? 'red' : r.tone === 'amber' ? 'amber' : 'primary'})">${icon(r.icon, 15)}</span>
        <div class="grow"><div class="t1">${esc(truncate(r.title, 26))}</div><div class="t2">${esc(r.sub)}</div></div>
        <div class="meta">${r.badge}</div>
      </div>`).join('')}</div>`;
  }

  function renderTasks(items, type = '全部') {
    const el = $('#taskTable', root);
    const rows = items.filter((t) => type === '全部' || taskType(t.goal) === type);
    if (!rows.length) {
      el.innerHTML = emptyState('这个分类下还没有任务记录', 'clock');
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>任务名称</th><th>类型</th><th>执行时间</th><th>状态</th><th>结果</th><th></th></tr></thead>
      <tbody>${rows.map((t, i) => `<tr data-idx="${i}">
        <td><div class="name"><span class="avatar sm">${icon('terminal', 12)}</span>
          <div><div class="t1">${esc(truncate(t.goal, 26))}</div><div class="t2">${t.planner === 'llm' ? 'LLM 规划' : '规则规划'} · ${t.steps} 步</div></div></div></td>
        <td><span class="badge gray">${taskType(t.goal)}</span></td>
        <td class="num muted">${esc(t.ts)}</td>
        <td>${t.status === 'completed' ? '<span class="badge green dot">已完成</span>' : '<span class="badge red dot">失败</span>'}</td>
        <td class="muted">${esc(truncate(t.title || t.final_head || '—', 24))}</td>
        <td class="actions"><button class="link-btn" data-task="${i}">查看</button></td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-task]', el).forEach((btn) => {
      btn.addEventListener('click', () => {
        const t = rows[Number(btn.dataset.task)];
        openModal({
          title: '任务详情',
          body: `
            <div class="field"><div class="field-label">目标</div><div>${esc(t.goal)}</div></div>
            <div class="flex wrap" style="gap:6px;margin-bottom:12px">
              <span class="badge ${t.planner === 'llm' ? 'blue' : 'gray'}">${t.planner === 'llm' ? 'LLM 规划器' : '规则规划器'}</span>
              <span class="badge">${t.steps} 步</span><span class="badge">${t.ts}</span>
            </div>
            <div class="field-label">结论摘要</div>
            <div class="doc-card"><div class="body" style="max-height:220px;overflow:auto">${esc(t.final_head || '（无结论）')}</div></div>
            ${t.warnings && t.warnings.length ? `<div class="notice amber mt-12">${icon('alert', 15)}<div>${t.warnings.map(esc).join('<br>')}</div></div>` : ''}`,
          footer: `<button class="btn btn-sm" id="rerun">${icon('refresh', 14)} 用同样目标重跑</button><span class="spacer"></span><button class="btn btn-sm" id="closeTask">关闭</button>`,
          size: 'sm',
          onMount(el, close) {
            $('#closeTask', el).addEventListener('click', close);
            $('#rerun', el).addEventListener('click', () => {
              close();
              goalInput.value = t.goal;
              goalInput.focus();
              goalInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
          },
        });
      });
    });
  }
}

function sum(arr) { return arr.reduce((a, b) => a + b, 0); }

function heroArt() {
  return `<svg viewBox="0 0 260 170" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="ha1" x1="60" y1="30" x2="200" y2="140" gradientUnits="userSpaceOnUse">
        <stop stop-color="#dbeafe"/><stop offset="1" stop-color="#eff6ff"/>
      </linearGradient>
      <linearGradient id="ha2" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="#3b82f6"/><stop offset="1" stop-color="#60a5fa"/>
      </linearGradient>
      <linearGradient id="ha3" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="#10b981"/><stop offset="1" stop-color="#34d399"/>
      </linearGradient>
    </defs>
    <ellipse cx="132" cy="150" rx="86" ry="12" fill="#dbeafe" opacity=".55"/>
    <g transform="rotate(-16 130 86)">
      <rect x="72" y="40" width="108" height="76" rx="16" fill="url(#ha1)" stroke="#c7ddff"/>
      <rect x="86" y="52" width="108" height="76" rx="16" fill="#fff" stroke="#d7e6ff" opacity=".9"/>
      <rect x="100" y="64" width="108" height="76" rx="16" fill="url(#ha2)" opacity=".92"/>
      <path d="M118 102l14-14 12 12 20-22" stroke="#fff" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="118" cy="102" r="4" fill="#fff"/>
    </g>
    <g transform="rotate(14 200 60)">
      <rect x="186" y="34" width="42" height="42" rx="12" fill="url(#ha3)" opacity=".9"/>
      <path d="M198 55l8-8 4 4 8-9" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </g>
    <circle cx="60" cy="44" r="3" fill="#93c5fd"/>
    <circle cx="224" cy="126" r="2.5" fill="#6ee7b7"/>
    <path d="M40 108l4 8 8 4-8 4-4 8-4-8-8-4 8-4 4-8z" fill="#bfdbfe"/>
  </svg>`;
}
