// 内容库
import { api } from '../api.js';
import { icon } from '../icons.js';
import { $, $$, esc, kpi, platformTag, emptyState, openModal, copyText, toast } from '../ui.js';
import { num } from '../format.js';

export async function renderLibrary(root) {
  const data = await api.samples();
  const state = { platform: '', status: '', q: '' };
  const passCount = data.samples.filter((s) => s.compliance?.pass).length;

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>内容库</h1>
        <p>待复写的合成样本与合规预检结果。选一条进入复写，原文与改写后会逐平台对照。</p>
      </div>
      <div class="actions">
        <button class="btn btn-primary" id="newRewrite">${icon('plus', 14)} 新建复写任务</button>
      </div>
    </div>

    <div class="grid grid-3">
      ${kpi({ iconName: 'book', tone: 'blue', label: '内容样本', value: num(data.samples.length), unit: '条', foot: '<span class="muted">合成样例</span>' })}
      ${kpi({ iconName: 'shield', tone: 'green', label: '合规样本', value: num(passCount), unit: '条', foot: `<span class="muted">违规 ${data.samples.length - passCount} 条待清洗</span>` })}
      ${kpi({ iconName: 'layers', tone: 'violet', label: '覆盖平台', value: String(new Set(data.samples.map((s) => s.platform)).size), unit: '个', foot: `<span class="muted">${[...new Set(data.samples.map((s) => s.platform))].join(' / ')}</span>` })}
    </div>

    <section class="card mt-16">
      <div class="card-tools" style="padding-top:14px">
        <div class="flex" style="gap:8px">
          <select class="select" id="libPlatform" style="width:120px;height:30px">
            <option value="">全部平台</option>
            ${[...new Set(data.samples.map((s) => s.platform))].map((p) => `<option>${esc(p)}</option>`).join('')}
          </select>
          <select class="select" id="libStatus" style="width:120px;height:30px">
            <option value="">全部状态</option><option value="pass">合规</option><option value="fail">有违规</option>
          </select>
        </div>
        <div class="right flex" style="gap:8px">
          <div class="search" style="width:200px;margin:0">${icon('search', 14)}
            <input id="libSearch" placeholder="搜索标题 / ID" style="height:30px"></div>
        </div>
      </div>
      <div class="card-b flush" id="libTable"></div>
    </section>`;

  $('#newRewrite', root).addEventListener('click', () => { location.hash = '#/content'; });
  ['libPlatform', 'libStatus'].forEach((id) => $('#' + id, root).addEventListener('change', () => {
    state.platform = $('#libPlatform', root).value;
    state.status = $('#libStatus', root).value;
    render();
  }));
  $('#libSearch', root).addEventListener('input', (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });

  render();

  function render() {
    const rows = data.samples.filter((s) => {
      if (state.platform && s.platform !== state.platform) return false;
      if (state.status === 'pass' && !s.compliance?.pass) return false;
      if (state.status === 'fail' && s.compliance?.pass) return false;
      if (state.q && !(s.title + ' ' + s.id).toLowerCase().includes(state.q)) return false;
      return true;
    });
    const el = $('#libTable', root);
    if (!rows.length) { el.innerHTML = emptyState('没有符合条件的内容', 'book'); return; }
    el.innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>内容</th><th class="nw">平台</th><th class="nw">字数</th><th class="nw">合规状态</th><th>标注问题</th><th></th></tr></thead>
      <tbody>${rows.map((s) => `<tr>
        <td><div class="name"><div><div class="t1">${esc(s.title)}</div><div class="t2">${esc(s.id)}</div></div></div></td>
        <td class="nw">${platformTag(s.platform)}</td>
        <td class="nw num">${s.length}</td>
        <td class="nw">${s.compliance?.pass ? '<span class="badge green dot">合规</span>' : `<span class="badge red dot">${s.compliance.hit_count} 处</span>`}</td>
        <td class="muted">${esc(s.problem || '—')}</td>
        <td class="actions"><button class="link-btn" data-preview="${esc(s.id)}">预览</button>
          <button class="link-btn" data-rewrite="${esc(s.id)}" style="margin-left:8px">去复写</button></td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-preview]', el).forEach((b) => b.addEventListener('click', () => {
      const s = data.samples.find((x) => x.id === b.dataset.preview);
      openModal({
        title: s.title,
        body: `<div class="flex wrap" style="gap:8px;margin-bottom:10px">${platformTag(s.platform)}
            <span class="badge gray">${s.length} 字</span>
            ${s.compliance?.pass ? '<span class="badge green">合规</span>' : `<span class="badge red">${s.compliance.hit_count} 处违规</span>`}</div>
          <div class="doc-card"><div class="body">${esc(s.body)}</div>
            <div class="foot"><span>${esc(s.problem || '')}</span></div></div>
          ${!(s.compliance?.pass) ? `<div class="notice red mt-12">${icon('alert', 14)}<div>命中：${esc([...new Set((s.compliance.hits || []).map((h) => h.word))].join('、'))}</div></div>` : ''}`,
        footer: `<button class="btn btn-sm" id="copyLibBody">${icon('copy', 13)} 复制原文</button>
          <button class="btn btn-sm" id="useLibBody">${icon('edit', 13)} 用这条复写</button>
          <span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeLib">关闭</button>`,
        onMount(m, close) {
          $('#closeLib', m).addEventListener('click', close);
          $('#copyLibBody', m).addEventListener('click', () => copyText(s.body));
          $('#useLibBody', m).addEventListener('click', () => { close(); location.hash = '#/content?sample=' + encodeURIComponent(s.id); });
        },
      });
    }));
    $$('[data-rewrite]', el).forEach((b) => b.addEventListener('click', () => {
      location.hash = '#/content?sample=' + encodeURIComponent(b.dataset.rewrite);
    }));
  }
}
