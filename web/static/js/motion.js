// 动效：数字滚动、表格错峰、图表进入视口、Hero 视差
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function initMotion(root) {
  if (!root || reduced()) return;
  markRows(root);
  animateCounts(root);
  observeCharts(root);
  initHeroParallax(root);
}

function markRows(root) {
  root.querySelectorAll('tbody tr').forEach((tr, i) => {
    if (tr.dataset.motion) return;
    tr.dataset.motion = '1';
    tr.style.setProperty('--ri', String(Math.min(i, 12)));
  });
}

function animateCounts(root) {
  const targets = root.querySelectorAll('.kpi-num, .chart-stat .v');
  targets.forEach((el) => {
    if (el.dataset.counted) return;
    el.dataset.counted = '1';
    const raw = el.textContent.trim();
    if (!raw || raw.includes('/')) return;
    const m = raw.match(/(-?\d[\d,]*\.?\d*)/);
    if (!m) return;
    const token = m[1];
    const value = Number(token.replace(/,/g, ''));
    if (!Number.isFinite(value) || Math.abs(value) < 0.01) return;

    const decimals = (token.split('.')[1] || '').length;
    const useComma = token.includes(',');
    const pre = raw.slice(0, m.index);
    const post = raw.slice(m.index + token.length);
    const fmt = (v) => {
      if (useComma) {
        return v.toLocaleString('zh-CN', {
          minimumFractionDigits: decimals, maximumFractionDigits: decimals,
        });
      }
      return v.toFixed(decimals);
    };

    const dur = 720;
    const t0 = performance.now();
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = pre + fmt(value * eased) + post;
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = pre + token + post;
    };
    el.textContent = pre + fmt(0) + post;
    requestAnimationFrame(tick);
  });
}

let io = null;
function observeCharts(root) {
  if (!('IntersectionObserver' in window)) {
    root.querySelectorAll('.chart-wrap, .donut-wrap').forEach((el) => el.classList.add('chart-in'));
    return;
  }
  if (!io) {
    io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('chart-in');
        io.unobserve(entry.target);
      });
    }, { threshold: 0.15 });
  }
  root.querySelectorAll('.chart-wrap, .donut-wrap').forEach((el) => {
    if (el.classList.contains('chart-in')) return;
    io.observe(el);
  });
}

function initHeroParallax(root) {
  const hero = root.querySelector('.hero');
  const art = hero && hero.querySelector('.hero-art');
  if (!hero || !art || !window.matchMedia('(pointer: fine)').matches) return;
  if (hero.dataset.parallax) return;
  hero.dataset.parallax = '1';
  hero.addEventListener('pointermove', (e) => {
    const r = hero.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    art.style.setProperty('--px', (x * 14).toFixed(1) + 'px');
    art.style.setProperty('--py', (y * 10).toFixed(1) + 'px');
  });
  hero.addEventListener('pointerleave', () => {
    art.style.setProperty('--px', '0px');
    art.style.setProperty('--py', '0px');
  });
}
