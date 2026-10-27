// 投放策略：销售结构 → 简报
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, kpi, emptyState, toast } from '../ui.js';
import { money, num, pct } from '../format.js';

export async function renderStrategy(root) {
  const s = await api.strategy('起量');
  if (s.error) {
    root.innerHTML = `<div class="card"><div class="card-b"><div class="notice red">${esc(s.error)}</div></div></div>`;
    return;
  }

  const mix = s['达人类型配比'] || {};
  const channel = s.channel || {};
  const basis = s['判断依据'] || {};
  const bands = s['价格带备选'] || [s['价格带定位']];

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>投放策略</h1>
        <p>从商品销售结构推导主推渠道、达人配比与价格带——先看数据，再决定找哪类达人。</p>
      </div>
      <div class="actions">
        <button class="btn" id="recalc">${icon('refresh', 14)} 重新计算</button>
        <button class="btn btn-primary" id="strategyToKols">${icon('user-search', 14)} 按策略筛选达人</button>
      </div>
    </div>

    <div class="grid grid-4">
      ${kpi({ iconName: 'megaphone', tone: 'blue', label: '主推渠道', value: esc(s['主推渠道'] || '—'), foot: `<span class="muted">按销量结构判断</span>` })}
      ${kpi({ iconName: 'dollar', tone: 'amber', label: '客单价', value: money(s.aov, 1), foot: `<span class="badge ${s.aov_conf === '低' ? 'amber' : 'green'}">置信度 ${esc(s.aov_conf || '—')}</span>` })}
      ${kpi({ iconName: 'target', tone: 'violet', label: '价格带定位', value: esc(s['价格带定位'] || '—'), foot: `<span class="muted">备选 ${esc(bands.join(' / '))}</span>` })}
      ${kpi({ iconName: 'users', tone: 'green', label: '人均产出', value: num(s.creators?.['人均产出_件'], 1), unit: '件', foot: `<span class="muted">单条视频 ${num(s.creators?.['单条视频产出_件'], 1)} 件</span>` })}
    </div>

    <div class="split mt-16">
      <div>
        <section class="card">
          <div class="card-h"><h2>渠道结构</h2><div class="right muted tiny">近 28 天销量占比</div></div>
          <div class="card-b">
            ${Object.keys(channel).length ? Object.entries(channel).map(([k, v]) => `
              <div style="margin-bottom:13px">
                <div class="flex" style="justify-content:space-between;font-size:12px;margin-bottom:5px">
                  <span>${esc(k)}</span>
                  <span class="muted">${pct((v.占比 || 0) * 100, 1)} · ${num(v.销量)} 件</span>
                </div>
                <div class="bar"><i style="width:${(v.占比 || 0) * 100}%"></i></div>
              </div>`).join('') : emptyState('无渠道数据', 'chart')}
            <div class="notice ${s.aov_conf === '低' ? 'amber' : ''} mt-12">
              ${icon(s.aov_conf === '低' ? 'alert' : 'check-circle', 14)}
              <div>${s.aov_conf === '低'
                ? '客单价由「销售额区间中值 ÷ 销量区间中值」派生，置信度低；不要拿它去硬筛价格带，建议改用实际成交价。'
                : '客单价置信度正常，可作为价格带筛选依据。'}</div>
            </div>
          </div>
        </section>

        <section class="card">
          <div class="card-h"><h2>判断依据</h2><div class="right muted tiny">来自 parse_product_sales</div></div>
          <div class="card-b flush">
            <div class="table-wrap"><table class="table">
              <thead><tr><th>指标</th><th>取值</th><th>怎么用</th></tr></thead>
              <tbody>
                <tr><td>直播占比</td><td class="num">${pct((basis['直播占比'] || 0) * 100, 1)}</td><td class="muted">决定要不要优先达播</td></tr>
                <tr><td>视频占比</td><td class="num">${pct((basis['视频占比'] || 0) * 100, 1)}</td><td class="muted">决定短视频种草配比</td></tr>
                <tr><td>商品卡占比</td><td class="num">${pct((basis['商品卡占比'] || 0) * 100, 1)}</td><td class="muted">搜索/货架承接能力</td></tr>
                <tr><td>人均产出</td><td class="num">${num(basis['人均产出_件'], 1)} 件</td><td class="muted">判断达播效率</td></tr>
                <tr><td>客单价置信度</td><td><span class="badge ${basis['客单价置信度'] === '低' ? 'amber' : 'green'}">${esc(basis['客单价置信度'] || '—')}</span></td><td class="muted">低置信度时不硬筛价格带</td></tr>
              </tbody></table></div>
          </div>
        </section>
      </div>

      <div>
        <div class="panel">
          <div class="panel-head"><h3>达人类型配比</h3></div>
          <div class="score-basis">
            ${Object.entries(mix).map(([k, v]) => `<div class="basis-row">
              <span class="name" style="width:76px">${esc(k)}</span>
              <span class="bar"><i style="width:${v * 100}%"></i></span>
              <span class="val">${(v * 100).toFixed(0)}%</span></div>`).join('')}
          </div>
          <div class="muted tiny mt-12">按销售结构推导的初始配比，实际以候选池供给为准。</div>
        </div>

        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><h3>内容方向</h3></div>
          <div class="flex wrap" style="gap:6px">
            ${(s['内容方向'] || []).map((c) => `<span class="badge blue">${esc(c)}</span>`).join('')}
          </div>
          <div class="field-label mt-12">需要回避</div>
          <div class="flex wrap" style="gap:6px">
            ${(s['需要回避'] || []).map((c) => `<span class="badge red">${esc(c)}</span>`).join('')}
          </div>
        </div>

        <div class="panel" style="margin-top:16px">
          <div class="panel-head"><h3>价格带</h3></div>
          <div class="flex wrap" style="gap:6px">
            ${bands.map((b, i) => `<span class="badge ${i === 0 ? 'blue' : 'gray'}">${esc(b)}${i === 0 ? '（定位）' : '（备选）'}</span>`).join('')}
          </div>
          <div class="notice mt-12" style="font-size:11px">${icon('target', 14)}<div>置信度低时先小预算测试两个相邻价格带。</div></div>
        </div>
      </div>
    </div>`;

  $('#strategyToKols', root).addEventListener('click', () => {
    store.budget = store.budget || 8000;
    location.hash = '#/kols';
  });
  $('#recalc', root).addEventListener('click', () => { renderStrategy(root); toast('已按最新销售结构重算'); });
}
