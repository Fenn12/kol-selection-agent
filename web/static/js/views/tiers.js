// 达人分层
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, kpi, tierBadge, platformTag, avatar, emptyState, toast } from '../ui.js';
import { compact, money, num } from '../format.js';
import { donut } from '../charts.js';
import { showCandidate, openOutreach } from '../kol-actions.js';

const TIERS = ['S', 'A', 'B', 'C'];
const TIER_COLOR = { S: '#8b5cf6', A: '#2563eb', B: '#10b981', C: '#cbd5e1' };
const ACTION = { S: '首席约谈', A: '优先约谈', B: '小预算测试', C: '观察' };

export async function renderTiers(root) {
  const data = await api.candidates({ budget: store.budget });
  const state = { tier: 'A', page: 1 };

  const byTier = Object.fromEntries(TIERS.map((t) => [t, data.rows.filter((r) => r.tier === t)]));
  const stat = (t) => {
    const rows = byTier[t];
    const avg = rows.length ? rows.reduce((a, r) => a + r.total, 0) / rows.length : 0;
    const quote = rows.reduce((a, r) => a + Number(r.quote), 0);
    return { count: rows.length, avg, quote };
  };

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>达人分层</h1>
        <p>按 S ≥ 75 / A ≥ 62 / B ≥ 50 / C &lt; 50 分层，每层给出平均分与预算口径，可直接导出或约谈。</p>
      </div>
      <div class="actions">
        <button class="btn" id="exportAll">${icon('download', 14)} 导出全部</button>
        <button class="btn btn-primary" id="goKols">${icon('user-search', 14)} 去筛选达人</button>
      </div>
    </div>

    <div class="grid grid-4">
      ${TIERS.map((t) => {
        const s = stat(t);
        return `<div class="kpi" data-tier-card="${t}" style="cursor:pointer">
          <div class="kpi-top"><span class="tier ${t}" style="width:28px;height:28px;border-radius:8px;font-size:12px">${t}</span>
            <span class="kpi-label">${t} 层</span>
            <span class="badge ${t === 'S' ? 'violet' : t === 'A' ? 'blue' : t === 'B' ? 'green' : 'gray'} right">${ACTION[t]}</span></div>
          <div class="kpi-value">${num(s.count)}<small>位</small></div>
          <div class="kpi-foot"><span class="muted">平均 ${num(s.avg, 1)} 分 · 报价合计 ${money(s.quote)}</span></div>
        </div>`;
      }).join('')}
    </div>

    <div class="split mt-16" style="grid-template-columns:minmax(0,1fr) 320px">
      <section class="card">
        <div class="card-tools" style="padding-top:14px">
          <div class="tabs" id="tierTabs" style="border:0">
            ${TIERS.map((t) => `<button class="tab ${t === state.tier ? 'on' : ''}" data-tier="${t}">
              ${t} 层 <span class="count">${byTier[t].length}</span></button>`).join('')}
          </div>
          <div class="right muted tiny" id="tierMeta"></div>
        </div>
        <div class="card-b flush" id="tierTable"></div>
      </section>

      <div>
        <div class="panel">
          <div class="panel-head"><h3>分层分布</h3></div>
          <div class="donut-wrap" style="flex-direction:column;align-items:stretch">
            <div id="tierDonut" style="align-self:center"></div>
            <div class="donut-legend" style="display:grid;grid-template-columns:1fr 1fr;gap:4px 12px">
              ${TIERS.map((t) => `<div class="row"><span class="legend-dot" style="background:${TIER_COLOR[t]}"></span>
                <b>${t}</b><span class="muted">${byTier[t].length}</span><span class="pct" style="margin-left:auto">${(byTier[t].length / (data.total || 1) * 100).toFixed(0)}%</span></div>`).join('')}
            </div>
          </div>
        </div>
        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><h3>分层规则</h3></div>
          <div class="muted tiny" style="line-height:1.9">
            · S：≥ 75 分，首席约谈，优先锁档期<br>
            · A：62–74 分，优先约谈，可给货盘<br>
            · B：50–61 分，小预算测试，先看单条效果<br>
            · C：&lt; 50 分，观察，不建议本期投放<br><br>
            分数是候选池内相对排序，换一批候选会变；报价与预算口径以实际为准。
          </div>
        </div>
      </div>
    </div>`;

  donut($('#tierDonut', root), TIERS.map((t) => ({ value: byTier[t].length, color: TIER_COLOR[t] })), {
    size: 132, thickness: 14, center: String(data.total),
  });

  renderTable();

  $$('#tierTabs .tab', root).forEach((tab) => tab.addEventListener('click', () => {
    $$('#tierTabs .tab', root).forEach((t) => t.classList.toggle('on', t === tab));
    state.tier = tab.dataset.tier;
    state.page = 1;
    renderTable();
  }));

  $$('[data-tier-card]', root).forEach((card) => card.addEventListener('click', () => {
    state.tier = card.dataset.tierCard;
    state.page = 1;
    $$('#tierTabs .tab', root).forEach((t) => t.classList.toggle('on', t.dataset.tier === state.tier));
    renderTable();
    document.querySelector('#tierTable').scrollIntoView({ behavior: 'smooth', block: 'center' });
  }));

  $('#goKols', root).addEventListener('click', () => { location.hash = '#/kols'; });
  $('#exportAll', root).addEventListener('click', () => {
    window.open(api.exportUrl([], store.budget), '_blank');
    toast('已导出全部评分名单');
  });

  function renderTable() {
    const rows = byTier[state.tier].slice().sort((a, b) => b.total - a.total);
    const el = $('#tierTable', root);
    $('#tierMeta', root).textContent = `${rows.length} 位 · 平均 ${num(rows.length ? rows.reduce((a, r) => a + r.total, 0) / rows.length : 0, 1)} 分`;
    if (!rows.length) { el.innerHTML = emptyState(`没有 ${state.tier} 层达人`, 'layers'); return; }

    const dimName = (r) => {
      const dims = [['D1 匹配', r.D1], ['D2 内容', r.D2], ['D3 转化', r.D3], ['D4 性价比', r.D4]];
      return dims.sort((a, b) => b[1] - a[1])[0][0];
    };

    el.innerHTML = `<div class="table-wrap"><table class="table table-compact">
      <thead><tr><th>达人</th><th class="nw">平台</th><th class="nw">粉丝</th><th class="nw">报价</th><th class="nw">综合分</th><th class="nw">最强维度</th><th class="nw">建议动作</th><th></th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td><div class="name">${avatar(r.handle)}<div><div class="t1">${esc(r.handle)}</div><div class="t2">${esc(r.kol_id)} · ${esc(r.category)}</div></div></div></td>
        <td class="nw">${platformTag(r.platform)}</td>
        <td class="nw num">${compact(r.followers)}</td>
        <td class="nw num">${money(r.quote)}</td>
        <td class="nw"><b class="num">${num(r.total, 1)}</b></td>
        <td class="nw"><span class="badge gray">${dimName(r)}</span></td>
        <td class="nw"><span class="badge ${r.tier === 'S' ? 'violet' : r.tier === 'A' ? 'blue' : r.tier === 'B' ? 'green' : 'gray'}">${ACTION[r.tier]}</span></td>
        <td class="actions"><button class="link-btn" data-detail="${esc(r.kol_id)}">详情</button>
          ${r.tier === 'C' ? '' : `<button class="link-btn" data-outreach="${esc(r.kol_id)}" style="margin-left:8px">邀约</button>`}</td>
      </tr>`).join('')}</tbody></table></div>
      <div class="pager"><span class="info">共 ${rows.length} 位</span>
        <span class="muted tiny">按综合分降序</span></div>`;

    $$('[data-detail]', el).forEach((b) => b.addEventListener('click', () => {
      const row = data.rows.find((x) => x.kol_id === b.dataset.detail);
      showCandidate(row, { note: data.note });
    }));
    $$('[data-outreach]', el).forEach((b) => b.addEventListener('click', () => openOutreach([b.dataset.outreach])));
  }
}
