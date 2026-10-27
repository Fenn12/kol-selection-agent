// 线索入库（群消息 → 名单 → 待发队列）
import { api } from '../api.js';
import { icon } from '../icons.js';
import { $, $$, esc, openModal, copyText, toast, kpi, emptyState, platformTag, tierBadge } from '../ui.js';
import { money, num, truncate } from '../format.js';

const SAMPLE = `抖音号：jiuzuo2024 粉丝 12.3w，做久坐缓解的，最近在测居家好物
小红书号：aijiankang_xhs 主页 xiaohongshu.com/user/profile/5f8a2b1c，瑜伽 + 拉伸
视频号：K023 户外运动，之前带过筋膜枪
抖音号：footcare_lin 粉丝 8.6w，足部护理垂类`;

export async function renderLeads(root) {
  root.innerHTML = `
    <div class="page-head">
      <div>
        <h1>线索入库</h1>
        <p>粘贴企微群消息或回调体，Agent 抽账号 ID → 补画像 → 四维评分 → 分层 → 待发队列。</p>
      </div>
      <div class="actions">
        <button class="btn" id="sampleBtn">${icon('sparkles', 14)} 填入示例</button>
      </div>
    </div>

    <div class="split">
      <section class="card">
        <div class="card-h"><h2>粘贴群消息</h2><span class="badge gray">支持 小红书号 / 抖音号 / @handle / 纯 ID</span></div>
        <div class="card-b">
          <textarea class="textarea" id="leadText" style="min-height:150px;font-size:12.5px"
            placeholder="粘贴企微群消息，例如：&#10;抖音号：jiuzuo2024 粉丝 12.3w，做久坐缓解的&#10;小红书号：aijiankang_xhs 主页 xiaohongshu.com/user/profile/5f8a2b1c"></textarea>
          <div class="flex wrap mt-12" style="gap:12px">
            <label class="checkbox"><input type="checkbox" id="writeFeishu"> 写入飞书多维表格（未配置时降级 CSV）</label>
            <span class="right muted tiny">当前仅支持粘贴文本与回调体，不绕过企微权限</span>
          </div>
          <div class="flex mt-12" style="gap:8px">
            <button class="btn btn-primary" id="parseBtn">${icon('play', 14)} 解析并入库</button>
            <button class="btn" id="clearBtn">清空</button>
            <span class="muted tiny right" id="leadMeta"></span>
          </div>
        </div>
      </section>

      <div>
        <div class="panel">
          <div class="panel-head"><h3>处理规则</h3></div>
          <div class="muted tiny" style="line-height:1.8">
            · 抗误抓：<code>抖音号：jiuzuo2024 粉丝</code> 里的 2024 不会被当成粉丝数<br>
            · 粉丝数 &lt; 100 的候选直接丢弃<br>
            · 同一账号多次提及只保留一条<br>
            · 高分层（S/A）自动生成货盘与邀约话术，进入待发队列<br>
            · 所有话术需人工确认后发送
          </div>
        </div>
        <div class="panel mt-16" style="margin-top:16px">
          <div class="panel-head"><h3>队列状态</h3></div>
          <div id="queueInfo" class="muted tiny">还没有运行</div>
        </div>
      </div>
    </div>

    <div class="grid grid-4 mt-16" id="leadKpis"></div>

    <section class="card mt-16">
      <div class="card-h"><h2>解析结果</h2><div class="right muted tiny" id="leadTime"></div></div>
      <div class="card-b flush" id="leadResult">
        ${emptyState('粘贴群消息后点击「解析并入库」', 'inbox')}
      </div>
    </section>`;

  $('#sampleBtn', root).addEventListener('click', () => { $('#leadText', root).value = SAMPLE; });

  $('#clearBtn', root).addEventListener('click', () => {
    $('#leadText', root).value = '';
    $('#leadKpis', root).innerHTML = '';
    $('#leadResult', root).innerHTML = emptyState('粘贴群消息后点击「解析并入库」', 'inbox');
    $('#queueInfo', root).textContent = '还没有运行';
    $('#leadMeta', root).textContent = '';
  });

  $('#parseBtn', root).addEventListener('click', async () => {
    const text = $('#leadText', root).value.trim();
    if (!text) { toast('先粘贴一段群消息', 'err'); return; }
    const btn = $('#parseBtn', root);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>解析中…';
    $('#leadMeta', root).textContent = 'Agent 正在抽取账号、补全画像、评分…';
    try {
      const res = await api.pipeline({
        text,
        min_tier: 'A',
        write: $('#writeFeishu', root).checked,
        push: false,
      });
      renderResult(res);
      toast(`解析完成：${res.accounts_found} 个账号，${res.tier_count?.A || 0} 个 A 层`);
    } catch (e) {
      $('#leadResult', root).innerHTML = `<div class="notice red" style="margin:16px">${icon('alert', 15)}<div>${esc(e.message)}</div></div>`;
      toast('解析失败：' + e.message, 'err');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${icon('play', 14)} 解析并入库`;
      $('#leadMeta', root).textContent = '';
    }
  });

  function renderResult(res) {
    const leads = res.leads || [];
    const tiers = res.tier_count || {};
    const high = (tiers.S || 0) + (tiers.A || 0);
    $('#leadTime', root).textContent = `${res.accounts_found} 个账号 · ${res.scored} 条评分`;
    $('#leadKpis', root).innerHTML = [
      kpi({ iconName: 'inbox', tone: 'blue', label: '解析账号', value: num(res.accounts_found), unit: '个', foot: '<span class="muted">去重后</span>' }),
      kpi({ iconName: 'users', tone: 'green', label: '完成画像', value: num(res.profiles), unit: '个', foot: '<span class="muted">第三方指标已补全</span>' }),
      kpi({ iconName: 'target', tone: 'violet', label: '高匹配（S/A）', value: num(high), unit: '个', foot: `<span class="muted">B ${tiers.B || 0} / C ${tiers.C || 0}</span>` }),
      kpi({ iconName: 'send', tone: 'amber', label: '待发队列', value: num((res.leads || []).filter((l) => l.outreach).length), unit: '条', foot: '<span class="muted">人工确认后发送</span>' }),
    ].join('');

    $('#queueInfo', root).innerHTML = res.queue_path
      ? `<div>队列已落盘</div><div style="font-family:var(--mono);font-size:10.5px;margin-top:4px;word-break:break-all">${esc(res.queue_path)}</div>`
      : '<div>本次没有生成待发队列</div>';
    if (res.write) {
      $('#queueInfo', root).innerHTML += `<div class="mt-8"><span class="badge ${res.write.mode === 'feishu' ? 'green' : 'amber'}">飞书写入：${esc(res.write.mode)}</span></div>`;
    }

    if (!leads.length) {
      $('#leadResult', root).innerHTML = emptyState('没有解析到有效账号，检查一下文本格式', 'search');
      return;
    }

    $('#leadResult', root).innerHTML = `<div class="table-wrap"><table class="table">
      <thead><tr><th>账号</th><th>平台</th><th>内容方向</th><th>粉丝</th><th>报价</th><th>评分</th><th>分层</th><th>建议动作</th><th></th></tr></thead>
      <tbody>${leads.map((l, i) => `<tr>
        <td><div class="name"><div><div class="t1">${esc(l.handle || l.account_id)}</div><div class="t2">${esc(l.account_id)}</div></div></div></td>
        <td>${platformTag(l.platform)}</td>
        <td><span class="badge gray">${esc(l.category || '—')}</span></td>
        <td class="num">${l.followers ? (l.followers / 10000).toFixed(1) + 'w' : '—'}</td>
        <td class="num">${money(l.quote)}</td>
        <td><b class="num">${num(l.score, 1)}</b></td>
        <td>${tierBadge(l.tier)}</td>
        <td class="muted">${esc(truncate(l.action || '—', 16))}</td>
        <td class="actions">${l.outreach ? `<button class="link-btn" data-outreach="${i}">查看话术</button>` : '<span class="muted tiny">—</span>'}</td>
      </tr>`).join('')}</tbody></table></div>`;

    $$('[data-outreach]', $('#leadResult', root)).forEach((btn) => btn.addEventListener('click', () => {
      const l = leads[Number(btn.dataset.outreach)];
      const o = l.outreach || {};
      openModal({
        title: `邀约话术 · ${l.handle || l.account_id}`,
        body: `<div class="flex wrap" style="gap:6px;margin-bottom:10px">
            <span class="badge blue">${esc(l.tier)} 层</span><span class="badge">${num(l.score, 1)} 分</span>
            <span class="badge gray">${esc(l.category || '')}</span></div>
          ${(o.pack || []).length ? `<div class="field-label">货盘</div><div class="flex wrap" style="gap:6px;margin-bottom:12px">${o.pack.map((p) => `<span class="badge">${esc(p.sku)} · ¥${p.price} · 佣金 ${(p.commission * 100).toFixed(0)}%</span>`).join('')}</div>` : ''}
          <div class="doc-card"><div class="head"><span class="badge blue">话术</span></div><div class="body" id="msgBody">${esc(o.body || '—')}</div></div>
          <div class="notice amber mt-12">${icon('shield', 15)}<div>需人工确认后发送，不会自动私信。</div></div>`,
        footer: `<button class="btn btn-sm" id="copyMsg">${icon('copy', 13)} 复制话术</button><span class="spacer"></span><button class="btn btn-sm btn-primary" id="closeMsg">关闭</button>`,
        onMount(el, close) {
          $('#closeMsg', el).addEventListener('click', close);
          $('#copyMsg', el).addEventListener('click', () => copyText(o.body || ''));
        },
      });
    }));
  }
}
