// 邀约管理：选人 → 生成话术 → 待发队列
import { api } from '../api.js';
import { icon } from '../icons.js';
import { $, $$, esc, avatar, emptyState, toast, copyText, platformTag, tierBadge } from '../ui.js';
import { money, num, dateTime } from '../format.js';

export async function renderOutreach(root) {
  const [data, queues] = await Promise.all([api.candidates({ budget: 8000 }), api.queues()]);
  const pool = data.rows.filter((r) => r.tier === 'S' || r.tier === 'A');
  const state = { q: '', selected: new Set(), messages: [], queue: null, channel: '私信' };

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>邀约管理</h1>
        <p>高分层达人批量生成首次触达话术，进入待发队列；所有话术需人工确认后发送，不自动私信。</p>
      </div>
      <div class="actions">
        <span class="badge amber dot">${pool.length} 位可邀约</span>
      </div>
    </div>

    <div class="split" style="grid-template-columns:minmax(0,1fr) 360px">
      <div>
        <section class="card">
          <div class="card-h"><h2>选择达人</h2><span class="badge">S/A 层</span>
            <div class="right flex" style="gap:8px">
              <div class="search" style="width:190px;margin:0">${icon('search', 14)}
                <input id="outreachSearch" placeholder="搜索昵称 / ID" style="height:30px"></div>
            </div>
          </div>
          <div class="card-b" style="padding-top:10px">
            <div id="pickList" style="max-height:420px;overflow-y:auto;display:flex;flex-direction:column;gap:6px"></div>
            <div class="flex wrap mt-12" style="gap:10px">
              <span class="muted tiny">已选 <b id="pickCount">0</b> / 5（接口单次上限 5 位）</span>
              <span class="right">
                <select class="select" id="channelSel" style="width:100px;height:32px"><option>私信</option><option>邮件</option></select>
              </span>
            </div>
            <button class="btn btn-primary mt-12" id="genBtn" style="width:100%">${icon('message', 14)} 生成邀约话术</button>
          </div>
        </section>

        <section class="card" id="messageCard">
          <div class="card-h"><h2>话术结果</h2><span class="badge gray" id="msgMeta">未生成</span></div>
          <div class="card-b" id="messageBody">${emptyState('选择达人后点「生成邀约话术」', 'message')}</div>
        </section>
      </div>

      <div>
        <section class="card">
          <div class="card-h"><h2>待发队列</h2><div class="right muted tiny">${queues.items.length} 份</div></div>
          <div class="card-b" id="queueList"></div>
        </section>
        <section class="card" style="margin-top:16px">
          <div class="card-h"><h2>发送纪律</h2></div>
          <div class="card-b">
            <div class="muted tiny" style="line-height:1.9">
              · 首次私信不附产品链接，容易被判营销<br>
              · 报价区间按 75–95 折给，留谈判空间<br>
              · 确认对方近期还在该垂类更新<br>
              · 所有话术带「需人工终审」，不自动发送
            </div>
          </div>
        </section>
      </div>
    </div>`;

  renderPickList();
  renderQueues();
  $('#outreachSearch', root).addEventListener('input', (e) => { state.q = e.target.value.trim(); renderPickList(); });
  $('#channelSel', root).addEventListener('change', (e) => { state.channel = e.target.value; });
  $('#genBtn', root).addEventListener('click', generate);

  function filtered() {
    const q = state.q.toLowerCase();
    return pool.filter((r) => !q || (r.handle + ' ' + r.kol_id + ' ' + r.category).toLowerCase().includes(q));
  }

  function renderPickList() {
    const el = $('#pickList', root);
    const rows = filtered();
    if (!rows.length) { el.innerHTML = emptyState('没有匹配的达人', 'user-search'); return; }
    el.innerHTML = rows.map((r) => `<label class="pick-row" style="background:${state.selected.has(r.kol_id) ? 'var(--primary-soft)' : 'var(--surface-2)'};cursor:pointer">
      <input type="checkbox" data-pick="${esc(r.kol_id)}" ${state.selected.has(r.kol_id) ? 'checked' : ''}
        style="width:15px;height:15px;accent-color:var(--primary)">
      ${avatar(r.handle)}
      <div class="grow" style="min-width:0"><div class="t1">${esc(r.handle)}</div>
        <div class="t2">${esc(r.platform)} · ${r.tier} 层 · ${num(r.total, 1)} 分 · ${esc(r.category)}</div></div>
      <span class="amt">${money(r.quote)}</span>
    </label>`).join('');

    $$('[data-pick]', el).forEach((cb) => cb.addEventListener('change', () => {
      const id = cb.dataset.pick;
      if (cb.checked) {
        if (state.selected.size >= 5) { cb.checked = false; toast('单次最多 5 位', 'err'); return; }
        state.selected.add(id);
      } else state.selected.delete(id);
      $('#pickCount', root).textContent = String(state.selected.size);
      renderPickList();
    }));
  }

  function renderQueues() {
    const el = $('#queueList', root);
    if (!queues.items.length) { el.innerHTML = emptyState('还没有待发队列，可在线索入库生成', 'send'); return; }
    el.innerHTML = `<div class="list">${queues.items.map((q) => `<div class="list-item" data-queue="${esc(q.file)}" style="cursor:pointer">
      <span class="ico" style="background:var(--green-soft);color:#059669">${icon('send', 14)}</span>
      <div class="grow"><div class="t1">${esc(q.file)}</div>
        <div class="t2">${q.count} 条 · ${(q.size / 1024).toFixed(1)} KB</div></div>
      <div class="meta">${dateTime(q.ts * 1000)}</div>
    </div>`).join('')}</div>`;

    $$('[data-queue]', el).forEach((row) => row.addEventListener('click', async () => {
      try {
        const q = await api.queue(row.dataset.queue);
        const msgs = (q.items || []).map((it) => ({
          handle: it.lead?.handle || it.lead?.account_id,
          channel: state.channel,
          body: it.lead?.outreach?.body || it.outreach?.body || '',
          tips: it.lead?.outreach?.tips || [],
          mode: 'queue',
        })).filter((m) => m.body);
        state.messages = msgs;
        $('#msgMeta', root).textContent = `队列 · ${msgs.length} 条`;
        renderMessages();
        toast(`已载入 ${msgs.length} 条待发话术`);
      } catch (e) { toast('读取队列失败：' + e.message, 'err'); }
    }));
  }

  async function generate() {
    const ids = [...state.selected];
    if (!ids.length) { toast('先选择达人', 'err'); return; }
    const btn = $('#genBtn', root);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>生成中…';
    try {
      const res = await api.outreach(ids, state.channel);
      state.messages = res.messages || [];
      $('#msgMeta', root).textContent = `${state.messages.length} 条 · ${state.channel}`;
      renderMessages();
      toast('已生成 ' + state.messages.length + ' 条话术');
    } catch (e) { toast('生成失败：' + e.message, 'err'); }
    finally {
      btn.disabled = false;
      btn.innerHTML = `${icon('message', 14)} 生成邀约话术`;
    }
  }

  function renderMessages() {
    const el = $('#messageBody', root);
    if (!state.messages.length) { el.innerHTML = emptyState('还没有话术', 'message'); return; }
    el.innerHTML = `<div style="display:flex;flex-direction:column;gap:10px">${state.messages.map((m, i) => `
      <div class="doc-card">
        <div class="head">
          <span class="badge blue">${esc(m.handle || m.kol_id || '')}</span>
          <span class="muted tiny">${esc(m.channel || state.channel)} · ${m.mode === 'llm' ? '模型生成' : '模板生成'}</span>
          <button class="link-btn right" data-copy="${i}">${icon('copy', 12)} 复制</button>
        </div>
        <div class="body">${esc(m.body || m.error || '')}</div>
        ${(m.tips || []).length ? `<div class="foot" style="display:block">${m.tips.map((t) => `· ${esc(t)}`).join('<br>')}</div>` : ''}
      </div>`).join('')}
      <div class="notice">${icon('shield', 14)}<div>发送前请人工确认对象、报价与近期内容方向。</div></div>
    </div>`;
    $$('[data-copy]', el).forEach((b) => b.addEventListener('click', () => copyText(state.messages[Number(b.dataset.copy)].body || '')));
  }
}
