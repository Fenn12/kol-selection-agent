// 系统设置
import { api } from '../api.js';
import { store, setBudget, setPlanner } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, toast, kpi } from '../ui.js';
import { num } from '../format.js';

export async function renderSettings(root) {
  const [status, ds] = await Promise.all([api.llmStatus(), api.datasource()]);
  store.llm = status;
  store.ds = ds;
  const usage = status.usage || {};

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>系统设置</h1>
        <p>规划器、预算、AI 连接与数据源。所有配置只影响本机运行口径。</p>
      </div>
    </div>

    <div class="grid grid-2">
      <section class="card">
        <div class="card-h"><h2>AI 连接</h2>
          <span class="badge ${status.available ? 'green' : 'amber'} dot">${status.available ? '已配置' : '未配置 Key'}</span>
          <div class="right"><button class="btn btn-sm" id="testBtn">${icon('zap', 13)} 测试连接</button></div>
        </div>
        <div class="card-b">
          <div class="grid grid-2" style="gap:10px">
            ${[['模型', status.model || '—'], ['Base URL', status.base_url || '—'], ['环境文件', status.env_file ? '已读取 .env' : '未找到 .env'], ['已加载变量', num(status.env_loaded)]]
              .map(([k, v]) => `<div class="panel" style="padding:10px"><div class="muted tiny">${k}</div>
                <div style="font-weight:600;margin-top:3px;word-break:break-all;font-size:12px">${esc(String(v))}</div></div>`).join('')}
          </div>
          <div class="notice ${status.available ? '' : 'amber'} mt-12">
            ${icon(status.available ? 'check-circle' : 'alert', 15)}
            <div>${status.available
              ? '模型可用，Agent 会走 LLM 规划器：自己写计划、选工具、答前自检。'
              : '未配置 DEEPSEEK_API_KEY，Agent 自动降级为规则规划器——功能都能跑，但决策是固定序列，不是真 Agent。'}</div>
          </div>
          <div class="hr"></div>
          <div class="field-label">累计用量</div>
          <div class="flex wrap" style="gap:8px">
            <span class="badge">调用 ${num(usage.calls || 0)} 次</span>
            <span class="badge">输入 ${num(usage.prompt_tokens || 0)} tokens</span>
            <span class="badge">输出 ${num(usage.completion_tokens || 0)} tokens</span>
            <span class="badge">平均 ${usage.avg_latency_ms ? Math.round(usage.avg_latency_ms) + 'ms' : '—'}</span>
          </div>
          <div class="muted tiny mt-8">用量记录在 logs/llm_usage.jsonl，可审计。</div>
        </div>
      </section>

      <section class="card">
        <div class="card-h"><h2>运行参数</h2></div>
        <div class="card-b">
          <div class="field">
            <div class="field-label">默认规划器</div>
            <div class="segmented" id="plannerSeg">
              ${['auto', 'rule', 'llm'].map((p) => `<button data-planner="${p}" class="${store.planner === p ? 'on' : ''}">${p === 'auto' ? '自动（有 Key 用模型）' : p === 'rule' ? '离线规则' : 'LLM 规划'}</button>`).join('')}
            </div>
            <div class="field-hint">auto = 有 Key 走模型，无 Key 走规则；实际使用了哪个会在运行结果里标注。</div>
          </div>
          <div class="field">
            <div class="field-label">默认预算（元）</div>
            <div class="flex" style="gap:8px">
              <input class="input" id="budgetInput" type="number" value="${store.budget}" style="max-width:180px">
              <button class="btn btn-sm" id="saveBudget">保存</button>
            </div>
            <div class="field-hint">预算不足时 Agent 会明确报告缺口，不硬凑名单。</div>
          </div>
          <div class="hr"></div>
          <div class="flex wrap" style="gap:8px">
            <span class="badge">规划步数 ≤ 16</span><span class="badge">执行步数 ≤ 40</span>
            <span class="badge">token ≤ 150,000</span><span class="badge">观察值截断 6,000 字符</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-h"><h2>数据源</h2>
          <span class="badge blue">${esc(String(ds.source || 'csv').toUpperCase())}</span>
        </div>
        <div class="card-b">
          <div class="panel" style="padding:10px">
            <div class="muted tiny">当前路径</div>
            <div style="font-family:var(--mono);font-size:11px;margin-top:3px;word-break:break-all">${esc(ds.path || '—')}</div>
          </div>
          <div class="muted tiny mt-12" style="line-height:1.8">
            支持三态切换：<code>KOL_DATASOURCE=csv|sql|http</code>。<br>
            SQL 模式通过 <code>sql/mapping.json</code> 做字段映射，业务代码不改。<br>
            当前数据为合成样例，商用前请接入企业库。
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-h"><h2>产品说明</h2></div>
        <div class="card-b">
          <div class="flex" style="gap:8px;margin-bottom:10px">
            <span class="brand-mark" style="width:26px;height:26px">${icon('activity', 14)}</span>
            <div><div style="font-weight:600">KOL Operations Agent</div><div class="muted tiny">达人运营智能体 · v1.5</div></div>
          </div>
          <div class="muted tiny" style="line-height:1.8">
            五条硬原则：先查数据再下结论 / 数字只能来自工具返回 / 不可行就直说 /
            内容双检 / 人工终审不可跳过。<br><br>
            已知局限：未配置 Key 时是规则基线；第三方指标为 mock；企微读取依赖管理员开通；
            评分为批内相对排序；客单价为区间派生。
          </div>
        </div>
      </section>
    </div>`;

  $('#testBtn', root).addEventListener('click', async () => {
    const btn = $('#testBtn', root);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin dark"></span>测试中';
    try {
      const res = await api.llmTest();
      toast(`连接成功：${res.model} · ${res.latency_ms}ms`, 'ok');
      renderSettings(root);
    } catch (e) {
      toast('连接失败：' + e.message, 'err');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${icon('zap', 13)} 测试连接`;
    }
  });

  $$('#plannerSeg button', root).forEach((b) => b.addEventListener('click', () => {
    setPlanner(b.dataset.planner);
    $$('#plannerSeg button', root).forEach((x) => x.classList.toggle('on', x === b));
    toast('默认规划器已设为 ' + b.dataset.planner);
  }));

  $('#saveBudget', root).addEventListener('click', () => {
    setBudget($('#budgetInput', root).value);
    toast('默认预算已保存为 ¥' + num(store.budget));
  });
}
