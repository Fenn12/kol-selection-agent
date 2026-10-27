'use strict';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pct = (v, d = 1) => (v == null ? '—' : `${Number(v).toFixed(d)}%`);
const money = (v) => (v == null ? '—' : Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 }));

let OVERVIEW = null;

/* ---------------- 驾驶舱 ---------------- */

async function loadOverview() {
  const budget = Number($('#budget').value) || 8000;
  try {
    const r = await fetch(`/api/overview?budget=${budget}`);
    OVERVIEW = await r.json();
    renderChips();
    renderKpis();
    renderTodos();
    renderChannel();
    renderReview();
  } catch (e) {
    $('#todos').innerHTML = `<div class="empty">驾驶舱加载失败：${esc(e.message)}</div>`;
  }
}

function renderChips() {
  const o = OVERVIEW || {};
  const llmOn = !!o.llm;
  $('#chips').innerHTML = [
    `<span class="chip ${llmOn ? 'on' : ''}">${llmOn ? 'AI 模式 · ' + esc(o.model || 'llm') : '离线规则模式（未配置 key）'}</span>`,
    `<span class="chip">扫描 ${o.monitor?.scanned ?? '—'} 位达人</span>`,
    `<span class="chip">窗口 ${o.monitor?.window?.recent_days ?? 3} 天 / 基线 ${o.monitor?.window?.baseline_days ?? 7} 天</span>`,
    `<span class="chip">数据源 ${esc(o.datasource?.source ?? 'csv')}</span>`,
    `<span class="chip warn">数据为合成样例</span>`,
  ].join('');
  if (llmOn) $('#llmState').textContent = '（已检测到 key）';
}

function renderKpis() {
  const o = OVERVIEW || {};
  const alerts = o.monitor?.alert_count ?? 0;
  const p0 = o.monitor?.p0 ?? 0, p1 = o.monitor?.p1 ?? 0;
  const roi = o.review?.overall?.roi;
  const best = o.review?.best ?? '—';
  const aov = o.product?.aov;
  const conf = o.product?.aov_conf ?? '中';

  $('#kpis').innerHTML = `
    <div class="kpi ${alerts ? 'alert' : ''}">
      <div class="k">待处理告警</div>
      <div class="v">${alerts}<small>条</small></div>
      <div class="d">P0 ${p0} · P1 ${p1}</div>
    </div>
    <div class="kpi">
      <div class="k">整体 ROI</div>
      <div class="v">${roi ?? '—'}</div>
      <div class="d">花费 ${money(o.review?.overall?.spend)} / 成交 ${money(o.review?.overall?.gmv)}</div>
    </div>
    <div class="kpi">
      <div class="k">最优内容类型</div>
      <div class="v" style="font-size:20px">${esc(best)}</div>
      <div class="d">按 ROI 排序第一</div>
    </div>
    <div class="kpi">
      <div class="k">估算客单价</div>
      <div class="v">${aov ?? '—'}<small>元</small></div>
      <div class="d">置信度 ${esc(conf)}${conf === '低' ? ' · 不用于硬筛选' : ''}</div>
    </div>`;
}

function renderTodos() {
  const todos = (OVERVIEW && OVERVIEW.todos) || [];
  if (!todos.length) {
    $('#todos').innerHTML = '<div class="empty">本期无告警。注意：无告警不等于无风险，可能是阈值过宽。</div>';
    $('#todoMeta').textContent = '0 条';
    return;
  }
  $('#todoMeta').textContent = `${todos.length} 条 · 按严重度排序`;
  $('#todos').innerHTML = todos.map((t) => `
    <div class="todo">
      <span class="dot ${t.level === 'P0' ? 'p0' : 'p1'}"></span>
      <div class="txt">
        <div class="t1"><b>${esc(t.kol_id)}</b> · ${esc(t.rule)}
          <span style="color:${t.delta < 0 ? 'var(--p0)' : 'var(--amber)'}">${t.delta > 0 ? '+' : ''}${t.delta}%</span></div>
        <div class="t2">${esc(t.hint)}</div>
      </div>
      <span class="tier ${t.level === 'P0' ? 'C' : 'B'}">${esc(t.level)}</span>
    </div>`).join('');
}

function renderChannel() {
  const ch = (OVERVIEW && OVERVIEW.product && OVERVIEW.product.channel) || {};
  const keys = Object.keys(ch);
  if (!keys.length) { $('#channel').innerHTML = '<div class="empty">无数据</div>'; return; }
  $('#channel').innerHTML = keys.map((k) => {
    const v = ch[k] || {};
    const p = Math.round((v.占比 || 0) * 100);
    return `<div style="margin-bottom:11px">
      <div style="display:flex;justify-content:space-between;font-size:12.5px;margin-bottom:4px">
        <span>${esc(k)}</span><span class="num" style="color:var(--muted)">${p}% · ${money(v.销量)} 件</span>
      </div>
      <div style="height:6px;background:#efeae1;border-radius:3px;overflow:hidden">
        <div style="width:${p}%;height:100%;background:var(--navy)"></div>
      </div></div>`;
  }).join('');
}

function renderReview() {
  const rows = (OVERVIEW && OVERVIEW.review && OVERVIEW.review.rows) || [];
  if (!rows.length) { $('#review').innerHTML = '<div class="empty">无数据</div>'; return; }
  $('#review').innerHTML = `<table>
    <thead><tr><th>类型</th><th>ROI</th><th>CTR</th><th>CVR</th><th>CPM</th></tr></thead>
    <tbody>${rows.map((r) => `<tr>
      <td>${esc(r.group)}</td>
      <td class="num" style="font-weight:600;color:${r.roi >= 1.8 ? 'var(--olive)' : r.roi >= 1.5 ? 'var(--ink)' : 'var(--p0)'}">${r.roi}</td>
      <td class="num">${pct(r.ctr, 2)}</td>
      <td class="num">${pct(r.cvr, 2)}</td>
      <td class="num">${r.cpm}</td>
    </tr>`).join('')}</tbody></table>`;
}

/* ---------------- 运行 ---------------- */

async function runAgent(goal) {
  const btn = $('#runBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="loading"></span>运行中';
  $('#result').innerHTML = '<div class="empty"><span class="loading"></span>Agent 正在执行…</div>';
  $('#resultMeta').textContent = '执行中';
  $('#goalLine').textContent = goal;

  const payload = {
    goal,
    budget: Number($('#budget').value) || 8000,
    planner: document.querySelector('input[name="planner"]:checked').value,
  };

  try {
    const r = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const rec = await r.json();
    if (rec.error) throw new Error(rec.error);
    renderResult(rec);
  } catch (e) {
    $('#result').innerHTML = `<div class="empty">运行失败：${esc(e.message)}</div>`;
    $('#resultMeta').textContent = '失败';
  } finally {
    btn.disabled = false;
    btn.textContent = '运行';
  }
}

async function loadLLMStatus() {
  try {
    const r = await fetch('/api/llm/status');
    const d = await r.json();
    const el = $('#llmInfo');
    if (d.available) {
      el.innerHTML = `<span style="color:var(--olive)">● AI 已连接</span> · ${esc(d.model)}`;
      $('#llmState').textContent = '（已检测到 key）';
    } else {
      el.innerHTML = `<span style="color:var(--amber)">● 未配置 key</span> · 当前走离线规则<br>`
        + `在项目根目录 .env 里填 DEEPSEEK_API_KEY`;
      $('#llmState').textContent = '（未检测到 key）';
    }
    $('#llmTest').onclick = async () => {
      const b = $('#llmTest');
      b.disabled = true; b.textContent = '测试中…';
      try {
        const rr = await fetch('/api/llm/test', { method: 'POST' });
        const dd = await rr.json();
        if (dd.ok) {
          el.innerHTML = `<span style="color:var(--olive)">● 连接正常</span> · ${esc(dd.model)} · ${dd.latency_ms}ms`;
        } else {
          el.innerHTML = `<span style="color:var(--p0)">● 失败</span> ${esc(dd.error || '')}`;
        }
      } catch (e) {
        el.innerHTML = `<span style="color:var(--p0)">● 失败</span> ${esc(e.message)}`;
      } finally {
        b.disabled = false; b.textContent = '测试 AI 连接';
      }
    };
  } catch (e) {
    $('#llmInfo').textContent = '状态获取失败';
  }
}

function renderResult(rec) {
  const v = rec.view || {};
  const parts = [];

  // 名单
  if (v.plan && v.plan.length) {
    parts.push(`<div class="card-h" style="padding:0 0 8px;border:none">
      <h2 style="font-size:12.5px;color:var(--muted);letter-spacing:.08em">入选名单</h2>
      <a class="btn-s" href="/api/export" style="text-decoration:none">导出 CSV</a></div>
      <table><thead><tr>
        <th>达人</th><th>平台</th><th>分层</th><th>分数</th><th>报价</th><th>入选理由</th><th></th>
      </tr></thead><tbody>` +
      v.plan.map((p) => `<tr>
        <td><b>${esc(p.handle)}</b><br><span style="font-size:11px;color:var(--muted)">${esc(p.kol_id)}</span></td>
        <td>${esc(p.platform)}</td>
        <td><span class="tier ${esc(p.tier)}">${esc(p.tier)}</span></td>
        <td class="num">${p.score}</td>
        <td class="num">${money(p.quote)}</td>
        <td style="font-size:11.5px;color:var(--muted)">${esc(p.reason)}</td>
        <td style="white-space:nowrap">
          <button class="btn-s" data-brief="${esc(p.kol_id)}">Brief</button>
          <button class="btn-s" data-outreach="${esc(p.kol_id)}">邀约</button>
        </td>
      </tr>`).join('') + '</tbody></table>');
  }

  // 告警
  if (v.alerts && v.alerts.length) {
    parts.push(`<h2 style="font-size:12.5px;color:var(--muted);letter-spacing:.08em;margin:18px 0 8px">监测告警</h2>
      <table><thead><tr><th>级别</th><th>达人</th><th>规则</th><th>变化</th><th>建议</th></tr></thead><tbody>` +
      v.alerts.map((a) => `<tr>
        <td><span class="tier ${a.severity === 'P0' ? 'C' : 'B'}">${esc(a.severity)}</span></td>
        <td>${esc(a.kol_id)}</td><td>${esc(a.rule)}</td>
        <td class="num" style="color:${a.delta_pct < 0 ? 'var(--p0)' : 'var(--amber)'}">${a.delta_pct}%</td>
        <td style="font-size:11.5px;color:var(--muted)">${esc(a.hint)}</td>
      </tr>`).join('') + '</tbody></table>');
  }

  // 漏斗
  if (v.funnels && v.funnels.length) {
    parts.push(`<h2 style="font-size:12.5px;color:var(--muted);letter-spacing:.08em;margin:18px 0 8px">漏斗诊断</h2>`);
    v.funnels.forEach((f) => {
      const dev = f.deviation_pct || {};
      const cells = Object.keys(dev).map((k) => {
        const d = dev[k];
        const cls = Math.abs(d) < 5 ? 'flat' : d > 0 ? 'up' : 'down';
        return `<div class="fstep"><div class="fk">${esc(k)}</div>
          <div class="fd ${cls}">${d > 0 ? '+' : ''}${d}%</div></div>`;
      }).join('');
      parts.push(`<div style="margin-bottom:12px">
        <div style="font-size:12.5px;margin-bottom:6px"><b>${esc(f.kol_id)}</b>
          <span style="color:var(--muted)">主因 ${esc(f.main_driver)}</span></div>
        <div class="funnel">${cells}</div>
        <div style="font-size:11.5px;color:var(--muted);margin-top:6px">→ ${esc(f.suggested_action)}</div>
      </div>`);
    });
  }

  // 复写
  if (v.rewrites && v.rewrites.length) {
    parts.push(`<h2 style="font-size:12.5px;color:var(--muted);letter-spacing:.08em;margin:18px 0 8px">内容复写</h2>`);
    v.rewrites.forEach((w) => {
      const before = w.before_compliance?.hit_count ?? '—';
      const after = w.after_compliance?.hit_count ?? '—';
      parts.push(`<div class="rw">
        <div class="rw-h"><b>${esc(w.source_id)}</b>　${esc(w.title || '')}
          <span class="chip">${esc(w.mode)}</span>
          <span class="chip">${w.length} 字 / 目标 ${(w.target_length || []).join('–')}</span>
          <span class="chip">违规 <span class="${before > 0 ? 'bad' : ''}">${before}</span> → <span class="${after === 0 ? 'good' : 'bad'}">${after}</span></span>
        </div>
        <div class="rw-b">${esc(w.body)}</div>
        <div class="rw-m">改动：${(w.changes || []).map(esc).join('；')}</div>
      </div>`);
    });
  }

  // 结论
  parts.push(`<h2 style="font-size:12.5px;color:var(--muted);letter-spacing:.08em;margin:18px 0 8px">结论</h2>
    <div class="final">${esc(rec.final)}</div>`);

  if (rec.warnings && rec.warnings.length) {
    parts.push(`<div class="risk">${[...new Set(rec.warnings)].map((w) => `<div>· ${esc(w)}</div>`).join('')}</div>`);
  }

  $('#result').innerHTML = parts.join('');
  const m = rec.agent_meta || {};
  $('#resultMeta').textContent = `${rec.planner}${m.model ? ' · ' + m.model : ''} · ${rec.steps} 步 · ${rec.elapsed_ms}ms`
    + (m.tokens ? ` · ${m.tokens} tokens` : '')
    + (rec.stopped_early ? ' · 中途终止' : '');

  if (m.plan && m.plan.length) {
    $('#planBox').style.display = '';
    $('#planBox').innerHTML = `<div style="font-size:11.5px;color:var(--muted);margin-bottom:5px">模型自己定的计划</div>`
      + `<ol style="margin:0;padding-left:18px;font-size:12.5px;color:var(--ink2);line-height:1.9">`
      + m.plan.map((t) => `<li>${esc(t)}</li>`).join('') + `</ol>`;
  } else {
    $('#planBox').style.display = 'none';
  }
  $('#traceMeta').textContent = `${rec.planner === 'llm' ? '模型逐步决策，每步可核对' : '离线规则推进，每步可核对'}`;

  renderTrace(rec.trace || []);
  bindBriefButtons();
  bindOutreachButtons();
}

function renderTrace(trace) {
  if (!trace.length) return;
  $('#traceCard').style.display = '';
  $('#trace').innerHTML = trace.map((s) => {
    const obs = JSON.stringify(s.observation || {});
    return `<div class="step">
      <div class="n">${s.step}</div>
      <div><div class="tool">${esc(s.tool)}</div>
        <div class="obs">${esc(obs.slice(0, 220))}</div></div>
      <div class="ms">${s.elapsed_ms}ms</div>
    </div>`;
  }).join('');
}

/* ---------------- 交互 ---------------- */

function bindBriefButtons() {
  document.querySelectorAll('[data-brief]').forEach((b) => {
    b.onclick = async () => {
      const id = b.getAttribute('data-brief');
      const old = b.textContent;
      b.textContent = '…';
      try {
        const r = await fetch(`/api/brief?ids=${encodeURIComponent(id)}`);
        const md = await r.text();
        await navigator.clipboard.writeText(md);
        b.textContent = '已复制';
      } catch (e) {
        b.textContent = '复制失败';
      }
      setTimeout(() => { b.textContent = old; }, 1600);
    };
  });
}

function bindOutreachButtons() {
  document.querySelectorAll('[data-outreach]').forEach((b) => {
    b.onclick = async () => {
      const id = b.getAttribute('data-outreach');
      const old = b.textContent;
      b.textContent = '…';
      try {
        const r = await fetch(`/api/outreach?ids=${encodeURIComponent(id)}`);
        const d = await r.json();
        const msg = (d.messages || [])[0];
        if (!msg || msg.error) throw new Error(msg?.error || '生成失败');
        const text = `${msg.subject}\n\n${msg.body}\n\n（发送前确认：${(msg.tips || []).join('；')}）`;
        await navigator.clipboard.writeText(text);
        b.textContent = '已复制';
      } catch (e) {
        b.textContent = '失败';
      }
      setTimeout(() => { b.textContent = old; }, 1600);
    };
  });
}

async function generateReport() {
  const btn = $('#reportBtn');
  btn.disabled = true;
  btn.textContent = '生成中…';
  try {
    const budget = Number($('#budget').value) || 8000;
    const r = await fetch(`/api/report?budget=${budget}`);
    const md = await r.text();
    $('#reportBody').textContent = md;
    $('#reportCard').style.display = '';
    $('#reportMeta').textContent = `${md.length} 字 · 可直接复制或推送`;
    await navigator.clipboard.writeText(md);
    $('#reportBtn').textContent = '已生成并复制';
  } catch (e) {
    $('#reportBody').textContent = `生成失败：${e.message}`;
    $('#reportCard').style.display = '';
  } finally {
    btn.disabled = false;
    setTimeout(() => { btn.textContent = '生成日报'; }, 1800);
  }
}

function bindReportActions() {
  $('#reportBtn').onclick = generateReport;
  $('#copyReport').onclick = async () => {
    await navigator.clipboard.writeText($('#reportBody').textContent || '');
    $('#copyReport').textContent = '已复制';
    setTimeout(() => { $('#copyReport').textContent = '复制'; }, 1500);
  };
  $('#pushReport').onclick = async () => {
    const btn = $('#pushReport');
    btn.disabled = true;
    btn.textContent = '推送中…';
    try {
      const r = await fetch('/api/notify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: true, budget: Number($('#budget').value) || 8000 }),
      });
      const d = await r.json();
      $('#reportMeta').textContent = d.sent
        ? `已发送给 ${(d.recipients || []).join(', ')}`
        : `未发送：${d.reason || d.error || d.mode}${d.path ? ' → ' + d.path : ''}`;
    } catch (e) {
      $('#reportMeta').textContent = `推送失败：${e.message}`;
    } finally {
      btn.disabled = false;
      btn.textContent = '推送测试';
    }
  };
}

document.querySelectorAll('.preset').forEach((p) => {
  p.onclick = () => runAgent(p.dataset.goal);
});

$('#runBtn').onclick = () => {
  const goal = $('#goalLine').textContent.includes('——')
    ? '指压板新品起量，预算 8000'
    : $('#goalLine').textContent;
  runAgent(goal);
};

$('#budget').onchange = loadOverview;

function bindLeadPool() {
  const ta = $('#leadText');
  $('#leadSample').onclick = () => {
    ta.value = '抖音号：jiuzuo2024 粉丝 12.3w，做久坐缓解的\n'
      + '小红书号：aijiankang_xhs 主页 https://www.xiaohongshu.com/user/profile/5f8a2b1c\n'
      + '还有 v.douyin.com/iRxT9kQ 粉丝4.5万';
  };

  $('#leadRun').onclick = async () => {
    const text = (ta.value || '').trim();
    if (!text) { $('#leadMeta').textContent = '先粘贴内容或点「填入示例」'; return; }
    const btn = $('#leadRun');
    btn.disabled = true; btn.textContent = '解析中…';
    $('#leadMeta').textContent = '';
    try {
      const r = await fetch('/api/pipeline', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, write: true, push: false }),
      });
      const d = await r.json();
      if (d.error) throw new Error(d.error);
      renderLeads(d);
    } catch (e) {
      $('#leadResult').innerHTML = `<div class="empty">失败：${esc(e.message)}</div>`;
    } finally {
      btn.disabled = false; btn.textContent = '解析并入库';
    }
  };
}

function renderLeads(d) {
  const leads = d.leads || [];
  const w = d.write_result || {};
  $('#leadMeta').textContent =
    `抽到 ${d.accounts_found} 个账号 · 评分 ${d.scored} 条 · 高匹配 ${(d.outreach_queue||[]).length} 条 · `
    + `写入 ${w.mode}${w.path ? '（' + w.path.split(/[\\/]/).pop() + '）' : ''} · 画像来源 ${d.provider}`;

  if (!leads.length) {
    $('#leadResult').innerHTML = '<div class="empty">没有从这段内容里识别到账号 ID。格式需包含「抖音号：」「小红书号：」或主页链接。</div>';
    return;
  }

  const rows = leads.map((l) => `<tr>
      <td>${esc(l.platform)}</td>
      <td><b>${esc(l.account_id)}</b></td>
      <td>${esc(l.handle || '')}</td>
      <td>${esc(l.category || '')} / ${esc(l.style || '')}</td>
      <td class="num">${(l.followers || 0).toLocaleString()}</td>
      <td class="num">${l.score}</td>
      <td><span class="tier ${esc(l.tier)}">${esc(l.tier)}</span></td>
      <td style="font-size:11.5px;color:var(--muted);max-width:220px">${esc(l.breakdown || '')}</td>
      <td style="font-size:11.5px">${esc(l.action || '')}</td>
    </tr>`).join('');

  let extra = '';
  if ((d.outreach_queue || []).length) {
    extra = `<div style="margin-top:12px">
      <div style="font-size:12px;color:var(--muted);margin-bottom:6px">待发队列（需人工确认后发送）</div>`
      + d.outreach_queue.map((q, i) => `<div class="rw">
          <div class="rw-h"><b>${esc(q.lead.handle || q.lead.account_id)}</b>
            <span class="chip">${esc(q.lead.tier)} · ${q.lead.score}</span>
            <button class="btn-s" data-copyq="${i}">复制话术</button></div>
          <div class="rw-b">${esc(q.outreach.body)}</div>
          <div class="rw-m">货盘：${q.outreach.pack.map((p) => `${p.sku} ¥${p.price}/${Math.round(p.commission*100)}%`).join('　')}</div>
        </div>`).join('') + '</div>';
  }

  $('#leadResult').innerHTML = `<table><thead><tr>
      <th>平台</th><th>账号</th><th>昵称</th><th>方向/风格</th><th>粉丝</th>
      <th>匹配分</th><th>分层</th><th>风格拆解</th><th>建议动作</th>
    </tr></thead><tbody>${rows}</tbody></table>${extra}`;

  document.querySelectorAll('[data-copyq]').forEach((b) => {
    b.onclick = async () => {
      const q = d.outreach_queue[Number(b.getAttribute('data-copyq'))];
      await navigator.clipboard.writeText(`${q.outreach.body}\n\n（${(q.outreach.tips||[]).join('；')}）`);
      b.textContent = '已复制';
      setTimeout(() => { b.textContent = '复制话术'; }, 1500);
    };
  });
}

bindLeadPool();
bindReportActions();
loadLLMStatus();
loadOverview();
