// Agent 运行与结果弹窗（工作台 / 达人页共用）
import { api } from './api.js';
import { store } from './state.js';
import { icon } from './icons.js';
import { $, $$, esc, openModal, copyText, markdownToHtml, toast } from './ui.js';
import { duration, num, truncate } from './format.js';

export async function runAgent(goal) {
  return api.run(goal, store.budget, store.planner);
}

function planList(plan) {
  if (!plan) return '<div class="empty">该规划器没有输出计划</div>';
  const items = Array.isArray(plan) ? plan : String(plan).split('\n').filter(Boolean);
  return `<ol class="markdown" style="padding-left:18px;margin:4px 0">${items
    .map((p) => `<li style="margin:6px 0">${esc(typeof p === 'string' ? p : JSON.stringify(p))}</li>`).join('')}</ol>`;
}

function traceHtml(trace = []) {
  if (!trace.length) return '<div class="empty">没有工具调用记录</div>';
  return `<div class="trace">${trace.map((t, i) => {
    const obs = t.observation;
    let obsText = '';
    if (obs && typeof obs === 'object') {
      const keys = Object.keys(obs).slice(0, 4);
      obsText = keys.map((k) => `${k}=${JSON.stringify(obs[k]).slice(0, 60)}`).join(' · ');
    } else obsText = truncate(String(obs || ''), 160);
    return `<div class="trace-row">
      <span class="trace-no">${t.step || i + 1}</span>
      <div class="grow">
        <div class="t1">${esc(t.thought || '（无思考文本）')}</div>
        <div class="t2 flex wrap" style="gap:6px">
          <span class="trace-tool">${icon('terminal', 11)} ${esc(t.tool || '—')}</span>
          <span class="muted tiny">${esc(truncate(JSON.stringify(t.args || {}), 90))}</span>
          <span class="muted tiny">· ${duration(t.elapsed_ms)}</span>
        </div>
        <div class="t2" style="font-family:var(--mono);font-size:10.5px">${esc(obsText)}</div>
      </div>
    </div>`;
  }).join('')}</div>`;
}

export function openRunModal(rec) {
  const meta = rec.agent_meta || {};
  const planner = rec.planner || meta.planner || 'rule';
  const tokens = meta.tokens || 0;
  const warnings = rec.warnings || [];
  const body = `
    <div class="flex wrap" style="gap:6px;margin-bottom:12px">
      <span class="badge ${planner === 'llm' ? 'blue' : 'gray'}">${planner === 'llm' ? 'LLM 规划器' : '规则规划器'}</span>
      <span class="badge">${num(rec.steps)} 步</span>
      <span class="badge">${duration(rec.elapsed_ms)}</span>
      ${tokens ? `<span class="badge">${num(tokens)} tokens</span>` : ''}
      ${meta.model ? `<span class="badge gray">${esc(meta.model)}</span>` : ''}
    </div>
    ${warnings.length ? `<div class="notice amber mb-12">${icon('alert', 15)}<div>${warnings.map(esc).join('<br>')}</div></div>` : ''}
    <div class="tabs" id="runTabs">
      <button class="tab on" data-tab="plan">执行计划</button>
      <button class="tab" data-tab="trace">执行轨迹</button>
      <button class="tab" data-tab="final">最终结论</button>
    </div>
    <div style="padding-top:12px">
      <div data-pane="plan">${planList(meta.plan)}</div>
      <div data-pane="trace" class="hidden">${traceHtml(rec.trace)}</div>
      <div data-pane="final" class="hidden"><div class="markdown" id="finalMd">${markdownToHtml(rec.final || '（没有输出结论）')}</div></div>
    </div>`;

  const footer = `<span class="muted tiny" id="modalGoal">${esc(truncate(rec.goal || '', 40))}</span>
    <span class="spacer"></span>
    <button class="btn btn-sm" id="copyFinal">${icon('copy', 14)} 复制结论</button>
    <button class="btn btn-sm btn-primary" id="closeRun">关闭</button>`;

  const m = openModal({ title: 'Agent 运行结果', body, footer, size: '', onMount(el, close) {
    $$('#runTabs .tab', el).forEach((tab) => {
      tab.addEventListener('click', () => {
        $$('#runTabs .tab', el).forEach((t) => t.classList.toggle('on', t === tab));
        $$('[data-pane]', el).forEach((p) => p.classList.toggle('hidden', p.dataset.pane !== tab.dataset.tab));
      });
    });
    $('#copyFinal', el).addEventListener('click', () => copyText(rec.final || ''));
    $('#closeRun', el).addEventListener('click', close);
  } });
  return m;
}

export async function runWithModal(goal, onDone) {
  toast('Agent 开始执行…');
  try {
    const rec = await runAgent(goal);
    openRunModal(rec);
    if (onDone) onDone(rec);
    return rec;
  } catch (e) {
    toast('运行失败：' + e.message, 'err');
    throw e;
  }
}
