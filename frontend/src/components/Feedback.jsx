import React, { useState } from 'react';
import { Github, Globe2, Mail, MapPin, Phone } from 'lucide-react';
import { usePreferences } from '../i18n';
import VisitStatistics from './VisitStatistics';

export default function Feedback() {
  const { language, t } = usePreferences();
  const isZh = language === 'zh';
  const [showVisits, setShowVisits] = useState(false);
  return (
    <section id="feedback" aria-labelledby="feedback-heading" className="border-t border-white/10 pt-8 pb-4 space-y-4">
      <h2 id="feedback-heading" className="text-lg font-semibold text-gray-200">{isZh ? '联系与反馈' : 'Contact & Feedback'}</h2>
      <p className="text-sm text-gray-400">
        {isZh ? '欢迎联系团队开展科研合作，或通过邮件和 GitHub 反馈网站问题与建议。' : 'Contact the team for research collaboration, or share website questions and suggestions by email or on GitHub.'}
      </p>
      <div className="space-y-2 text-sm text-gray-400">
        <p className="flex items-start gap-2">
          <MapPin className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-500" />
          <span>{isZh ? '厦门大学化学系 434 室，厦门 361005，中国' : 'Room 434, Department of Chemistry, Xiamen University, Xiamen 361005, China'}</span>
        </p>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <a href="tel:+865922186532" className="inline-flex items-center gap-2 hover:text-indigo-400 transition-colors">
            <Phone className="w-3.5 h-3.5 shrink-0 text-gray-500" /> +86-592-2186532
          </a>
          <a href="mailto:bren@xmu.edu.cn" className="inline-flex flex-wrap items-center gap-2 hover:text-indigo-400 transition-colors">
            <Mail className="w-3.5 h-3.5 shrink-0 text-gray-500" />
            <span>{isZh ? '科研合作：' : 'Research inquiries:'}</span><span>bren@xmu.edu.cn</span>
          </a>
        </div>
      </div>
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
        <button type="button"
          title={isZh ? '查看全球访问分布' : 'View global visits'}
          aria-label={isZh ? '查看全球访问分布' : 'View global visits'}
          aria-expanded={showVisits}
          aria-controls="feedback-visit-statistics"
          onClick={() => setShowVisits(value => !value)}
          className={`liquid-button inline-flex min-h-9 items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-sm transition-colors ${showVisits ? 'bg-indigo-500/10 text-indigo-400' : 'text-gray-500 hover:bg-white/10 hover:text-indigo-400'}`}>
          <Globe2 className="h-4 w-4 shrink-0" />
          {isZh ? '全球访问分布' : 'Global visits'}
        </button>
        <a href="https://github.com/moria5161/RamancloudV2" target="_blank" rel="noopener noreferrer" title={isZh ? '在 GitHub 查看源代码' : 'View source code on GitHub'}
          className="liquid-button inline-flex min-h-9 items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-sm text-gray-500 hover:text-indigo-400 transition-colors">
          <Github className="w-4 h-4 shrink-0" />
          {isZh ? '源代码' : 'Source code'}
        </a>
        </div>
      </div>
      {showVisits && <div id="feedback-visit-statistics" className="animate-fade-in"><VisitStatistics /></div>}
      <p className="text-xs text-gray-500">
        {t('developedBy')}{' '}<a href="https://bren.xmu.edu.cn" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">Ren Research Group</a>, {isZh ? '厦门大学' : 'Xiamen University'}
      </p>
    </section>
  );
}
