import React, { useState } from 'react';
import { Bot, SlidersHorizontal } from 'lucide-react';
import { usePreferences } from '../i18n';
import AIChatPanel from './AIChatPanel';

export default function WorkspaceSidePanel({ surface, context, control, onApplyCommand, blocked }) {
  const { t, language } = usePreferences();
  const [tab, setTab] = useState('control');
  return <aside className="workspace-side-panel">
    <div className="workspace-side-tabs" role="tablist" aria-label={language === 'zh' ? '工作区面板' : 'Workspace panel'}>
      <button type="button" role="tab" aria-selected={tab === 'control'} onClick={() => setTab('control')}><SlidersHorizontal size={15} />{t('controls')}</button>
      <button type="button" role="tab" aria-selected={tab === 'assistant'} onClick={() => setTab('assistant')}><Bot size={15} />{language === 'zh' ? 'AI 对话' : 'AI Chat'}</button>
    </div>
    <div role="tabpanel" className="workspace-tab-content" hidden={tab !== 'control'}>{control}</div>
    <div role="tabpanel" className="workspace-tab-content" hidden={tab !== 'assistant'}><AIChatPanel surface={surface} context={context} onApplyCommand={onApplyCommand} blocked={blocked} /></div>
  </aside>;
}
