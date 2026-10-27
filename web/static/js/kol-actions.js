// 达人相关弹窗：详情 / 合作方案 / 邀约话术
import { api } from './api.js';
import { icon } from './icons.js';
import { $, $$, esc, openModal, copyText, toast, platformTag, tierBadge, mountMarkdown } from './ui.js';
import { compact, money, num, pct } from './format.js';

export function showCandidate(row, { note = '分数为候选池内相对排序' } = {}) {
  if (!row) return;
  const dims = [['D1 匹配度', row.D1, 30], ['D2 内容力', row.D2, 25], ['D3 转化力', row.D3, 30], ['D4 性价比', row.D4, 15]];
  openModal({
    title: `${row.handle} · ${row.kol_id}`,
    body: `
      <div class="flex wrap" style="gap:8px;margin-bottom:14px">
        ${platformTag(row.platform)}<span class="badge gray">${esc(row.category)}</span>
        <span class="badge gray">${esc(row.content_category)}</span>${tierBadge(row.tier)}
      </div>
      <div class="grid grid-4" style="gap:10px;margin-bottom:14px">
        ${[['粉丝数', compact(row.followers)], ['预估报价', money(row.quote)], ['互动率', pct(row.engagement_rate * 100, 2)], ['履约率', pct(row.fulfill_rate * 100, 1)]]
          .map(([k, v]) => `<div class="panel" style="padding:10px"><div class="muted tiny">${k}</div>
            <div style="font-size:16px;font-weight:700;margin-top:3px">${v}</div></div>`).join('')}
      </div>
      <div class="field-label">四维评分明细（匹配 30 / 内容 25 / 转化 30 / 成本 15）</div>
      ${dims.map(([name, v, w]) => `<div class="basis-row" style="margin-bottom:8px"><span class="name">${name}</span>
        <span class="bar"><i style="width:${v}%"></i></span><span class="val">${num(v, 1)}</span>
        <span class="muted tiny" style="width:34px;text-align:right">×${w}%</span></div>`).join('')}
      <div class="flex" style="justify-content:space-between;margin-top:12px;padding-top:12px;border-top:1px solid var(--line)">
        <span class="muted">综合分</span><b style="font-size:20px">${num(row.total, 1)}</b>
      </div>
      <div class="notice mt-12">${icon('target', 15)}<div>${esc(note)}。换一批候选，同一达人的分数会变。</div></div>`,
    footer: `<button class="btn btn-sm" id="detailOutreach">${icon('message', 13)} 生成邀约</button>
      <button class="btn btn-sm" id="detailBrief">${icon('file-text', 13)} 合作方案</button>
      <span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeDetail">关闭</button>`,
    size: 'sm',
    onMount(el, close) {
      $('#closeDetail', el).addEventListener('click', close);
      $('#detailOutreach', el).addEventListener('click', () => { close(); openOutreach([row.kol_id]); });
      $('#detailBrief', el).addEventListener('click', () => { close(); openBrief([row.kol_id]); });
    },
  });
}

export async function openBrief(ids) {
  if (!ids.length) { toast('先勾选达人', 'err'); return; }
  try {
    const md = await api.brief(ids);
    openModal({
      title: `合作方案 · ${ids.length} 位达人`,
      body: `<div class="markdown" id="briefBody" style="max-height:52vh;overflow:auto;padding:2px 4px"></div>`,
      footer: `<button class="btn btn-sm" id="copyBrief">${icon('copy', 13)} 复制 Markdown</button><span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeBrief">关闭</button>`,
      onMount(el, close) {
        mountMarkdown($('#briefBody', el), md);
        $('#copyBrief', el).addEventListener('click', () => copyText(md));
        $('#closeBrief', el).addEventListener('click', close);
      },
    });
  } catch (e) { toast('生成失败：' + e.message, 'err'); }
}

export async function openOutreach(ids, channel = '私信') {
  if (!ids.length) { toast('先勾选达人', 'err'); return; }
  try {
    const res = await api.outreach(ids, channel);
    openOutreachModal(res.messages || [], channel);
  } catch (e) { toast('生成失败：' + e.message, 'err'); }
}

export function openOutreachModal(messages, channel = '私信') {
  openModal({
    title: `邀约话术 · ${messages.length} 条`,
    body: `<div style="display:flex;flex-direction:column;gap:12px">${messages.map((m, i) => `
      <div class="doc-card">
        <div class="head"><span class="badge blue">${esc(m.handle || m.kol_id)}</span>
          <span class="muted tiny">${esc(m.channel || channel)} · ${m.mode === 'llm' ? '模型生成' : '模板生成'}</span>
          <button class="link-btn right" data-copy-msg="${i}">${icon('copy', 12)} 复制</button></div>
        <div class="body">${esc(m.body || m.error || '')}</div>
        ${(m.tips || []).length ? `<div class="foot" style="display:block">${m.tips.map((t) => `· ${esc(t)}`).join('<br>')}</div>` : ''}
      </div>`).join('')}</div>`,
    footer: `<span class="notice tiny" style="padding:6px 9px">${icon('shield', 13)} 所有话术需人工确认后发送，不会自动私信</span>
      <span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeOutreach">关闭</button>`,
    onMount(el, close) {
      $('#closeOutreach', el).addEventListener('click', close);
      $$('[data-copy-msg]', el).forEach((b) => b.addEventListener('click', () => copyText(messages[Number(b.dataset.copyMsg)].body || '')));
    },
  });
}
