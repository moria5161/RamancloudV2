import React from 'react';
import { Users, Heart, MapPin, Mail, Phone, Github, ExternalLink } from 'lucide-react';
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
      <div className="max-w-3xl mx-auto px-8 py-10 space-y-8 animate-fade-in">
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Heart className="w-6 h-6 text-red-400" />
            <h1 className="text-2xl font-bold text-white">{isZh ? '贡献人员' : 'Contributors'}</h1>
          </div>
          <p className="text-gray-400 text-sm">
            {isZh
              ? 'RamanCloud 由厦门大学 Ren Research Group 开发和维护。感谢所有为本项目做出贡献的成员。'
              : 'RamanCloud is developed and maintained by the Ren Research Group at Xiamen University. We thank everyone who contributed to this project.'}
          </p>
        </div>

        {/* Team */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-4">
          <h2 className="text-lg font-semibold text-gray-200 flex items-center gap-2">
            <Users className="w-4 h-4" /> {isZh ? '团队成员' : 'Team Members'}
          </h2>
          <div className="space-y-3">
            {team.map(({ name, role, link, desc }) => (
              <div key={name} className="flex items-start gap-3 bg-black/20 rounded-lg p-3">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
                  {name.charAt(0)}
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    {link ? (
                      <a href={link} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-gray-200 hover:text-indigo-400 transition-colors flex items-center gap-1">
                        {name} <ExternalLink className="w-2.5 h-2.5" />
                      </a>
                    ) : (
                      <span className="text-sm font-medium text-gray-200">{name}</span>
                    )}
                  </div>
                  <p className="text-xs text-indigo-400">{role}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Mentors */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-3">
          <h2 className="text-lg font-semibold text-gray-200">{isZh ? '导师与顾问' : 'Mentors & Advisors'}</h2>
          <div className="space-y-3">
            {[
              { name: 'Prof. Bin Ren', link: 'https://chem.xmu.edu.cn/en/info/1010/1352.htm' },
              { name: 'Prof. Guokun Liu', link: 'https://mel2.xmu.edu.cn/staff.asp?tid=587' },
              { name: 'Prof. Xiang Wang', link: 'https://chem.xmu.edu.cn/en/info/1010/1815.htm' },
              { name: 'Prof. Hao Ma', link: 'https://www.researchgate.net/profile/Hao-Ma-20' },
            ].map(({ name, link }) => (
              <a key={name} href={link} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 text-sm text-gray-300 hover:text-indigo-400 transition-colors">
                <ExternalLink className="w-3 h-3" /> {name}
              </a>
            ))}
          </div>
          <p className="text-xs text-gray-500 pt-2">
            {isZh ? '特别感谢各位老师在开发过程中提供的宝贵指导与支持。' : 'Special thanks for invaluable guidance and support throughout the development process.'}
          </p>
        </div>

        {/* External Support */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-3">
          <h2 className="text-lg font-semibold text-gray-200">{isZh ? '外部支持' : 'External Support'}</h2>
          <a href="http://www.ikkem.com/" target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm text-gray-300 hover:text-indigo-400 transition-colors">
            <ExternalLink className="w-3 h-3" /> Tan Kah Kee Innovation Laboratory
          </a>
        </div>

        {/* Contact */}
        <div className="glass rounded-xl p-5 border border-white/5 space-y-3">
          <h2 className="text-lg font-semibold text-gray-200">{isZh ? '联系方式' : 'Contact'}</h2>
          <div className="space-y-2 text-sm text-gray-400">
            <div className="flex items-center gap-2"><MapPin className="w-3.5 h-3.5 text-gray-500" /> {isZh ? '厦门大学化学系 434 室，厦门 361005，中国' : 'Room 434, Department of Chemistry, Xiamen University, Xiamen 361005, China'}</div>
            <div className="flex items-center gap-2"><Phone className="w-3.5 h-3.5 text-gray-500" /> +86-592-2186532</div>
            <div className="flex items-center gap-2"><Mail className="w-3.5 h-3.5 text-gray-500" /> bren@xmu.edu.cn</div>
            <a href="https://github.com/moria5161/RamancloudV2" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-indigo-400 hover:text-indigo-300">
              <Github className="w-3.5 h-3.5" /> {isZh ? 'GitHub 仓库' : 'GitHub Repository'}
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
