// 预算管理
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, kpi, emptyState, toast, platformTag, tierBadge } from '../ui.js';
import { money, num } from '../format.js';

const QUICK = [4000, 8000, 12000, 20000];

export async function renderBudget(root) {
  let budget = store.budget;
  let data = await api.candidates({ budget, top_n: 20 });

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>预算管理</h1>
        <p>按「分数 / 成本」性价比贪心分配，只在 S/A/B 层里选；预算不足会直接报告缺口，不硬凑名单。</p>
      </div>
      <div class="actions">
        <button class="btn" id="budgetExport">${icon('download', 14)} 导出名单</button>
        <button class="btn btn-primary" id="budgetToKols">${icon('user-search', 14)} 去筛选达人</button>
      </div>
    </div>

    <div class="grid grid-4" id="budgetKpis"></div>

    <div class="split mt-16" style="grid-template-columns:minmax(0,1fr) 330px">
      <section class="card">
        <div class="card-h"><h2>入选名单</h2><span class="badge gray" id="pickMeta"></span>
          <div class="right muted tiny">按性价比降序，最终按综合分展示</div></div>
        <div class="card-b flush" id="budgetTable"></div>
      </section>

      <div>
        <div class="panel">
          <div class="panel-head"><h3>预算设置</h3></div>
          <div class="flex" style="gap:8px">
            <input class="input" id="budgetInput" type="number" min="0" step="500" value="${budget}">
            <button class="btn btn-sm" id="budgetApply">测算</button>
          </div>
          <div class="flex wrap mt-12" style="gap:6px">
            ${QUICK.map((v) => `<button class="chip" data-quick="${v}" style="height:26px;font-size:11.5px">${money(v)}</button>`).join('')}
          </div>
        </div>
        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><h3>使用情况</h3></div>
          <div class="flex" style="justify-content:space-between;font-size:12px;margin-bottom:6px">
            <span class="muted">已分配</span><b id="spentText"></b>
          </div>
          <div class="bar"><i id="spentBar" style="width:0%"></i></div>
          <div class="flex" style="justify-content:space-between;margin-top:8px">
            <span class="muted tiny" id="leftText"></span>
            <span class="muted tiny" id="pickCountText"></span>
          </div>
          <div id="allocNote" class="mt-12"></div>
        </div>
        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><h3>分配规则</h3></div>
          <div class="muted tiny" style="line-height:1.9">
            · 只在 S/A/B 层里选，C 层不参与<br>
            · 性价比 = 综合分 ÷ 报价 × 1000<br>
            · 剩余预算 &gt; 30% 时提示扩池或换更高分层<br>
            · 预算低于最低报价 → 直接 BLOCK，报告最低预算
          </div>
        </div>
      </div>
    </div>`;

  render(data);

  $('#budgetApply', root).addEventListener('click', apply);
  $('#budgetInput', root).addEventListener('keydown', (e) => { if (e.key === 'Enter') apply(); });
  $$('[data-quick]', root).forEach((b) => b.addEventListener('click', () => {
    $('#budgetInput', root).value = b.dataset.quick;
    apply();
  }));
  $('#budgetToKols', root).addEventListener('click', () => { location.hash = '#/kols'; });
  $('#budgetExport', root).addEventListener('click', () => {
    const ids = (data.allocation.plan || []).map((p) => p.kol_id);
    window.open(api.exportUrl(ids, budget), '_blank');
    toast(ids.length ? `导出 ${ids.length} 位入选达人` : '当前没有入选达人');
  });

  async function apply() {
    const v = Number($('#budgetInput', root).value) || 8000;
    budget = v;
    store.budget = v;
    localStorage.setItem('kol.budget', String(v));
    data = await api.candidates({ budget, top_n: 20 });
    render(data);
    toast('已按 ' + money(v) + ' 重新测算');
  }

  function render(data) {
    const alloc = data.allocation || {};
    const picks = alloc.plan || [];
    const spent = Number(alloc.spent || 0);
    const pct = budget ? Math.min(100, spent / budget * 100) : 0;

    $('#budgetKpis', root).innerHTML = [
      kpi({ iconName: 'dollar', tone: 'blue', label: '预算', value: money(budget), foot: `<span class="muted">本期可分配</span>` }),
      kpi({ iconName: 'target', tone: 'green', label: '已分配', value: money(spent), foot: `<span class="muted">${pct.toFixed(0)}% 预算使用率</span>` }),
      kpi({ iconName: 'activity', tone: 'amber', label: '剩余', value: money(alloc.remaining ?? budget - spent), foot: `<span class="muted">可用于加投</span>` }),
      kpi({ iconName: 'users', tone: 'violet', label: '入选达人', value: num(alloc.picked_count || 0), unit: '位', foot: `<span class="muted">S/A/B 层中性价比优先</span>` }),
    ].join('');

    $('#spentText', root).textContent = `${money(spent)} / ${money(budget)}`;
    $('#spentBar', root).style.width = pct + '%';
    $('#leftText', root).textContent = `剩余 ${money(alloc.remaining ?? 0)}`;
    $('#pickCountText', root).textContent = `${picks.length} 位入选`;
    $('#allocNote', root).innerHTML = alloc.feasible
      ? (alloc.note ? `<div class="notice amber" style="font-size:11px">${icon('alert', 14)}<div>${esc(alloc.note)}</div></div>`
        : `<div class="notice" style="font-size:11px">${icon('check-circle', 14)}<div>预算已按性价比分配完毕。</div></div>`)
      : `<div class="notice red" style="font-size:11px">${icon('alert', 14)}<div>${esc(alloc.reason || '预算不可行')}${alloc.min_budget_needed ? `<br>最低预算：${money(alloc.min_budget_needed)}` : ''}</div></div>`;

    const el = $('#budgetTable', root);
    $('#pickMeta', root).textContent = `${picks.length} 位`;
    if (!picks.length) {
      el.innerHTML = emptyState(alloc.feasible ? '当前预算下没有可入选的达人' : '预算不可行，名单为空', 'dollar');
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table class="table table-compact">
      <thead><tr><th>#</th><th>达人</th><th class="nw">平台</th><th class="nw">分层</th><th class="nw">综合分</th><th class="nw">报价</th><th class="nw">性价比</th><th>入选理由</th></tr></thead>
      <tbody>${picks.map((p, i) => {
        const row = data.rows.find((r) => r.kol_id === p.kol_id) || {};
        return `<tr>
          <td class="nw muted">${i + 1}</td>
          <td><div class="name"><div><div class="t1">${esc(p.handle)}</div><div class="t2">${esc(p.kol_id)}</div></div></div></td>
          <td class="nw">${platformTag(p.platform)}</td>
          <td class="nw">${tierBadge(p.tier)}</td>
          <td class="nw"><b class="num">${num(p.score, 1)}</b></td>
          <td class="nw num">${money(p.quote)}</td>
          <td class="nw num">${num(p.value_index, 2)}</td>
          <td class="muted">${esc(p.reason || '—')}</td>
        </tr>`;
      }).join('')}</tbody></table></div>`;
  }
}
