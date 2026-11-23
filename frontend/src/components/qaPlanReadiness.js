import { localize } from '../locale.js';
const ACTIVE = ['queued', 'running', 'stopping'];
const ACTION = /预处理|降噪|平滑|基线|去噪|鬼峰|裁剪|波段|匹配|候选|结构|解析|提取|训练|模型|转换|转为|转成|合并|拆分|导出|下载|打包|共享|分享|处理|TSHI|TSVD|SG|preprocess|denois|smooth|baseline|match|predict|train|convert|merge|split|export|download|share/i;
const QUESTION = /^(你好|您好|谢谢|好的|好|嗯|hi|hello|ok|下一步该怎么操作[？?]?|帮我解读当前结果|生成运行方案|运行方案|开始|运行|执行|what should I do next[?]?|help me interpret the current results|generate (?:a )?plan|run(?: plan)?)[。！!\s]*$/i;

export function discussionGoal(messages = []) {
  const completed = messages.filter(m => !m.planNotice);
  for (let n = completed.length - 1; n >= 0; n--) {
    const m = completed[n], text = (m.content || '').trim();
    if (m.role !== 'user' || m.incomplete || text.length < 3 || QUESTION.test(text) || !ACTION.test(text)) continue;
    if (/是什么|什么意思|有什么区别|为什么/.test(text) && !/我想|我要|帮我|请.*(?:处理|生成|降噪|匹配)/.test(text)) continue;
    if (/^(what|why|how|explain|describe)\b/i.test(text) && !/please|I want|can you (?:run|apply|process|generate|train)/i.test(text)) continue;
    if (completed.slice(n+1).some(reply => reply.role === 'assistant' && !reply.incomplete && reply.content?.trim())) return text;
  }
  return '';
}

export function planReadiness({ context, contextError, messages = [], consent, busy, status }) {
  if (busy) return localize("正在生成回答或方案，请稍候");
  if (ACTIVE.includes(status)) return localize("请等待当前方案结束，或先停止方案");
  if (!consent) return localize("请先允许 AI 读取附带数据");
  if (contextError) return contextError;
  if (!context) return localize("请先在功能模块选择数据，或上传光谱");
  if (context.locked) return localize("请等待当前模块处理或导入完成");
  const i = context.inputs || {}, files = context.files || [];
  const source = i.source && ['workflow_id', 'run_id', 'dataset_asset_id', 'reference_id', 'source_id', 'reuse_job_id'].some(k => i.source[k] !== undefined && i.source[k] !== null && i.source[k] !== '');
  if (i.batch_id && !i.workflow_ids?.length) return localize("请先勾选需要批量处理的数据");
  const training = context.module === 'spectral-unmixing' && (i.settings?.mode === 'train' || !!i.settings?.name);
  if (training) {
    if (!i.settings?.name?.trim()) return localize("请先填写标准品目标名称");
    if (!i.standards?.length) return localize("请先选择训练用的标准品光谱");
  } else if (!source && !i.dataset_id && !i.workflow_ids?.length && !i.run_ids?.length && !i.export_refs?.length && !i.asset_ids?.length && !files.length) {
    return context.module === 'extra-tools' ? localize("请先选择需要处理的文件") : localize("请先上传、选择或预览需要处理的数据");
  }
  if (context.module === 'spectral-unmixing' && !training && !i.model_id) return localize("请先选择已训练的标准品模型");
  if (!discussionGoal(messages)) return localize("请先发送处理目标并完成讨论，再生成运行方案");
  return '';
}
