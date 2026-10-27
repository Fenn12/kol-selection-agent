// 数据监测 / 异常告警
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, openModal, emptyState, kpi } from '../ui.js';
import { compact, money, num, pct } from '../format.js';
import { lineChart } from '../charts.js';

export async function renderMonitor(root) {
  const [ov, trend] = await Promise.all([api.overview(store.budget), api.trend(30)]);
  store.overview = ov;
  const mon = ov.monitor || {};
  const review = ov.review || {};
  const todos = ov.todos || [];

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>数据监测</h1>
        <p>滚动窗口比对近 ${mon.window?.recent_days || 3} 天 vs 近 ${mon.window?.baseline_days || 7} 天中位数基线，P0 才推送，避免告警疲劳。</p>
      </div>
      <div class="actions">
        <button class="btn" id="monRefresh">${icon('refresh', 14)} 重新扫描</button>
        <button class="btn btn-primary" id="monReport">${icon('file-text', 14)} 生成日报</button>
      </div>
    </div>

    <div class="grid grid-4">
      ${kpi({ iconName: 'alert', tone: 'red', label: 'P0 告警', value: num(mon.p0), unit: '条', foot: '<span class="muted">需当天处理</span>' })}
      ${kpi({ iconName: 'alert', tone: 'amber', label: 'P1 告警', value: num(mon.p1), unit: '条', foot: '<span class="muted">观察、核实</span>' })}
      ${kpi({ iconName: 'users', tone: 'blue', label: '扫描达人', value: num(mon.scanned), unit: '位', foot: '<span class="muted">近 14 天有投放</span>' })}
      ${kpi({ iconName: 'clock', tone: 'violet', label: '监测窗口', value: `${mon.window?.recent_days || 3}/${mon.window?.baseline_days || 7}`, unit: '天', foot: '<span class="muted">窗口 / 基线</span>' })}
    </div>

    <section class="card mt-16" id="section-alerts">
      <div class="card-h"><h2>异常告警</h2><span class="badge ${todos.length ? 'red' : 'green'}">${todos.length ? todos.length + ' 条命中' : '0 条'}</span>
        <div class="right muted tiny">基线取中位数，避免异常期稀释</div></div>
      <div class="card-b flush" id="alertTable"></div>
    </section>

    <section class="card mt-16">
        <div class="card-h"><h2>投放趋势</h2><div class="right muted tiny">近 30 天 · 曝光量</div></div>
        <div class="card-b">
          <div class="chart-stats">
            <div class="chart-stat"><div class="k">总曝光</div><div class="v">${compact(trend.totals.impressions)}</div></div>
            <div class="chart-stat"><div class="k">总点击</div><div class="v">${compact(trend.totals.clicks)}</div></div>
            <div class="chart-stat"><div class="k">花费</div><div class="v">${money(trend.totals.spend)}</div></div>
            <div class="chart-stat"><div class="k">ROI</div><div class="v">${trend.totals.roi}</div></div>
          </div>
          <div id="monChart"></div>
        </div>
    </section>

    <section class="card mt-16">
      <div class="card-h"><h2>按内容类型复盘</h2><div class="right muted tiny">ROI / CTR / CVR / CPM 均来自工具返回</div></div>
      <div class="card-b flush" id="reviewTable"></div>
    </section>`;

  renderAlerts(todos);
  renderReview(review);
  lineChart($('#monChart', root), {
    dates: trend.dates,
    series: [{ label: '曝光量', values: trend.series.impressions, color: '#2563eb' }],
    height: 240,
  });

  $('#monRefresh', root).addEventListener('click', () => renderMonitor(root));
  $('#monReport', root).addEventListener('click', () => { location.hash = '#/reports'; });

  function renderAlerts(list) {
    const el = $('#alertTable', root);
    if (!list.length) {
      el.innerHTML = emptyState('本期未命中告警阈值', 'shield', '<div class="tiny" style="margin-top:6px">无告警不等于无风险，可能是阈值过宽</div>');
      return;
    }
    el.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>级别</th><th>达人</th><th>规则</th><th>偏差</th><th>先查什么</th><th></th></tr></thead>
      <tbody>${list.map((a) => `<tr>
        <td><span class="lv ${a.level}" style="width:30px;height:22px;border-radius:6px;display:inline-grid;place-items:center;font-size:10px;font-weight:800;background:var(--${a.level === 'P0' ? 'red' : 'amber'}-soft);color:var(--${a.level === 'P0' ? 'red' : 'amber'})">${a.level}</span></td>
        <td><b>${esc(a.kol_id)}</b></td>
        <td>${esc(a.rule)}</td>
        <td class="num" style="color:${a.delta < 0 ? 'var(--red)' : 'var(--green)'};font-weight:600">${a.delta > 0 ? '+' : ''}${a.delta}%</td>
        <td class="muted">${esc(a.hint)}</td>
        <td class="actions"><button class="link-btn" data-funnel="${esc(a.kol_id)}">漏斗诊断</button></td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-funnel]', el).forEach((btn) => btn.addEventListener('click', () => showFunnel(btn.dataset.funnel)));
  }

  function renderReview(review) {
    const rows = review.rows || [];
    const el = $('#reviewTable', root);
    el.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>内容类型</th><th>花费</th><th>ROI</th><th>CTR</th><th>CVR</th><th>CPM</th></tr></thead>
      <tbody>${rows.map((r) => `<tr>
        <td class="nw"><b>${esc(r.group)}</b></td>
        <td class="num nw">${money(r.spend)}</td>
        <td class="num nw" style="font-weight:700;color:${r.roi >= 1.8 ? 'var(--green)' : r.roi >= 1.5 ? 'var(--ink)' : 'var(--red)'}">${r.roi}</td>
        <td class="num nw">${pct(r.ctr, 2)}</td>
        <td class="num nw">${pct(r.cvr, 2)}</td>
        <td class="num nw">${r.cpm}</td>
      </tr>`).join('')}</tbody></table></div>
      <div class="flex" style="padding:10px 18px;border-top:1px solid var(--line);gap:14px">
        <span class="badge green">最好 ${esc(review.best || '—')}</span>
        <span class="badge red">最差 ${esc(review.worst || '—')}</span>
        <span class="right muted tiny">整体 ROI ${review.overall?.roi ?? '—'}</span>
      </div>`;
  }

  async function showFunnel(kolId) {
    let res;
    try { res = await api.funnel(kolId); } catch (e) { openModal({ title: '漏斗诊断', body: `<div class="notice red">${esc(e.message)}</div>`, size: 'sm' }); return; }
    if (res.error) { openModal({ title: '漏斗诊断', body: `<div class="notice red">${esc(res.error)}</div>`, size: 'sm' }); return; }
    const dev = res.deviation_pct || {};
    const metrics = ['曝光', '点击率', '转化率', '客单价'];
    const fmt = (k, v) => k === '曝光' ? compact(v) : k === '客单价' ? money(v, 1) : pct(v * 100, 2);
    const body = `
      <div class="flex wrap" style="gap:8px;margin-bottom:12px">
        <span class="badge blue">${esc(res.kol_id)}</span>
        <span class="badge gray">${esc((res.period || []).join(' → '))}</span>
        <span class="badge ${res.main_driver === '无明显异常' ? 'green' : 'red'}">主因：${esc(res.main_driver)}</span>
      </div>
      ${res.early ? `<table class="table">
        <thead><tr><th>环节</th><th>前半程</th><th>后半程</th><th>偏差</th></tr></thead>
        <tbody>${metrics.map((k) => `<tr>
          <td>${k}</td><td class="num">${fmt(k, res.early[k])}</td><td class="num">${fmt(k, res.late[k])}</td>
          <td class="num" style="color:${dev[k] < -15 ? 'var(--red)' : dev[k] > 15 ? 'var(--green)' : 'var(--muted)'}">${dev[k] > 0 ? '+' : ''}${dev[k]}%</td>
        </tr>`).join('')}</tbody></table>` : ''}
      <div class="notice ${res.main_driver === '无明显异常' ? '' : 'amber'} mt-12">${icon('target', 15)}<div><b>建议动作：</b>${esc(res.suggested_action || '—')}</div></div>`;
    openModal({ title: '漏斗诊断', body, size: 'sm' });
  }
}
