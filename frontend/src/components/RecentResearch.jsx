import React, { useRef, useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { usePreferences } from '../i18n';
import { researchCategories } from '../data/research';

export default function RecentResearch() {
  const { language, t } = usePreferences();
  const [activeIndex, setActiveIndex] = useState(0);
  const tabs = useRef([]);
  const category = researchCategories[activeIndex];

  const navigateTabs = (event, index) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % researchCategories.length;
    else if (event.key === 'ArrowLeft') next = (index + researchCategories.length - 1) % researchCategories.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = researchCategories.length - 1;
    else return;
    event.preventDefault();
    setActiveIndex(next);
    tabs.current[next]?.focus();
  };

  return (
    <section className="space-y-5" aria-labelledby="recent-research-heading">
      <h2 id="recent-research-heading" className="text-lg font-semibold text-gray-200">{t('recentResearch')}</h2>
      <div role="tablist" aria-label={t('recentResearch')} className="flex flex-wrap gap-2 border-b border-white/10 pb-3">
        {researchCategories.map((item, index) => <button
          key={item.id} id={`research-tab-${item.id}`} role="tab" aria-selected={activeIndex === index}
          aria-controls="research-panel" tabIndex={activeIndex === index ? 0 : -1}
          ref={element => { tabs.current[index] = element; }}
          onClick={() => setActiveIndex(index)} onKeyDown={event => navigateTabs(event, index)}
          className={`px-3 py-2 text-xs rounded-md transition-colors ${activeIndex === index ? 'bg-indigo-500/20 text-indigo-400' : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'}`}>
          {t(item.labelKey)}
        </button>)}
      </div>
      <div id="research-panel" role="tabpanel" aria-labelledby={`research-tab-${category.id}`} tabIndex={0}
        className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {category.papers.map(paper => <article key={paper.url} className="glass rounded-lg border border-white/5 flex flex-col min-w-0">
          <div className="aspect-[4/3] bg-white/90 p-4">
            <img src={`${import.meta.env.BASE_URL}research/${paper.image}`} alt={language === 'zh' ? paper.titleZh : paper.title}
              loading="lazy" decoding="async" className="w-full h-full object-contain" />
          </div>
          <div className="p-5 flex flex-col gap-3 flex-1 min-w-0">
            <h3 className="text-sm font-semibold text-gray-200 leading-relaxed break-words">
              <a href={paper.url} target="_blank" rel="noopener noreferrer" title={paper.title} className="hover:text-indigo-400 transition-colors">
                {language === 'zh' ? paper.titleZh : paper.title}
              </a>
            </h3>
            <p className="text-xs text-gray-500">{paper.citation}</p>
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
              className="mt-auto inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 self-start">
              {t('readPublication')}<ArrowUpRight className="w-3.5 h-3.5" />
            </a>
          </div>
        </article>)}
      </div>
    </section>
  );
}
