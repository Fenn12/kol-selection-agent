// 后端接口封装
function qs(params = {}) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, v);
  }
  const s = p.toString();
  return s ? '?' + s : '';
}

async function request(path, opts = {}) {
  const res = await fetch(path, opts);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!res.ok) {
    const msg = (data && typeof data === 'object' && data.error) || text || res.statusText;
    throw new Error(msg);
  }
  return data;
}

const json = (path, body) => request(path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body || {}),
});

export const api = {
  overview: (budget = 8000) => request('/api/overview' + qs({ budget })),
  candidates: (params = {}) => request('/api/candidates' + qs(params)),
  trend: (days = 14) => request('/api/trend' + qs({ days })),
  tasks: (limit = 12) => request('/api/tasks' + qs({ limit })),
  samples: () => request('/api/content/samples'),
  compliance: (text) => json('/api/compliance', { text }),
  strategy: (goal = '起量') => request('/api/strategy' + qs({ goal })),
  queues: () => request('/api/queues'),
  queue: (file) => request('/api/queues/' + encodeURIComponent(file)),
  task: (id) => request('/api/tasks/' + encodeURIComponent(id)),
  rewrite: (body) => json('/api/content/rewrite', body),
  run: (goal, budget, planner) => json('/api/run', { goal, budget, planner }),
  brief: (ids) => request('/api/brief' + qs({ ids: ids.join(',') })),
  outreach: (ids, channel = '私信') => request('/api/outreach' + qs({ ids: ids.join(','), channel })),
  report: (budget = 8000) => request('/api/report' + qs({ budget })),
  notify: (body = { dry_run: true }) => json('/api/notify', body),
  pipeline: (body) => json('/api/pipeline', body),
  llmStatus: () => request('/api/llm/status'),
  llmTest: () => json('/api/llm/test'),
  datasource: () => request('/api/datasource'),
  funnel: (kolId) => request('/api/funnel' + qs({ kol_id: kolId })),
  reports: () => request('/api/reports'),
  last: () => request('/api/last'),
  exportUrl: (ids, budget) => '/api/export' + qs({ ids: ids.join(','), budget }),
  briefUrl: (ids) => '/api/brief' + qs({ ids: ids.join(',') }),
  reportUrl: (budget) => '/api/report' + qs({ budget }),
};
