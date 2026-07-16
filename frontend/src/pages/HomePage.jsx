import React from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, ArrowRight, Microscope, Cpu, Zap, TrendingUp, BookOpen, Github, Mail } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function HomePage() {
  const { t } = usePreferences();
  return (
    <div className="home-page h-full overflow-y-auto">
      <div className="max-w-5xl mx-auto px-8 py-12 space-y-12 animate-fade-in">
        {/* Hero */}
        <div className="text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-medium">
            <Sparkles className="w-3 h-3" />
            {t('nextGenPlatform')}
          </div>
          <h1 className="text-4xl font-bold text-white tracking-tight">
            RamanCloud
          </h1>
          <p className="text-lg text-gray-400 max-w-xl mx-auto">
            {t('heroSubtitle')}
          </p>
          <div className="flex gap-3 justify-center pt-2">
            <Link to="/spectral" className="liquid-button flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-sm font-medium hover:from-indigo-500 hover:to-purple-500 transition-all shadow-lg shadow-indigo-500/20">
              {t('getStarted')}
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link to="/tutorial" className="liquid-button flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-gray-300 text-sm font-medium hover:bg-white/10 border border-white/5 transition-all">
              <BookOpen className="w-4 h-4" />
              {t('tutorial')}
            </Link>
          </div>
        </div>

        {/* Feature cards */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { icon: Cpu, title: t('smartPipeline'), desc: t('smartPipelineDesc'), color: 'indigo' },
            { icon: TrendingUp, title: t('realTimeViz'), desc: t('realTimeVizDesc'), color: 'emerald' },
            { icon: Zap, title: t('algorithms'), desc: t('algorithmsDesc'), color: 'amber' },
          ].map(({ icon: Icon, title, desc, color }) => (
            <div key={title} className="glass liquid-card rounded-xl p-5 border border-white/5 hover:border-white/10 transition-all">
              <div className={`w-10 h-10 rounded-xl liquid-icon liquid-icon-${color} flex items-center justify-center mb-3`}>
                <Icon className="w-5 h-5" />
              </div>
              <h3 className="text-sm font-semibold text-gray-200 mb-1.5">{title}</h3>
              <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>

        {/* Processing modules */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-200">{t('processingModules')}</h2>
          <div className="grid grid-cols-2 gap-4">
            <Link to="/spectral" className="glass liquid-card rounded-xl p-5 border border-white/5 hover:border-indigo-500/30 transition-all group">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-200">{t('spectralProcessing')}</h3>
                  <p className="text-[10px] text-gray-500">{t('singleSpectrum')}</p>
                </div>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed">
                {t('spectralDesc')}
              </p>
            </Link>

            <Link to="/hyperspectral" className="glass liquid-card rounded-xl p-5 border border-white/5 hover:border-indigo-500/30 transition-all group">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                  <Microscope className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-200">{t('hyperspectralProcessing')}</h3>
                  <p className="text-[10px] text-gray-500">{t('imagingTimeSeries')}</p>
                </div>
              </div>
              <p className="text-xs text-gray-500 leading-relaxed">
                {t('hyperspectralDesc')}
              </p>
            </Link>
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-white/5 pt-8 pb-4">
          <div className="flex items-center justify-between">
            <div className="text-xs text-gray-600">
              {t('developedBy')} <a href="https://bren.xmu.edu.cn" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300">Ren Research Group</a>, Xiamen University
            </div>
            <div className="flex items-center gap-4">
              <a href="mailto:xinyulu@stu.xmu.edu.cn" className="text-gray-600 hover:text-gray-400 transition-colors">
                <Mail className="w-4 h-4" />
              </a>
              <a href="https://github.com/moria5161/RamancloudV2" target="_blank" rel="noopener noreferrer" className="text-gray-600 hover:text-gray-400 transition-colors">
                <Github className="w-4 h-4" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
