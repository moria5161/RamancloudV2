export function addPlanToTimeline(messages, plan, restored = false) {
  const entry = { id: `plan:${plan.id}`, kind: 'plan', role: 'assistant', planNotice: true, content: '', plan };
  const previous = messages.map(message => message.kind === 'plan' && message.plan.status === 'draft' && message.plan.id !== plan.id
    ? { ...message, plan: { ...message.plan, status: 'superseded' } } : message);
  if (previous.some(message => message.id === entry.id)) return updateTimelinePlan(previous, plan);
  return restored ? [entry, ...previous] : [...previous, entry];
}

export function updateTimelinePlan(messages, plan) {
  return messages.map(message => message.kind === 'plan' && message.plan.id === plan.id ? { ...message, plan } : message);
}

export function chatHistory(messages) {
  return messages.filter(message => message.kind !== 'plan' && (!message.incomplete || message.truncated));
}
