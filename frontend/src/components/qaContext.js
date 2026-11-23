import { localize } from '../locale.js';
function activeNode(selector) {
  return [...document.querySelectorAll(selector)].find(node=>!node.closest('[hidden],[aria-hidden="true"]'));
}
export function currentQATask() {
  const record = activeNode('[data-qa-run]');
  if (record?.dataset.qaRun) return { run_id: record.dataset.qaRun };
  const node = activeNode('[data-qa-task]');
  return node?.dataset.qaTask ? { task_id: node.dataset.qaTask, version_id: node.dataset.qaVersion || '' } : null;
}

export const QA_PAGES = {
  'peak-fitting': '分峰拟合',
  'ai-analysis': '智能光谱处理', hyperspectral: '高光谱处理', 'spectral-unmixing': '混合物解析',
  'library-matching': '库匹配', 'structure-generation': '光谱到结构', projects: '项目与数据',
  'analysis-history': '分析记录', 'extra-tools': '附加工具', tutorial: '使用教程', contributors: '贡献人员', account: '个人空间',
};

// Pages explicitly publish only task information. Never collect arbitrary form values or whole DOM text.
export function screenContext(path, withCharts = true) {
  const workspace = document.querySelector('[data-qa-workspace]');
  const slug = path.split('/').filter(Boolean).at(-1);
  let state = {};
  try {
    const raw = activeNode('[data-qa-state]')?.dataset.qaState;
    if (raw && raw.length <= 7000) state = JSON.parse(raw);
  } catch { /* A page without published state still has headings and graph summaries. */ }
  const visible = node => node.getClientRects().length && !node.closest('[hidden],[aria-hidden="true"],dialog:not([open])');
  const labels = selector => [...(workspace?.querySelectorAll(selector) || [])].filter(visible).slice(0, 3).map(n => n.textContent.trim().slice(0, 120));
  const charts = []; let remaining = 64;
  if (withCharts) workspace?.querySelectorAll('.js-plotly-plot').forEach(plot => {
    if (!visible(plot) || charts.length >= 2) return;
    const traces = [];
    (plot.data || []).slice(0, 2).forEach(trace => {
      if (trace.visible === false || trace.visible === 'legendonly') return;
      if (trace.z) {
        traces.push({ name: String(trace.name || '').slice(0, 60), kind: 'heatmap', rows: trace.z.length, columns: trace.z[0]?.length || 0, note: localize("仅矩阵尺寸，不含图像像素或完整矩阵") });
        return;
      }
      if (!trace.x || !trace.y || Array.isArray(trace.y[0])) return;
      const n = Math.min(trace.x.length, trace.y.length), count = Math.min(n, remaining, 32), points = [];
      for (let i = 0; i < count; i++) {
        const index = Math.round(i * (n - 1) / Math.max(1, count - 1)), x = trace.x[index], y = trace.y[index];
        if (typeof x === 'number' && typeof y === 'number' && Number.isFinite(x) && Number.isFinite(y)) points.push([x, y]);
      }
      remaining -= points.length;
      if (points.length) traces.push({ name: String(trace.name || '').slice(0, 60), points, total_points: n });
    });
    if (traces.length) charts.push({ traces });
  });
  return { path, page: localize(QA_PAGES[slug]) || localize("平台页面"),
    observed_at: new Date().toISOString(), state, headings: labels('h1,h2'),
    notices: labels('[role="alert"],[role="status"]'), charts,
    scope: localize("当前平台工作区的结构化状态，不是屏幕图像；未读取其他窗口、密码或任意表单") };
}
