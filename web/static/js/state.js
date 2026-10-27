// 全局状态
export const store = {
  budget: Number(localStorage.getItem('kol.budget') || 8000),
  planner: localStorage.getItem('kol.planner') || 'auto',
  llm: null,
  ds: null,
  overview: null,
};

export function setBudget(v) {
  const n = Number(v) || 8000;
  store.budget = n;
  localStorage.setItem('kol.budget', String(n));
}

export function setPlanner(v) {
  store.planner = v || 'auto';
  localStorage.setItem('kol.planner', store.planner);
}
