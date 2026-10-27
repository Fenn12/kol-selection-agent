// 合规检查
import { api } from '../api.js';
import { icon } from '../icons.js';
import { $, $$, esc, emptyState, toast, platformTag } from '../ui.js';
import { num } from '../format.js';

const CATEGORY_TONE = {
  绝对化: 'red', 医疗功效: 'amber', 替代医疗: 'red', 硬引导: 'violet', 疗效时间承诺: 'amber',
};

export async function renderCompliance(root) {
  const data = await api.samples();
  const state = { result: null, text: '', history: [], checking: false };

  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>合规检查</h1>
        <p>确定性规则扫描：极限词、医疗功效、替代医疗、硬引导、疗效时间承诺。不调模型，同样的输入永远同样的结果。</p>
      </div>
      <div class="actions">
        <button class="btn" id="goContent">${icon('edit', 14)} 去内容复写</button>
      </div>
    </div>

    <div class="split">
      <section class="card">
        <div class="card-h"><h2>待检查文本</h2><span class="badge gray">支持粘贴任意文案</span></div>
        <div class="card-b">
          <textarea class="textarea" id="checkText" style="min-height:190px" placeholder="粘贴一条准备发布的内容…"></textarea>
          <div class="flex wrap mt-12" style="gap:8px">
            <span class="muted tiny">示例：</span>
            ${data.samples.map((s) => `<button class="chip" data-sample="${esc(s.id)}" style="height:26px;font-size:11.5px">${esc(s.title)}</button>`).join('')}
          </div>
          <div class="flex mt-12" style="gap:8px">
            <button class="btn btn-primary" id="checkBtn">${icon('shield', 14)} 开始检查</button>
            <button class="btn" id="clearBtn">清空</button>
            <span class="muted tiny right" id="charCount">0 字</span>
          </div>
        </div>
      </section>

      <section class="card" id="resultCard">
        <div class="card-h"><h2>检查结果</h2><div class="right muted tiny" id="resultMeta"></div></div>
        <div class="card-b" id="resultBody">${emptyState('粘贴或选择一条文案后检查', 'shield')}</div>
      </section>
    </div>

    <section class="card mt-16">
      <div class="card-h"><h2>本次检查记录</h2><div class="right muted tiny">只保存在当前页面</div></div>
      <div class="card-b" id="historyBody">${emptyState('还没有检查记录', 'clock')}</div>
    </section>`;

  const textEl = $('#checkText', root);
  textEl.addEventListener('input', () => { $('#charCount', root).textContent = `${textEl.value.trim().length} 字`; });

  $$('[data-sample]', root).forEach((b) => b.addEventListener('click', () => {
    const s = data.samples.find((x) => x.id === b.dataset.sample);
    textEl.value = s.body;
    textEl.dispatchEvent(new Event('input'));
    textEl.focus();
  }));

  $('#clearBtn', root).addEventListener('click', () => {
    textEl.value = '';
    textEl.dispatchEvent(new Event('input'));
    state.result = null;
    $('#resultMeta', root).textContent = '';
    $('#resultBody', root).innerHTML = emptyState('粘贴或选择一条文案后检查', 'shield');
  });

  $('#checkBtn', root).addEventListener('click', check);
  $('#goContent', root).addEventListener('click', () => { location.hash = '#/content'; });

  async function check() {
    const text = textEl.value.trim();
    if (!text) { toast('先粘贴一段文案', 'err'); return; }
    if (state.checking) return;
    state.checking = true;
    const btn = $('#checkBtn', root);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>检查中…';
    try {
      const res = await api.compliance(text);
      state.result = res;
      renderResult(res);
      state.history.unshift({ text, res, at: new Date() });
      state.history = state.history.slice(0, 6);
      renderHistory();
      toast(res.pass ? '未发现违规词' : `命中 ${res.hit_count} 处违规`, res.pass ? 'ok' : 'err');
    } catch (e) {
      toast('检查失败：' + e.message, 'err');
    } finally {
      state.checking = false;
      btn.disabled = false;
      btn.innerHTML = `${icon('shield', 14)} 开始检查`;
    }
  }

  function renderResult(res) {
    $('#resultMeta', root).textContent = `${res.length} 字 · ${res.hit_count} 处命中`;
    const cats = [...new Set(res.hits.map((h) => h.category))];
    $('#resultBody', root).innerHTML = `
      <div class="flex" style="gap:10px;margin-bottom:12px">
        <span class="kpi-ico ${res.pass ? 'green' : 'red'}" style="width:40px;height:40px">
          ${icon(res.pass ? 'check' : 'alert', 20)}</span>
        <div>
          <div style="font-weight:700;font-size:15px">${res.pass ? '未发现违规' : `命中 ${res.hit_count} 处违规`}</div>
          <div class="muted tiny">${res.pass ? '仍需人工终审后发布' : '建议按建议逐条修改后重查'}</div>
        </div>
      </div>
      ${cats.length ? `<div class="flex wrap" style="gap:6px;margin-bottom:10px">
        ${cats.map((c) => `<span class="badge ${CATEGORY_TONE[c] || 'gray'}">${esc(c)} · ${res.hits.filter((h) => h.category === c).length}</span>`).join('')}
      </div>` : ''}
      ${res.hits.length ? `<div class="table-wrap"><table class="table table-compact">
        <thead><tr><th>类别</th><th>命中词</th></tr></thead>
        <tbody>${res.hits.map((h) => `<tr><td class="nw">${esc(h.category)}</td><td><span class="badge red">${esc(h.word)}</span></td></tr>`).join('')}</tbody>
      </table></div>` : ''}
      <div class="notice ${res.pass ? '' : 'amber'} mt-12">${icon('shield', 14)}
        <div>${res.suggestions.map(esc).join('<br>')}</div></div>
      <div class="muted tiny mt-12">检查规则为确定性匹配，不调模型；「三天见效」这类中文数字时间承诺需人工复核。</div>`;
  }

  function renderHistory() {
    const el = $('#historyBody', root);
    if (!state.history.length) { el.innerHTML = emptyState('还没有检查记录', 'clock'); return; }
    el.innerHTML = `<div class="list">${state.history.map((h) => `
      <div class="list-item">
        <span class="ico" style="background:${h.res.pass ? 'var(--green-soft)' : 'var(--red-soft)'};color:${h.res.pass ? '#059669' : 'var(--red)'}">
          ${icon(h.res.pass ? 'check' : 'alert', 14)}</span>
        <div class="grow"><div class="t1">${esc(h.text.slice(0, 42))}${h.text.length > 42 ? '…' : ''}</div>
          <div class="t2">${h.res.length} 字 · ${h.res.pass ? '合规' : h.res.hit_count + ' 处违规'}</div></div>
        <div class="meta">${h.at.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</div>
      </div>`).join('')}</div>`;
  }
}
