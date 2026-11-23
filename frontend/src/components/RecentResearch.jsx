import React, { useRef, useState } from 'react';
import { ArrowDown, ArrowUpRight, BookOpen } from 'lucide-react';
import { usePreferences } from '../i18n';
import { researchCategories } from '../content/research';
import './RecentResearch.css';

const LABELS = {
  structure: ['结构解析', 'Structure elucidation'],
  denoising: ['降噪与分辨率提升', 'Denoising & resolution'],
  classification: ['光谱分类', 'Spectral classification'],
};

export default function RecentResearch() {
  const { language } = usePreferences();
  const txt = (zh, en) => language === 'zh' ? zh : en;
  const [index, setIndex] = useState(0), [expanded, setExpanded] = useState(false);
  const tabs = useRef([]);
  const category = researchCategories[index];
  function choose(next) { setIndex(next); setExpanded(false); }
  function navigate(event, current) {
    let next;
    if (event.key === 'ArrowRight') next = (current + 1) % researchCategories.length;
    else if (event.key === 'ArrowLeft') next = (current + researchCategories.length - 1) % researchCategories.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = researchCategories.length - 1;
    else return;
    event.preventDefault(); choose(next); tabs.current[next]?.focus();
  }
  return <section className="research-section" aria-labelledby="recent-research-heading">
    <div className="learning-section-heading"><div><p className="learning-eyebrow"><BookOpen size={15} />{txt('研究与方法', 'Research & methods')}</p><h2 id="recent-research-heading">{txt('课题组研究进展', 'Research from our group')}</h2></div><a className="learning-text-link" href="https://github.com/moria5161/RamancloudV2/blob/main/frontend/src/data/research.js" target="_blank" rel="noopener noreferrer">{txt('原始 V2 论文列表', 'Original V2 collection')}<ArrowUpRight size={14} /></a></div>
    <div className="research-tabs" role="tablist" aria-label={txt('论文研究方向', 'Research topics')}>{researchCategories.map((item, i) => <button key={item.id} type="button" role="tab" id={`research-tab-${item.id}`} aria-selected={index === i} aria-controls="research-panel" tabIndex={index === i ? 0 : -1} ref={node => { tabs.current[i] = node; }} onClick={() => choose(i)} onKeyDown={event => navigate(event, i)}>{txt(...LABELS[item.id])}<span>{item.papers.length}</span></button>)}</div>
    <div className="research-grid" id="research-panel" role="tabpanel" tabIndex={0} aria-labelledby={`research-tab-${category.id}`}>
      {(expanded ? category.papers : category.papers.slice(0, 4)).map(paper => <article key={paper.url} className="research-card">
        <div className="research-illustration"><img src={`${import.meta.env.BASE_URL}research/${paper.image}`} alt={txt(paper.titleZh, paper.title)} loading="lazy" decoding="async" /></div>
        <div className="research-card-content"><h3><a href={paper.url} target="_blank" rel="noopener noreferrer">{txt(paper.titleZh, paper.title)}</a></h3>{language === 'zh' && <p className="research-original-title">{paper.title}</p>}<p className="research-citation">{paper.citation}</p><a className="learning-text-link" href={paper.url} target="_blank" rel="noopener noreferrer">{txt('阅读原文', 'Read publication')}<ArrowUpRight size={14} /></a></div>
      </article>)}
    </div>
    {category.papers.length > 4 && <button type="button" className="learning-button research-more" aria-expanded={expanded} aria-controls="research-panel" onClick={() => setExpanded(!expanded)}>{expanded ? txt('收起', 'Show fewer') : txt(`查看本类全部 ${category.papers.length} 篇`, `View all ${category.papers.length} papers`)}<ArrowDown size={14} style={expanded ? { transform: 'rotate(180deg)' } : undefined} /></button>}
  </section>;
}
