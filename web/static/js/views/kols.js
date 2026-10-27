// 达人筛选与评分
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import {
  $, $$, esc, kpi, tierBadge, platformTag, avatar, emptyState, openModal,
  copyText, toast, stepper, mountMarkdown,
} from '../ui.js';
import { compact, money, num, pct, duration, truncate } from '../format.js';
import { donut } from '../charts.js';
import { openRunModal, runAgent } from '../run.js';
import { openOutreach } from '../kol-actions.js';

const PAGE_SIZE = 10;

export async function renderKols(root, { focus = '', params } = {}) {
  const budget = store.budget;
  const data = await api.candidates({ budget });
  const state = {
    data,
    tab: 'all',
    platform: '',
    tier: '',
    q: params?.get('q') || '',
    page: 1,
    selected: new Set(),
    rec: null,
    budget,
  };

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>达人筛选与评分</h1>
        <p>达人线索批量导入、四维评分、S/A/B/C 分层、报价与预算分配，并展示评分依据。</p>
      </div>
      <div class="actions">
        <button class="btn" id="refreshBtn">${icon('refresh', 14)} 重新筛选</button>
        <button class="btn btn-primary" id="exportBtn">${icon('download', 14)} 导出结果</button>
      </div>
    </div>

    <div class="card"><div class="card-b" style="padding:14px 18px">${stepper(['导入线索', '画像解析', '四维评分', '分层与推荐'], 3, 3)}</div></div>

    <div class="grid grid-5 mt-16" id="section-tiers">
      ${kpi({ iconName: 'users', tone: 'blue', label: '总线索数', value: num(data.total), unit: '位', foot: `<span class="muted">候选池 ${data.platform_matched} 位 · 去重后</span>` })}
      ${kpi({ iconName: 'target', tone: 'green', label: '高分层（S/A）', value: num(data.high_tier), unit: '位', foot: `<span class="delta up">${pct(data.high_tier / (data.total || 1) * 100, 0)}</span> <span class="muted">占比</span>` })}
      ${kpi({ iconName: 'activity', tone: 'violet', label: '平均分', value: num(data.avg_score, 1), unit: '分', foot: `<span class="muted">批内相对排序</span>` })}
      ${kpi({ iconName: 'dollar', tone: 'amber', label: '预估合作总花费', value: money(data.estimated_spend), foot: `<span class="muted">按 ${money(data.budget)} 预算分配</span>` })}
      <div class="kpi tier-card">
        <div class="kpi-top"><span class="kpi-ico blue">${icon('pie', 16)}</span><span class="kpi-label">分层分布</span></div>
        <div class="donut-wrap" style="gap:8px">
          <div id="tierDonut"></div>
          <div class="donut-legend" id="tierLegend"></div>
        </div>
      </div>
    </div>

    <div class="split mt-16" style="grid-template-columns:minmax(0,1fr) 300px">
      <div>
        <section class="card">
          <div class="card-tools" style="padding-top:14px">
            <div class="tabs" id="kolTabs" style="border:0">
              <button class="tab on" data-tab="all">达人列表 <span class="count" id="cAll"></span></button>
              <button class="tab" data-tab="high">高分推荐 <span class="count" id="cHigh"></span></button>
              <button class="tab" data-tab="watch">待观察 <span class="count" id="cWatch"></span></button>
            </div>
            <div class="right flex" style="gap:8px">
              <select class="select" id="platformSel" style="width:120px;height:30px">
                <option value="">全部平台</option><option>抖音</option><option>小红书</option><option>视频号</option>
              </select>
              <select class="select" id="tierSel" style="width:110px;height:30px">
                <option value="">全部分层</option><option>S</option><option>A</option><option>B</option><option>C</option>
              </select>
              <div class="search" style="width:180px;margin:0">
                ${icon('search', 14)}
                <input id="kolSearch" placeholder="搜索达人 ID / 昵称" style="height:30px">
              </div>
            </div>
          </div>
          <div class="card-b flush" id="kolTable"></div>
        </section>

        <section class="card" id="agentRun">
          <div class="card-h">
            <h2>Agent 执行过程</h2>
            <span class="badge blue">Plan → Act → Observe → Reflect</span>
            <div class="right" id="agentRunActions">
              <button class="btn btn-sm btn-primary" id="runFilterBtn">${icon('play', 13)} 运行 Agent 筛选</button>
            </div>
          </div>
          <div class="card-b" id="agentRunBody">
            ${emptyState('还没有执行过筛选任务', 'terminal', '<div class="tiny" style="margin-top:6px">点击右上角「运行 Agent 筛选」，用当前筛选条件跑一次，执行计划与工具调用会显示在这里</div>')}
          </div>
        </section>
      </div>

      <div>
        <div class="panel" id="section-budget">
          <div class="panel-head"><h3>预算分配</h3><span class="badge ${data.allocation.feasible ? 'green' : 'red'}">${data.allocation.feasible ? '可行' : '不可行'}</span></div>
          <div class="flex nowrap" style="justify-content:space-between;font-size:12px;margin-bottom:6px;white-space:nowrap">
            <span class="muted">已分配</span><b>${money(data.estimated_spend)} / ${money(budget)}</b>
          </div>
          <div class="bar"><i style="width:${Math.min(100, data.estimated_spend / (budget || 1) * 100)}%"></i></div>
          <div class="flex" style="justify-content:space-between;margin-top:9px;font-size:11.5px">
            <span class="muted">入选 ${data.allocation.picked_count || 0} 位</span>
            <span class="muted">剩余 ${money(data.allocation.remaining || 0)}</span>
          </div>
          ${data.allocation.note ? `<div class="notice amber mt-12" style="font-size:11px">${icon('alert', 14)}<div>${esc(data.allocation.note)}</div></div>` : ''}
          <div class="hr"></div>
          <div class="flex" style="gap:8px">
            <span class="muted tiny">预算</span>
            <input class="input" id="budgetInline" type="number" value="${budget}" style="height:30px">
            <button class="btn btn-sm" id="budgetApply">应用</button>
          </div>
        </div>

        <div class="panel mt-16" id="section-outreach" style="margin-top:16px">
          <div class="panel-head"><h3>选中达人</h3><span class="badge" id="selCount">0</span>
            <div class="right"><button class="link-btn" id="clearSel">清空</button></div>
          </div>
          <div class="side-list" id="selList">${emptyState('在左侧表格勾选达人', 'users')}</div>
          <div class="flex mt-12" style="gap:8px">
            <button class="btn btn-sm btn-primary grow" id="briefBtn">${icon('sparkles', 13)} 生成合作方案</button>
          </div>
          <div class="flex mt-8" style="gap:8px">
            <select class="select" id="channelSel" style="width:96px;height:30px"><option>私信</option><option>邮件</option></select>
            <button class="btn btn-sm grow" id="outreachBtn">${icon('message', 13)} 生成邀约话术</button>
          </div>
        </div>

        <div class="panel mt-16">
          <div class="panel-head"><h3>评分依据</h3></div>
          <div class="score-basis">
            ${[['D1 匹配度', 30, 'blue'], ['D2 内容力', 25, 'green'], ['D3 转化力', 30, 'violet'], ['D4 性价比', 15, 'amber']]
              .map(([name, w, tone]) => `<div class="basis-row"><span class="name">${name}</span><span class="bar ${tone === 'blue' ? '' : tone}"><i style="width:${w * 3}%"></i></span><span class="val">${w}%</span></div>`).join('')}
          </div>
          <div class="hr"></div>
          <div class="muted tiny" style="line-height:1.6">${esc(data.note)}。<br>分层：S ≥ 75 / A ≥ 62 / B ≥ 50 / C &lt; 50。</div>
        </div>
      </div>
    </div>`;

  /* ---------- 渲染 ---------- */

  donut($('#tierDonut', root), data.distribution.map((d) => ({
    value: d.count,
    color: { S: '#8b5cf6', A: '#2563eb', B: '#10b981', C: '#cbd5e1' }[d.tier],
  })), { size: 92, thickness: 11, center: String(data.total) });

  $('#tierLegend', root).innerHTML = data.distribution.map((d) => `
    <div class="row"><span class="legend-dot" style="background:${{ S: '#8b5cf6', A: '#2563eb', B: '#10b981', C: '#cbd5e1' }[d.tier]}"></span>
      <b>${d.tier}</b><span class="muted">${d.count}</span><span class="pct">${(d.ratio * 100).toFixed(0)}%</span></div>`).join('');

  const counts = {
    all: data.rows.length,
    high: data.rows.filter((r) => r.tier === 'S' || r.tier === 'A').length,
    watch: data.rows.filter((r) => r.tier === 'C').length,
  };
  $('#cAll', root).textContent = counts.all;
  $('#cHigh', root).textContent = counts.high;
  $('#cWatch', root).textContent = counts.watch;

  bindFilters();
  renderTable();
  renderSelection();
  bindAgent();

  /* ---------- 表格 ---------- */

  function filteredRows() {
    let rows = data.rows;
    if (state.tab === 'high') rows = rows.filter((r) => r.tier === 'S' || r.tier === 'A');
    if (state.tab === 'watch') rows = rows.filter((r) => r.tier === 'C');
    if (state.platform) rows = rows.filter((r) => r.platform === state.platform);
    if (state.tier) rows = rows.filter((r) => r.tier === state.tier);
    if (state.q) {
      const q = state.q.toLowerCase();
      rows = rows.filter((r) => (r.handle + ' ' + r.kol_id + ' ' + r.category).toLowerCase().includes(q));
    }
    return rows;
  }

  function renderTable() {
    const rows = filteredRows();
    const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    state.page = Math.min(state.page, totalPages);
    const start = (state.page - 1) * PAGE_SIZE;
    const pageRows = rows.slice(start, start + PAGE_SIZE);
    const el = $('#kolTable', root);

    if (!rows.length) { el.innerHTML = emptyState('没有符合条件的达人', 'user-search'); return; }

    el.innerHTML = `<div class="table-wrap"><table class="table table-compact">
      <thead><tr>
        <th style="width:34px"><label class="checkbox"><input type="checkbox" id="selectAll"></label></th>
        <th>达人信息</th><th class="nw">粉丝数</th><th class="nw">预估报价</th>
        <th>四维评分 <span class="muted tiny">D1–D4</span></th><th class="nw">综合分</th><th class="nw">分层</th><th></th>
      </tr></thead>
      <tbody>${pageRows.map((r) => `
        <tr data-id="${esc(r.kol_id)}" class="${state.selected.has(r.kol_id) ? 'sel' : ''}">
          <td><label class="checkbox"><input type="checkbox" data-check="${esc(r.kol_id)}" ${state.selected.has(r.kol_id) ? 'checked' : ''}></label></td>
          <td><div class="name"><div>${avatar(r.handle)}</div>
            <div><div class="t1">${esc(r.handle)}</div><div class="t2">${esc(r.kol_id)} · ${esc(r.platform)} · ${esc(r.category)}</div></div></div></td>
          <td class="nw num">${compact(r.followers)}</td>
          <td class="nw num">${money(r.quote)}</td>
          <td><div class="dim-grid">${['D1', 'D2', 'D3', 'D4'].map((k) => `<span title="${k} 得分"><i>${k}</i><b>${num(r[k], 0)}</b></span>`).join('')}</div></td>
          <td class="nw"><b class="num" style="font-size:13.5px">${num(r.total, 1)}</b></td>
          <td class="nw">${tierBadge(r.tier)}</td>
          <td class="actions"><button class="link-btn" data-detail="${esc(r.kol_id)}">详情</button><button class="link-btn" data-outreach-row="${esc(r.kol_id)}" style="margin-left:8px">邀约</button></td>
        </tr>`).join('')}</tbody></table></div>
      <div class="pager">
        <span class="info">共 ${rows.length} 位 · 第 ${state.page}/${totalPages} 页</span>
        <button id="prevPage" ${state.page <= 1 ? 'disabled' : ''}>${icon('chevron-left', 13)}</button>
        ${Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
          const p = Math.max(1, Math.min(state.page - 2, totalPages - 4)) + i;
          return `<button data-page="${p}" class="${p === state.page ? 'on' : ''}">${p}</button>`;
        }).join('')}
        <button id="nextPage" ${state.page >= totalPages ? 'disabled' : ''}>${icon('chevron-right', 13)}</button>
      </div>`;

    $('#selectAll', el)?.addEventListener('change', (e) => {
      pageRows.forEach((r) => e.target.checked ? state.selected.add(r.kol_id) : state.selected.delete(r.kol_id));
      renderTable(); renderSelection();
    });
    $$('[data-check]', el).forEach((cb) => cb.addEventListener('change', () => {
      const id = cb.dataset.check;
      cb.checked ? state.selected.add(id) : state.selected.delete(id);
      renderSelection();
      cb.closest('tr').classList.toggle('sel', cb.checked);
    }));
    $$('[data-detail]', el).forEach((btn) => btn.addEventListener('click', () => showDetail(btn.dataset.detail)));
    $$('[data-outreach-row]', el).forEach((btn) => btn.addEventListener('click', () => openOutreach([btn.dataset.outreachRow])));
    $$('[data-page]', el).forEach((btn) => btn.addEventListener('click', () => { state.page = Number(btn.dataset.page); renderTable(); }));
    $('#prevPage', el)?.addEventListener('click', () => { state.page--; renderTable(); });
    $('#nextPage', el)?.addEventListener('click', () => { state.page++; renderTable(); });
  }

  /* ---------- 选中面板 ---------- */

  function renderSelection() {
    const ids = [...state.selected];
    const rows = data.rows.filter((r) => state.selected.has(r.kol_id));
    $('#selCount', root).textContent = String(ids.length);
    const list = $('#selList', root);
    if (!rows.length) { list.innerHTML = emptyState('在左侧表格勾选达人', 'users'); return; }
    const spend = rows.reduce((a, r) => a + Number(r.quote || 0), 0);
    list.innerHTML = rows.slice(0, 6).map((r, i) => `
      <div class="pick-row">
        <span class="rank">${i + 1}</span>
        <div class="grow" style="min-width:0"><div class="t1">${esc(r.handle)}</div><div class="t2">${esc(r.platform)} · ${num(r.total, 1)} 分 · ${r.tier} 层</div></div>
        <span class="amt">${money(r.quote)}</span>
        <button class="icon-btn" style="width:22px;height:22px" data-remove="${esc(r.kol_id)}">${icon('x', 12)}</button>
      </div>`).join('') + (rows.length > 6 ? `<div class="muted tiny">还有 ${rows.length - 6} 位…</div>` : '')
      + `<div class="flex" style="justify-content:space-between;margin-top:4px;font-size:11.5px"><span class="muted">合计报价</span><b>${money(spend)}</b></div>`;
    $$('[data-remove]', list).forEach((b) => b.addEventListener('click', () => {
      state.selected.delete(b.dataset.remove); renderTable(); renderSelection();
    }));
  }

  /* ---------- 详情 ---------- */

  function showDetail(id) {
    const r = data.rows.find((x) => x.kol_id === id);
    if (!r) return;
    const rows = [['D1 匹配度', r.D1, 30], ['D2 内容力', r.D2, 25], ['D3 转化力', r.D3, 30], ['D4 性价比', r.D4, 15]];
    openModal({
      title: `${r.handle} · ${r.kol_id}`,
      body: `
        <div class="flex wrap" style="gap:8px;margin-bottom:14px">
          ${platformTag(r.platform)}<span class="badge gray">${esc(r.category)}</span>
          <span class="badge gray">${esc(r.content_category)}</span>${tierBadge(r.tier)}
        </div>
        <div class="grid grid-4" style="gap:10px;margin-bottom:14px">
          ${[['粉丝数', compact(r.followers)], ['预估报价', money(r.quote)], ['互动率', pct(r.engagement_rate * 100, 2)], ['履约率', pct(r.fulfill_rate * 100, 1)]]
            .map(([k, v]) => `<div class="panel" style="padding:10px"><div class="muted tiny">${k}</div><div style="font-size:16px;font-weight:700;margin-top:3px">${v}</div></div>`).join('')}
        </div>
        <div class="field-label">四维评分明细（加权：匹配 30 / 内容 25 / 转化 30 / 成本 15）</div>
        ${rows.map(([name, v, w]) => `<div class="basis-row" style="margin-bottom:8px"><span class="name">${name}</span>
          <span class="bar"><i style="width:${v}%"></i></span><span class="val">${num(v, 1)}</span><span class="muted tiny" style="width:34px;text-align:right">×${w}%</span></div>`).join('')}
        <div class="flex" style="justify-content:space-between;margin-top:12px;padding-top:12px;border-top:1px solid var(--line)">
          <span class="muted">综合分</span><b style="font-size:20px">${num(r.total, 1)}</b>
        </div>
        <div class="notice mt-12">${icon('target', 15)}<div>${esc(data.note)}。换一批候选，同一达人的分数会变。</div></div>`,
      footer: `<button class="btn btn-sm" id="pickDetail">${icon('plus', 13)} 加入选中</button><span class="spacer"></span><button class="btn btn-sm" id="closeDetail">关闭</button>`,
      size: 'sm',
      onMount(el, close) {
        $('#closeDetail', el).addEventListener('click', close);
        $('#pickDetail', el).addEventListener('click', () => {
          state.selected.add(id); close(); renderTable(); renderSelection(); toast('已加入选中');
        });
      },
    });
  }

  /* ---------- 筛选交互 ---------- */

  function bindFilters() {
    $$('#kolTabs .tab', root).forEach((tab) => tab.addEventListener('click', () => {
      $$('#kolTabs .tab', root).forEach((t) => t.classList.toggle('on', t === tab));
      state.tab = tab.dataset.tab; state.page = 1; renderTable();
    }));
    $('#platformSel', root).addEventListener('change', (e) => { state.platform = e.target.value; state.page = 1; renderTable(); });
    $('#tierSel', root).addEventListener('change', (e) => { state.tier = e.target.value; state.page = 1; renderTable(); });
    const search = $('#kolSearch', root);
    search.value = state.q;
    search.addEventListener('input', (e) => { state.q = e.target.value.trim(); state.page = 1; renderTable(); });

    $('#refreshBtn', root).addEventListener('click', () => { renderKols(root, {}); });
    $('#exportBtn', root).addEventListener('click', () => {
      const ids = [...state.selected];
      window.open(api.exportUrl(ids, store.budget), '_blank');
      toast(ids.length ? `导出选中的 ${ids.length} 位达人` : '导出当前全部评分结果');
    });
    $('#budgetApply', root).addEventListener('click', async () => {
      const v = Number($('#budgetInline', root).value) || 8000;
      store.budget = v;
      localStorage.setItem('kol.budget', String(v));
      toast('预算已更新，正在重算…');
      renderKols(root, {});
    });

    $('#briefBtn', root).addEventListener('click', async () => {
      const ids = [...state.selected];
      if (!ids.length) { toast('先勾选达人', 'err'); return; }
      try {
        const md = await api.brief(ids);
        openModal({
          title: `合作方案 · ${ids.length} 位达人`,
          body: `<div class="markdown" id="briefBody" style="max-height:52vh;overflow:auto;padding:2px 4px"></div>`,
          footer: `<button class="btn btn-sm" id="copyBrief">${icon('copy', 13)} 复制 Markdown</button><span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeBrief">关闭</button>`,
          onMount(el, close) {
            mountMarkdown($('#briefBody', el), md);
            $('#copyBrief', el).addEventListener('click', () => copyText(md));
            $('#closeBrief', el).addEventListener('click', close);
          },
        });
      } catch (e) { toast('生成失败：' + e.message, 'err'); }
    });

    $('#outreachBtn', root).addEventListener('click', () => {
      const ids = [...state.selected];
      if (!ids.length) { toast('先勾选达人', 'err'); return; }
      openOutreach(ids, $('#channelSel', root).value);
    });

    $('#clearSel', root).addEventListener('click', () => { state.selected.clear(); renderTable(); renderSelection(); });
  }

  /* ---------- Agent 执行过程 ---------- */

  async function executeRun() {
    const btn = $('#runFilterBtn', root);
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>执行中'; }
    const goal = `筛选${state.platform || '全平台'}达人，预算 ${store.budget} 元${state.tier ? `，只看 ${state.tier} 层` : ''}，输出可投名单与预算分配`;
    try {
      const rec = await runAgent(goal);
      state.rec = rec;
      renderAgent(rec);
      toast('Agent 执行完成');
    } catch (e) {
      toast('执行失败：' + e.message, 'err');
      $('#agentRunBody', root).innerHTML = `<div class="notice red">${icon('alert', 15)}<div>${esc(e.message)}</div></div>`;
      if (btn) { btn.disabled = false; btn.innerHTML = `${icon('play', 13)} 运行 Agent 筛选`; }
    }
  }

  function bindAgent() {
    $('#runFilterBtn', root).addEventListener('click', executeRun);
  }

  function renderAgent(rec) {
    const meta = rec.agent_meta || {};
    const trace = rec.trace || [];
    const plan = meta.plan;
    const hasPlan = !!(plan && (Array.isArray(plan) ? plan.length : String(plan).trim()));
    const hasAct = trace.length > 0;
    const hasFinal = !!rec.final;
    const stages = [
      { name: 'Plan', cn: '规划', done: hasPlan, sub: hasPlan ? '已产出计划' : '待执行' },
      { name: 'Act', cn: '工具调用', done: hasAct, sub: hasAct ? `${trace.length} 次调用` : '待执行' },
      { name: 'Observe', cn: '观察结果', done: hasAct, sub: hasAct ? '事实已回灌' : '待执行' },
      { name: 'Reflect', cn: '自检优化', done: hasFinal, sub: hasFinal ? '已自检' : '待执行' },
    ];
    const alloc = rec.view?.allocation || {};
    const picks = alloc.plan || [];

    $('#agentRunActions', root).innerHTML = `
      <span class="badge ${rec.planner === 'llm' ? 'blue' : 'gray'}">${rec.planner === 'llm' ? 'LLM 规划' : '规则规划'}</span>
      <span class="badge">${rec.steps || 0} 步</span>
      <span class="badge">${duration(rec.elapsed_ms)}</span>
      <button class="btn btn-sm" id="fullRun">查看完整结论</button>
      <button class="btn btn-sm" id="runFilterBtn">${icon('refresh', 13)} 重新运行</button>`;

    $('#agentRunBody', root).innerHTML = `
      <div class="panel" style="background:var(--surface-2);margin-bottom:14px">
        <div class="flex wrap" style="gap:10px">
          <div class="grow" style="min-width:240px">
            <div class="muted tiny">任务目标</div>
            <div style="font-weight:600;margin-top:3px">${esc(rec.goal || '—')}</div>
          </div>
          <div><div class="muted tiny">规划器</div><div style="font-weight:600;margin-top:3px">${rec.planner === 'llm' ? 'LLM' : '规则基线'}</div></div>
          <div><div class="muted tiny">耗时</div><div style="font-weight:600;margin-top:3px">${duration(rec.elapsed_ms)}</div></div>
          <div><div class="muted tiny">状态</div><div style="margin-top:3px"><span class="badge green dot">已完成</span></div></div>
        </div>
      </div>

      <div class="agent-steps mb-12">
        ${stages.map((s, i) => `
          <div class="agent-step ${s.done ? 'done' : ''}">
            <span class="c">${s.done ? icon('check', 12) : i + 1}</span>
            <div><div class="t">${s.name} · ${s.cn}</div><div class="s">${esc(s.sub)}</div></div>
          </div>${i < stages.length - 1 ? `<span class="agent-arrow">${icon('arrow-right', 14)}</span>` : ''}`).join('')}
      </div>

      <div class="split-wide" style="gap:14px">
        <div>
          <div class="field-label">执行步骤与工具调用</div>
          <div class="trace">
            ${trace.length ? trace.map((t, i) => `
              <div class="trace-row">
                <span class="trace-no">${t.step || i + 1}</span>
                <div class="grow">
                  <div class="t1">${esc(truncate(t.thought || '（无思考文本）', 90))}</div>
                  <div class="t2 flex wrap" style="gap:6px">
                    <span class="trace-tool">${icon('terminal', 11)} ${esc(t.tool || '—')}</span>
                    <span class="muted tiny">${esc(truncate(JSON.stringify(t.args || {}), 60))}</span>
                    <span class="muted tiny">· ${duration(t.elapsed_ms)}</span>
                  </div>
                </div>
              </div>`).join('') : '<div class="empty">没有工具调用</div>'}
          </div>
        </div>
        <div>
          <div class="field-label">任务结果预览</div>
          <div class="panel" style="padding:10px">
            <div class="flex" style="justify-content:space-between;font-size:11.5px;margin-bottom:8px">
              <span class="muted">入选 ${picks.length} 位</span><b>${money(alloc.spent || 0)} / ${money(alloc.budget || store.budget)}</b>
            </div>
            <div class="side-list">
              ${picks.slice(0, 5).map((p, i) => `<div class="pick-row" style="background:#fff">
                <span class="rank">${i + 1}</span>
                <div class="grow"><div class="t1">${esc(p.handle)}</div><div class="t2">${esc(p.platform)} · ${num(p.score, 1)} 分 · ${p.tier}</div></div>
                <span class="amt">${money(p.quote)}</span></div>`).join('') || '<div class="muted tiny">本次没有入选达人</div>'}
            </div>
            ${(rec.warnings || []).length ? `<div class="notice amber mt-12" style="font-size:11px">${icon('alert', 13)}<div>${rec.warnings.map(esc).join('<br>')}</div></div>` : ''}
          </div>
          ${meta.tokens ? `<div class="muted tiny mt-8">用量：${num(meta.tokens)} tokens</div>` : ''}
        </div>
      </div>

      <div class="mt-12" style="display:grid;gap:14px">
        <div>
          <div class="field-label">工具调用记录</div>
          <div class="table-wrap"><table class="table table-compact">
            <thead><tr><th class="nw">步骤</th><th class="nw">工具</th><th>参数</th><th class="nw">结果</th></tr></thead>
            <tbody>${trace.map((t, i) => `<tr>
              <td class="nw muted">${t.step || i + 1}</td>
              <td class="nw"><span class="trace-tool">${esc(t.tool || '—')}</span></td>
              <td class="muted" style="font-family:var(--mono);font-size:10.5px" title="${esc(JSON.stringify(t.args || {}))}">${esc(truncate(JSON.stringify(t.args || {}), 30))}</td>
              <td class="nw"><span class="badge green dot">成功</span> <span class="muted tiny">${duration(t.elapsed_ms)}</span></td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>
        <div>
          <div class="field-label">实时思考过程</div>
          <div class="thought-box">
            ${trace.slice(-3).map((t) => `<div class="thought-line"><span class="badge gray">第 ${t.step || '?'} 步</span>
              <div>${esc(t.thought || '（无思考文本）')}</div></div>`).join('') || '<div class="muted tiny">没有思考记录</div>'}
          </div>
        </div>
      </div>`;

    $('#fullRun', root).addEventListener('click', () => openRunModal(rec));
    $('#runFilterBtn', root).addEventListener('click', executeRun);
  }
}
