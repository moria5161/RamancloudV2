import React from 'react';
import { Users, ExternalLink } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function Contributors() {
  const { language } = usePreferences();
  const isZh = language === 'zh';
  const team = [
    {
      name: 'Nannan Zhang',
      role: isZh ? '核心开发成员' : 'Core Developer',
      link: 'https://moria5161.github.io/',
      desc: isZh ? '核心功能开发与项目管理' : 'Core functionality and project management',
    },
    {
      name: 'Xinyu Lu',
      role: isZh ? '核心开发成员' : 'Core Developer',
      link: 'https://x1nyulu.github.io/',
      desc: isZh ? '核心功能开发与项目管理' : 'Core functionality and project management',
    },
    {
      name: 'Zhengyan Pan',
      role: isZh ? '部署与安全维护' : 'Deployment & Security',
      link: null,
      desc: isZh ? '项目部署管理与安全维护' : 'Project deployment management and security maintenance',
    },
  ];

  return (
    <div className="h-full overflow-y-auto">
      <article className="max-w-4xl mx-auto px-4 py-10 sm:px-8 space-y-8 animate-fade-in">
        <header className="space-y-3">
          <div className="flex items-center gap-3">
            <Users className="w-6 h-6 shrink-0 text-indigo-400" />
            <h1 className="text-2xl font-bold text-white">{isZh ? '贡献人员' : 'Contributors'}</h1>
          </div>
          <p className="text-gray-400 text-sm leading-relaxed">
            {isZh
              ? 'RamanCloud 由厦门大学 Ren Research Group 开发和维护。感谢所有为本项目做出贡献的成员。'
              : 'RamanCloud is developed and maintained by the Ren Research Group at Xiamen University. We thank everyone who contributed to this project.'}
          </p>
        </header>

        {/* Team */}
        <section aria-labelledby="team-heading" className="space-y-5">
          <h2 id="team-heading" className="text-lg font-semibold text-gray-200 flex items-center gap-2">
            <Users className="w-4 h-4 shrink-0" /> {isZh ? '团队成员' : 'Team Members'}
          </h2>
          <ul className="space-y-6">
            {team.map(({ name, role, link, desc }) => (
              <li key={name}>
                <div className="min-w-0">
                  <h3 className="text-base font-medium text-gray-200">
                    {link ? (
                      <a href={link} target="_blank" rel="noopener noreferrer" className="hover:text-indigo-400 transition-colors inline-flex items-center gap-1">
                        {name} <ExternalLink className="w-2.5 h-2.5 shrink-0" />
                      </a>
                    ) : (
                      <span>{name}</span>
                    )}
                  </h3>
                  <p className="text-xs font-medium text-indigo-400 mt-1">{role}</p>
                  <p className="text-sm leading-relaxed text-gray-400 mt-1">{desc}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Mentors */}
        <section aria-labelledby="mentors-heading" className="border-t pt-8 space-y-4" style={{ borderColor: 'var(--rc-hairline)' }}>
          <h2 id="mentors-heading" className="text-lg font-semibold text-gray-200">{isZh ? '导师与顾问' : 'Mentors & Advisors'}</h2>
          <div className="space-y-3">
            {[
              { name: 'Prof. Bin Ren', link: 'https://chem.xmu.edu.cn/en/info/1010/1352.htm' },
              { name: 'Prof. Guokun Liu', link: 'https://mel2.xmu.edu.cn/staff.asp?tid=587' },
              { name: 'Prof. Hao Ma', link: 'https://www.researchgate.net/profile/Hao-Ma-20' },
              { name: 'Prof. Xiang Wang', link: 'https://chem.xmu.edu.cn/en/info/1010/1815.htm' },
            ].map(({ name, link }) => (
              <a key={name} href={link} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-base font-medium text-gray-300 hover:text-indigo-400 transition-colors">
                {name} <ExternalLink className="w-2.5 h-2.5 shrink-0" />
              </a>
            ))}
          </div>
          <p className="text-sm leading-relaxed text-gray-400">
            {isZh ? '特别感谢各位老师在开发过程中提供的宝贵指导与支持。' : 'Special thanks for invaluable guidance and support throughout the development process.'}
          </p>
        </section>

        {/* External Support */}
        <section aria-labelledby="support-heading" className="border-t pt-8 space-y-4" style={{ borderColor: 'var(--rc-hairline)' }}>
          <h2 id="support-heading" className="text-lg font-semibold text-gray-200">{isZh ? '外部支持' : 'External Support'}</h2>
          <a href="http://www.ikkem.com/" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm text-gray-300 hover:text-indigo-400 transition-colors">
            <ExternalLink className="w-3 h-3" /> Tan Kah Kee Innovation Laboratory
          </a>
        </section>

      </article>
    </div>
  );
}
