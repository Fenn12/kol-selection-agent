// 内容复写与合规检查
import { api } from '../api.js';
import { icon } from '../icons.js';
import {
  $, $$, esc, openModal, copyText, toast, stepper, platformTag, emptyState,
} from '../ui.js';
import { num } from '../format.js';

const CAT_MAP = [
  { key: '绝对化', label: '极限词', icon: 'alert' },
  { key: '医疗功效', label: '功效宣称', icon: 'shield' },
  { key: '替代医疗', label: '替代医疗', icon: 'shield' },
  { key: '硬引导', label: '硬引导', icon: 'message' },
  { key: '疗效时间承诺', label: '疗效时间承诺', icon: 'clock' },
];

const RULES = [
  { title: '极限词检查', desc: '禁止使用"最好、最有效、第一、唯一、顶级"等极限词。' },
  { title: '功效词检查', desc: '禁止出现"治愈、治疗、减肥、降血压"等医疗功效暗示。' },
  { title: '敏感词检查', desc: '自动识别政治、色情、暴力等敏感词汇。' },
  { title: '品牌合规检查', desc: '检查是否涉及未授权的品牌、竞品及知名 IP。' },
];

export async function renderContent(root, { focus = '', params } = {}) {
  const data = await api.samples();
  const platforms = data.platforms;
  const want = params?.get('sample');
  const initial = data.samples.find((s) => s.id === want) || data.samples[0];
  const state = {
    samples: data.samples,
    sample: initial,
    results: [],
    active: platforms.includes(initial.platform) ? initial.platform : platforms[0],
    targets: new Set(platforms),
    product: '指压板新品：高弹力、环保材质、可折叠收纳',
    taskName: '指压板新品 · 多平台内容改写',
    running: false,
  };

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>内容复写与合规检查</h1>
        <p>一键改写多平台内容，自动检测违规项，确保内容合规可发。</p>
      </div>
      <div class="actions">
        <button class="btn" id="libraryBtn">${icon('book', 14)} 内容库</button>
        <button class="btn btn-primary" id="newTaskBtn">${icon('plus', 14)} 新建复写任务</button>
      </div>
    </div>

    <div class="card"><div class="card-b" style="padding:14px 18px">
      ${stepper(['选择达人与内容', 'AI 内容复写', '合规检查', '结果确认'], 0, -1)}
    </div></div>

    <div class="grid mt-16" style="grid-template-columns:minmax(280px,.9fr) minmax(0,1.35fr) minmax(260px,.85fr);align-items:start">
      <section class="card">
        <div class="card-h"><h2>任务信息</h2></div>
        <div class="card-b">
          <div class="field">
            <div class="field-label">任务名称</div>
            <input class="input" id="taskName" value="${esc(state.taskName)}">
          </div>
          <div class="field">
            <div class="field-label">选择内容样本</div>
            <select class="select" id="sampleSel">
              ${state.samples.map((s) => `<option value="${esc(s.id)}" ${s.id === initial.id ? 'selected' : ''}>${esc(s.platform)} · ${esc(s.title)}</option>`).join('')}
            </select>
            <div class="field-hint" id="sampleHint"></div>
          </div>
          <div class="field">
            <div class="field-label">产品 / 卖点 <span class="req">*</span></div>
            <textarea class="textarea" id="productInput" maxlength="200" style="min-height:74px">${esc(state.product)}</textarea>
            <div class="field-hint right" id="productCount">0/200</div>
          </div>
          <div class="field">
            <div class="field-label">目标平台</div>
            <div class="flex wrap" style="gap:12px">
              ${platforms.map((p) => `<label class="checkbox"><input type="checkbox" data-platform="${esc(p)}" checked>${esc(p)}</label>`).join('')}
            </div>
          </div>
          <div class="notice mb-12">${icon('alert', 14)}<div>改写前后各跑一次合规检查，违规项会在结论中显式对比。</div></div>
          <button class="btn btn-primary" id="startBtn" style="width:100%;height:38px">${icon('sparkles', 15)} 开始改写</button>
        </div>
      </section>

      <section class="card">
        <div class="card-h">
          <h2>改写结果预览</h2>
          <div class="right"><button class="link-btn" id="copyAllBtn" disabled>${icon('copy', 12)} 一键复制</button></div>
        </div>
        <div class="card-b">
          <div id="offlineNotice"></div>
          <div class="platform-tabs mb-12" id="platformTabs">
            ${platforms.map((p) => `<button class="platform-tab ${p === state.active ? 'on' : ''}" data-platform="${esc(p)}">${platformTag(p)}</button>`).join('')}
          </div>
          <div id="resultPane"></div>
        </div>
      </section>

      <section class="card" id="section-compliance">
        <div class="card-h"><h2>合规检查结果</h2><div class="right muted tiny" id="compMeta"></div></div>
        <div class="card-b" id="compliancePane"></div>
      </section>
    </div>

    <div class="grid mt-16" style="grid-template-columns:minmax(0,1.6fr) minmax(280px,.8fr);align-items:start">
      <section class="card">
        <div class="card-h"><h2>多平台内容对比</h2><div class="right muted tiny">改写结果会同时出现在这里</div></div>
        <div class="card-b"><div class="grid grid-3" id="compareGrid"></div></div>
      </section>
      <section class="card">
        <div class="card-h"><h2>内容合规规则与建议</h2></div>
        <div class="card-b">
          <div class="tabs mb-12" id="ruleTabs">
            <button class="tab on" data-rule="rules">规则说明</button>
            <button class="tab" data-rule="history">历史记录</button>
          </div>
          <div id="rulePane"></div>
        </div>
      </section>
    </div>

    <section class="card mt-16" id="section-library">
      <div class="card-h"><h2>内容库</h2><div class="right muted tiny">${state.samples.length} 条样本 · 全部来自合成数据</div></div>
      <div class="card-b flush" id="libraryTable"></div>
    </section>`;

  /* ---------- 初始渲染 ---------- */

  updateSampleMeta();
  $('#productCount', root).textContent = `${state.product.length}/200`;
  renderResult();
  renderCompliance();
  renderCompare();
  renderRules();
  renderLibrary();

  /* ---------- 交互 ---------- */

  $('#sampleSel', root).addEventListener('change', (e) => {
    state.sample = state.samples.find((s) => s.id === e.target.value);
    state.results = [];
    updateSampleMeta();
    renderResult();
    renderCompliance();
    renderCompare();
    toast('已切换内容样本，重新改写后生效');
  });

  $('#productInput', root).addEventListener('input', (e) => {
    state.product = e.target.value;
    $('#productCount', root).textContent = `${e.target.value.length}/200`;
  });
  $('#taskName', root).addEventListener('input', (e) => { state.taskName = e.target.value; });

  $$('[data-platform]', root).forEach((el) => {
    if (el.tagName === 'INPUT') {
      el.addEventListener('change', () => {
        el.checked ? state.targets.add(el.dataset.platform) : state.targets.delete(el.dataset.platform);
        if (!state.targets.size) { el.checked = true; state.targets.add(el.dataset.platform); toast('至少选择一个平台', 'err'); }
        if (!state.targets.has(state.active)) state.active = [...state.targets][0];
        renderResult(); renderCompare();
      });
    } else if (el.classList.contains('platform-tab')) {
      el.addEventListener('click', () => setActive(el.dataset.platform));
    }
  });

  $('#platformTabs', root).addEventListener('click', (e) => {
    const tab = e.target.closest('[data-platform]');
    if (tab) setActive(tab.dataset.platform);
  });

  $('#startBtn', root).addEventListener('click', runRewrite);
  $('#copyAllBtn', root).addEventListener('click', () => {
    const body = state.results.map((r) => `【${r.platform}】\n${r.body}`).join('\n\n');
    if (body) copyText(body);
  });
  $('#newTaskBtn', root).addEventListener('click', () => {
    state.results = [];
    renderResult(); renderCompliance(); renderCompare();
    $('#taskName', root).focus();
    toast('已重置任务，可重新选择内容并改写');
  });
  $('#libraryBtn', root).addEventListener('click', () => {
    $('#section-library', root).scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  $$('#ruleTabs .tab', root).forEach((tab) => tab.addEventListener('click', () => {
    $$('#ruleTabs .tab', root).forEach((t) => t.classList.toggle('on', t === tab));
    renderRules(tab.dataset.rule);
  }));

  /* ---------- 渲染函数 ---------- */

  function updateSampleMeta() {
    const s = state.sample;
    $('#sampleHint', root).textContent = `${s.platform} · ${s.length} 字 · ${s.problem || '无标注问题'}`;
  }

  function setActive(p) {
    state.active = p;
    $$('#platformTabs .platform-tab', root).forEach((t) => t.classList.toggle('on', t.dataset.platform === p));
    renderResult();
  }

  function currentResult() {
    return state.results.find((r) => r.platform === state.active);
  }

  function complianceBadge(c) {
    if (!c) return '<span class="badge gray">未检查</span>';
    return c.pass
      ? `<span class="badge green dot">合规通过</span>`
      : `<span class="badge red dot">${c.hit_count} 处违规</span>`;
  }

  function renderResult() {
    const pane = $('#resultPane', root);
    if (!pane) return;
    const notice = $('#offlineNotice', root);
    if (notice) {
      const offline = state.results.some((r) => r.mode === 'offline_rule');
      notice.innerHTML = offline
        ? `<div class="notice amber mb-12">${icon('alert', 14)}<div>当前是<strong>离线规则模式</strong>：只做合规清洗，不做文笔重写。配置 DEEPSEEK_API_KEY 后可获得完整改写。</div></div>`
        : '';
    }
    const s = state.sample;
    const r = currentResult();

    if (!r) {
      pane.innerHTML = `
        <div class="doc-card mb-12">
          <div class="head"><span class="badge gray">原文</span><span class="muted tiny">${esc(s.platform)}</span>
            <span class="right">${complianceBadge(s.compliance)}</span></div>
          <div class="body">${esc(s.body)}</div>
          <div class="foot"><span>${s.length} 字</span><span>·</span><span>${esc(s.problem || '')}</span></div>
        </div>
        <div class="notice">${icon('sparkles', 15)}<div>点击左侧「开始改写」，AI 会按各平台调性重写并做合规清洗。</div></div>`;
      $('#copyAllBtn', root).disabled = true;
      return;
    }

    pane.innerHTML = `
      <div class="doc-card mb-12">
        <div class="head"><span class="badge gray">原文</span><span class="muted tiny">${esc(s.platform)}</span>
          <span class="right">${complianceBadge(r.before_compliance)}</span></div>
        <div class="body clamp">${esc(s.body)}</div>
        <div class="foot"><span>${s.length} 字</span><span>·</span><span>${esc(s.problem || '')}</span></div>
      </div>
      <div class="doc-card">
        <div class="head"><span class="badge blue">${icon('sparkles', 12)} AI 改写后</span>
          <span class="muted tiny">${esc(r.platform)}风格 · ${r.mode === 'llm' ? '模型生成' : '离线规则'}${r.repaired ? ' · 已做合规修复' : ''}</span>
          <span class="right">${complianceBadge(r.after_compliance)}</span></div>
        <div class="body">${esc(r.body)}</div>
        <div class="foot">
          <span>${r.length} 字</span><span>·</span><span>目标 ${r.target_length?.[0]}–${r.target_length?.[1]} 字</span>
          <button class="link-btn right" data-copy-result="${esc(r.platform)}">${icon('copy', 12)} 复制</button>
        </div>
        ${(r.changes || []).length ? `<div style="padding:10px 13px;border-top:1px solid var(--line);background:var(--surface-2)">
          <div class="muted tiny" style="margin-bottom:4px">改动说明</div>
          ${r.changes.map((c) => `<div class="tiny" style="color:var(--ink-2);line-height:1.6">· ${esc(c)}</div>`).join('')}
          ${(r.rag_hits || []).length ? `<div class="flex wrap" style="gap:5px;margin-top:8px">
            <span class="muted tiny">知识库依据：</span>
            ${r.rag_hits.map((h) => `<span class="badge gray" title="${esc(h.title)}">${esc(h.doc)}</span>`).join('')}
          </div>` : ''}
        </div>` : ''}
      </div>`;

    const btn = $('[data-copy-result]', pane);
    if (btn) btn.addEventListener('click', () => copyText(r.body));
    $('#copyAllBtn', root).disabled = false;
  }

  function renderCompliance() {
    const pane = $('#compliancePane', root);
    if (!pane) return;
    const s = state.sample;
    const results = state.results;
    const active = currentResult();

    const before = active ? active.before_compliance : s.compliance;
    const after = active ? active.after_compliance : null;
    const allPass = results.length ? results.every((r) => r.after_compliance?.pass) : false;

    const countCat = (c, cat) => (c?.hits || []).filter((h) => h.category === cat).length;
    const rows = CAT_MAP.map((m) => ({
      ...m,
      before: countCat(before, m.key),
      after: after ? countCat(after, m.key) : null,
    }));

    $('#compMeta', root).textContent = results.length ? `${results.length} 个平台` : '改写前';

    pane.innerHTML = `
      <div class="flex" style="gap:10px;margin-bottom:12px">
        <span class="kpi-ico ${after ? (allPass ? 'green' : 'red') : 'amber'}" style="width:38px;height:38px">
          ${icon(after ? (allPass ? 'check' : 'alert') : 'shield', 19)}
        </span>
        <div>
          <div style="font-weight:700;font-size:14px">${after ? (allPass ? '合规通过' : '仍有违规') : '改写前检查'}</div>
          <div class="muted tiny">${after ? (allPass ? '未发现违规内容' : '需要人工处理后再发布') : `原文命中 ${before.hit_count} 处，改写后应清零`}</div>
        </div>
      </div>
      <div class="field-label">违规项对比</div>
      <table class="table" style="font-size:11.5px">
        <thead><tr><th>检查项</th><th>改写前</th><th>改写后</th></tr></thead>
        <tbody>${rows.map((r) => `<tr>
          <td>${r.label}</td>
          <td class="num ${r.before ? 'down' : ''}" style="color:${r.before ? 'var(--red)' : 'var(--muted)'}">${r.before} 项</td>
          <td class="num" style="color:${r.after === null ? 'var(--muted-2)' : r.after ? 'var(--red)' : 'var(--green)'}">${r.after === null ? '—' : r.after + ' 项'}</td>
        </tr>`).join('')}</tbody>
      </table>
      ${after
        ? `<div class="notice ${allPass ? '' : 'amber'} mt-12">${icon(allPass ? 'check-circle' : 'alert', 15)}
            <div>${allPass ? '当前内容符合平台规范，建议按计划发布。所有内容仍需人工终审。' : '复写后仍命中：' + esc([...new Set((after.hits || []).map((h) => h.word))].join('、'))}</div></div>`
        : `<div class="notice mt-12">${icon('shield', 15)}<div>改写后会自动再查一次，两次结果都会写进结论。</div></div>`}
    `;
  }

  function renderCompare() {
    const el = $('#compareGrid', root);
    if (!el) return;
    const s = state.sample;
    const targets = platforms.filter((p) => state.targets.has(p));
    el.innerHTML = targets.map((p) => {
      const r = state.results.find((x) => x.platform === p);
      if (!r) {
        return `<div class="doc-card">
          <div class="head"><span class="pf ${p}">${esc(p.slice(0, 2))}</span><span class="t">${esc(p)}</span>
            <span class="right badge gray">待改写</span></div>
          <div class="body clamp" style="color:var(--muted-2)">${p === s.platform ? esc(s.body) : '点击「开始改写」后生成' + esc(p) + '版本'}</div>
          <div class="foot"><span>${p === s.platform ? s.length + ' 字' : '待生成'}</span><span>·</span><span>${p === s.platform ? esc(s.platform) + ' 原文' : '改写后自动填充'}</span></div>
        </div>`;
      }
      return `<div class="doc-card">
        <div class="head"><span class="pf ${p}">${esc(p.slice(0, 2))}</span><span class="t">${esc(p)}</span>
          <span class="right">${complianceBadge(r.after_compliance)}</span></div>
        <div class="body clamp">${esc(r.body)}</div>
        <div class="foot"><span>${r.length} 字</span><span>·</span><span>违规 ${r.after_compliance?.hit_count ?? 0} 项</span>
          <button class="link-btn right" data-copy-compare="${esc(p)}">${icon('copy', 12)} 复制文案</button></div>
      </div>`;
    }).join('');

    $$('[data-copy-compare]', el).forEach((btn) => btn.addEventListener('click', () => {
      const r = state.results.find((x) => x.platform === btn.dataset.copyCompare);
      if (r) copyText(r.body);
    }));
  }

  function renderRules(mode = 'rules') {
    const pane = $('#rulePane', root);
    if (!pane) return;
    $$('#ruleTabs .tab', root).forEach((t) => t.classList.toggle('on', t.dataset.rule === mode));
    if (mode === 'history') {
      pane.innerHTML = state.results.length
        ? `<div class="list">${state.results.map((r) => `<div class="list-item">
            <span class="ico" style="background:var(--primary-soft);color:var(--primary)">${icon('edit', 14)}</span>
            <div class="grow"><div class="t1">${esc(state.sample.title)}</div>
              <div class="t2">${esc(r.platform)} · ${r.length} 字 · ${r.after_compliance?.hit_count || 0} 处违规</div></div>
            <div class="meta">${r.mode === 'llm' ? 'AI' : '规则'}</div>
          </div>`).join('')}</div>`
        : emptyState('本次还没有改写记录', 'clock');
      return;
    }
    pane.innerHTML = `
      <div>${RULES.map((r) => `<div class="rule-item">
        <span class="ri">${icon('check', 14)}</span>
        <div><div class="t1">${esc(r.title)}</div><div class="t2">${esc(r.desc)}</div></div>
      </div>`).join('')}</div>
      <div class="notice amber mt-12">${icon('alert', 14)}<div><b>人工终审提示：</b>所有内容均需人工复核后方可发布。</div></div>`;
  }

  function renderLibrary() {
    const el = $('#libraryTable', root);
    el.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>内容</th><th>平台</th><th>字数</th><th>合规状态</th><th>标注问题</th><th></th></tr></thead>
      <tbody>${state.samples.map((s) => `<tr>
        <td><div class="name"><div><div class="t1">${esc(s.title)}</div><div class="t2">${esc(s.id)}</div></div></div></td>
        <td>${platformTag(s.platform)}</td>
        <td class="num">${s.length}</td>
        <td>${s.compliance?.pass ? '<span class="badge green dot">合规</span>' : `<span class="badge red dot">${s.compliance.hit_count} 处</span>`}</td>
        <td class="muted">${esc(s.problem || '—')}</td>
        <td class="actions"><button class="link-btn" data-use="${esc(s.id)}">使用</button></td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-use]', el).forEach((btn) => btn.addEventListener('click', () => {
      $('#sampleSel', root).value = btn.dataset.use;
      $('#sampleSel', root).dispatchEvent(new Event('change'));
      $('#section-library', root).scrollIntoView({ behavior: 'smooth', block: 'start' });
    }));
  }

  async function runRewrite() {
    if (state.running) return;
    const targets = platforms.filter((p) => state.targets.has(p));
    if (!targets.length) { toast('至少选择一个平台', 'err'); return; }
    if (!state.product.trim()) { toast('先填写产品 / 卖点', 'err'); return; }

    state.running = true;
    const btn = $('#startBtn', root);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>改写中…';
    try {
      const res = await api.rewrite({
        sample_id: state.sample.id,
        platforms: targets,
        product: state.product,
      });
      state.results = res.results || [];
      state.active = state.results[0]?.platform || state.active;
      $$('#platformTabs .platform-tab', root).forEach((t) => t.classList.toggle('on', t.dataset.platform === state.active));
      renderResult();
      renderCompliance();
      renderCompare();
      renderRules('history');
      const allPass = state.results.every((r) => r.after_compliance?.pass);
      toast(allPass ? '改写完成，全部平台合规通过' : '改写完成，仍有违规项需处理', allPass ? 'ok' : 'err');
    } catch (e) {
      toast('改写失败：' + e.message, 'err');
    } finally {
      state.running = false;
      btn.disabled = false;
      btn.innerHTML = `${icon('sparkles', 15)} 重新改写`;
    }
  }
}

