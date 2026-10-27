// 日报中心
import { api } from '../api.js';
import { store } from '../state.js';
import { icon } from '../icons.js';
import { $, $$, esc, openModal, copyText, toast, mountMarkdown, emptyState } from '../ui.js';
import { money, dateTime } from '../format.js';

export async function renderReports(root, { focus = '' } = {}) {
  const [md, hist] = await Promise.all([api.report(store.budget), api.reports().catch(() => ({ items: [] }))]);

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>日报中心</h1>
        <p>汇总监测告警 + 复盘结论 + 预算执行情况，生成可直接发主管的 Markdown 日报。</p>
      </div>
      <div class="actions">
        <button class="btn" id="regenBtn">${icon('refresh', 14)} 重新生成</button>
        <button class="btn btn-primary" id="notifyBtn">${icon('send', 14)} 推送测试</button>
      </div>
    </div>

    <div class="split">
      <section class="card">
        <div class="card-h">
          <h2>今日日报</h2>
          <span class="badge gray">预算口径 ${money(store.budget)}</span>
          <div class="right flex" style="gap:8px">
            <button class="btn btn-sm" id="copyBtn">${icon('copy', 13)} 复制</button>
            <button class="btn btn-sm" id="downloadBtn">${icon('download', 13)} 下载 .md</button>
          </div>
        </div>
        <div class="card-b">
          <div class="markdown" id="reportBody" style="max-height:64vh;overflow:auto;padding-right:6px"></div>
        </div>
      </section>

      <div>
        <section class="card" id="section-history">
          <div class="card-h"><h2>历史记录</h2><div class="right muted tiny">${hist.items.length} 份</div></div>
          <div class="card-b" id="historyList"></div>
        </section>

        <section class="card">
          <div class="card-h"><h2>推送说明</h2></div>
          <div class="card-b">
            <div class="muted tiny" style="line-height:1.8">
              · 默认 dry-run：落盘到 <code>outbox/</code>，不会真的发出去<br>
              · 配置企微 Webhook 后才走真实推送<br>
              · 日报里的 P0/P1 数量、结论、待确认项都来自工具返回
            </div>
            <div class="notice mt-12">${icon('shield', 14)}<div>对外发送前请人工确认收件人与内容。</div></div>
          </div>
        </section>
      </div>
    </div>`;

  mountMarkdown($('#reportBody', root), md);

  $('#copyBtn', root).addEventListener('click', () => copyText(md));
  $('#downloadBtn', root).addEventListener('click', () => {
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `KOL日报-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast('已下载日报');
  });
  $('#regenBtn', root).addEventListener('click', () => renderReports(root));
  $('#notifyBtn', root).addEventListener('click', async () => {
    try {
      const res = await api.notify({ dry_run: true });
      openModal({
        title: '推送结果（dry-run）',
        body: `<div class="notice">${icon('check-circle', 15)}<div>未真实发送，已落盘到 outbox/。</div></div>
          <pre class="code mt-12">${esc(JSON.stringify(res, null, 2))}</pre>`,
        size: 'sm',
      });
      toast('已生成 dry-run 推送记录');
    } catch (e) { toast('推送失败：' + e.message, 'err'); }
  });

  renderHistory(hist.items);

  function renderHistory(items) {
    const el = $('#historyList', root);
    if (!items.length) { el.innerHTML = emptyState('还没有历史日报', 'clock'); return; }
    el.innerHTML = `<div class="list report-hist">${items.map((it) => `
      <div class="list-item" data-file="${esc(it.file)}" style="cursor:pointer">
        <span class="ico" style="background:var(--primary-soft);color:var(--primary)">${icon('file-text', 14)}</span>
        <div class="grow"><div class="t1">${esc(it.title)}</div>
          <div class="t2">${esc(it.file)} · ${(it.size / 1024).toFixed(1)} KB</div></div>
        <div class="meta">${dateTime(it.ts * 1000)}</div>
      </div>`).join('')}</div>`;

    $$('[data-file]', el).forEach((row) => row.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/reports/' + encodeURIComponent(row.dataset.file));
        if (!res.ok) throw new Error('读取失败');
        const text = await res.text();
        openModal({
          title: row.dataset.file,
          body: `<div class="markdown" id="histBody" style="max-height:60vh;overflow:auto"></div>`,
          footer: `<button class="btn btn-sm" id="copyHist">${icon('copy', 13)} 复制</button><span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeHist">关闭</button>`,
          onMount(m, close) {
            mountMarkdown($('#histBody', m), text);
            $('#copyHist', m).addEventListener('click', () => copyText(text));
            $('#closeHist', m).addEventListener('click', close);
          },
        });
      } catch (e) { toast('读取失败：' + e.message, 'err'); }
    }));
  }
}
