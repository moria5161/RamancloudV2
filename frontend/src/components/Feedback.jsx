import React, { useState } from 'react';
import { Github, Globe2, Mail, MessageSquare } from 'lucide-react';
import { usePreferences } from '../i18n';
import VisitStatistics from './VisitStatistics';

export default function Feedback() {
  const { language, t } = usePreferences();
  const isZh = language === 'zh';
  const [showVisits, setShowVisits] = useState(false);
  return (
    <section id="feedback" aria-labelledby="feedback-heading" className="border-t border-white/10 pt-8 pb-4 space-y-4">
      <h2 id="feedback-heading" className="text-lg font-semibold text-gray-200">{isZh ? '反馈' : 'Feedback'}</h2>
      <p className="text-sm text-gray-400">
        {isZh ? '遇到问题或有建议？欢迎通过邮件联系我们，或在 GitHub 提交反馈。' : 'Questions, issues, or suggestions? Contact us by email or share your feedback on GitHub.'}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <a href="mailto:xinyulu@stu.xmu.edu.cn" className="liquid-button inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-sm text-indigo-400">
          <Mail className="w-4 h-4" />{isZh ? '邮件联系' : 'Email us'}
        </a>
        <a href="https://github.com/moria5161/RamancloudV2/issues/new" target="_blank" rel="noopener noreferrer"
          className="liquid-button inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-sm text-indigo-400">
          <MessageSquare className="w-4 h-4" />{isZh ? '提交反馈' : 'Report an issue'}
        </a>
        <a href="https://github.com/moria5161/RamancloudV2" target="_blank" rel="noopener noreferrer" title="GitHub" aria-label="GitHub"
          className="inline-flex items-center justify-center w-9 h-9 text-gray-500 hover:text-indigo-400 transition-colors">
          <Github className="w-4 h-4" />
        </a>
        <button type="button"
          title={isZh ? '查看全球访问分布' : 'View global visits'}
          aria-label={isZh ? '查看全球访问分布' : 'View global visits'}
          aria-expanded={showVisits}
          aria-controls="feedback-visit-statistics"
          onClick={() => setShowVisits(value => !value)}
          className={`inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors ${showVisits ? 'bg-indigo-500/10 text-indigo-400' : 'text-gray-500 hover:bg-white/10 hover:text-indigo-400'}`}>
          <Globe2 className="h-4 w-4" />
        </button>
      </div>
      {showVisits && <div id="feedback-visit-statistics" className="animate-fade-in"><VisitStatistics /></div>}
      <p className="text-xs text-gray-500">
        {t('developedBy')}{' '}<a href="https://bren.xmu.edu.cn" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">Ren Research Group</a>, {isZh ? '厦门大学' : 'Xiamen University'}
      </p>
    </section>
  );
}
