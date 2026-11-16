import React from 'react';
import { Mail, ShieldCheck } from 'lucide-react';
import { usePreferences } from '../i18n';

export default function PrivacyPolicy() {
  const { language, t } = usePreferences();
  const isZh = language === 'zh';
  const sections = [
    {
      id: 'information',
      title: isZh ? '收集的信息' : 'Information Collected',
      paragraphs: [isZh
        ? '我们处理您上传的光谱、成像、时间序列或分子结构文件，以及完成相应功能所需的参数。原文件归档同时记录文件名、大小、校验值、上传时间和来源模块。'
        : 'We process uploaded spectra, imaging, time-series or molecular structure files and the parameters needed for the requested functions. Original-file archives also record filenames, sizes, checksums, upload times and source modules.',
      isZh
        ? '网站记录页面访问和匿名会话统计，并根据访问请求的 IP 推断国家或地区。访问统计不保存原始 IP、精确位置、文件名或光谱数据；安全与运维日志可能记录访问 IP 和请求信息。'
        : 'The website records pageviews and anonymous session statistics, using request IP addresses to infer countries or regions. Visit statistics do not retain raw IP addresses, precise locations, filenames or spectral data. Security and operational logs may record request IP addresses and request information.'],
    },
    {
      id: 'use',
      title: isZh ? '信息用途' : 'How Information Is Used',
      paragraphs: [isZh
        ? '数据用于提供处理与预测服务、改善用户体验、优化网站和算法，以及维护平台安全。未经明确同意，我们不会为营销目的出售或分享用户数据。'
        : 'Data is used to provide processing and prediction services, improve the user experience, optimize the website and algorithms, and maintain platform security. We do not sell or share user data for marketing purposes without explicit consent.'],
    },
    {
      id: 'originals',
      title: isZh ? '原始上传文件' : 'Original Uploads',
      paragraphs: [isZh
        ? '单光谱、高光谱和附加工具模块默认将上传的原始文件逐字节保存到私有归档，包括批量上传的每一个文件，以及文件中原有的空间或时间坐标。原文件保留至管理员删除。'
        : 'Spectral Processing, Hyperspectral Processing and Extra Tools retain original uploads byte-for-byte in a private archive by default. This includes every file in a batch and any spatial or time coordinates in the files. Originals are retained until deleted by administrators.',
      isZh
        ? '谱构解析模块在使用上传的 XYZ 文件提交光谱预测时保存该原文件；仅加载构象预览不会额外归档。示例选择、SMILES 和绘图输入、处理与预测结果不作为原始上传文件归档。高光谱处理缓存会在闲置约 30 分钟后清理，这不代表已归档原文件被删除。'
        : 'Spectrum-Structure Elucidation retains an uploaded XYZ original when it is submitted for spectrum prediction; loading a conformer preview does not create an additional archive. Example selections, SMILES and drawn inputs, and processed or predicted results are not archived as original uploads. Hyperspectral processing caches expire after about 30 minutes of inactivity; this does not delete archived originals.',
      isZh
        ? '上传前请确认您有权提供这些数据。请勿上传保密或含个人身份信息的数据。'
        : 'Before uploading, ensure that you are authorized to provide the data. Do not upload confidential or personally identifiable data.'],
    },
    {
      id: 'browser',
      title: isZh ? '浏览器存储与访问统计' : 'Browser Storage and Visit Statistics',
      paragraphs: [isZh
        ? '浏览器本地保存语言和外观偏好，工作区使用必要的会话 Cookie 保护请求。匿名访问统计会话在停止活动 30 分钟后过期，不等同于独立用户人数。访问统计尊重浏览器的 Do Not Track 和 Global Privacy Control 设置；这些设置不改变原始上传文件的归档规则。'
        : 'Language and appearance preferences are stored locally in your browser. Essential workspace session cookies protect requests. Anonymous analytics sessions expire after 30 minutes of inactivity and do not represent unique people. Visit statistics respect Do Not Track and Global Privacy Control; these settings do not change the original-upload archive policy.'],
    },
    {
      id: 'security',
      title: isZh ? '数据安全' : 'Data Security',
      paragraphs: [isZh
        ? '我们使用加密传输、访问控制和私有归档等措施保护数据。互联网传输和存储仍存在风险，无法保证绝对安全。'
        : 'We use measures including encrypted transport, access controls and private archives to protect data. Internet transmission and storage still carry risks; absolute security cannot be guaranteed.'],
    },
    {
      id: 'links',
      title: isZh ? '第三方链接' : 'Third-Party Links',
      paragraphs: [isZh
        ? '网站可能包含第三方网站的链接。第三方网站适用其各自的隐私政策，其数据处理行为不由我们控制。访问前请阅读相应政策。'
        : 'The website may contain links to third-party sites. Those sites have their own privacy policies, and we do not control their data practices. Please review their policies before use.'],
    },
    {
      id: 'changes',
      title: isZh ? '政策更新' : 'Changes to This Policy',
      paragraphs: [isZh
        ? '隐私政策可能随服务调整而更新，更新内容将在本页面公布。请定期查阅。'
        : 'This policy may be updated as the service changes. Updates will be published on this page; please review it periodically.'],
    },
  ];

  return <div className="h-full overflow-y-auto">
    <article className="mx-auto max-w-4xl px-4 py-10 sm:px-8 animate-fade-in">
      <header className="mb-8 space-y-3">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 shrink-0 text-indigo-400" />
          <h1 className="text-2xl font-bold text-white">{t('privacyPolicy')}</h1>
        </div>
        <p className="text-sm leading-relaxed text-gray-400">{isZh
          ? '本政策说明 RamanCloud 如何处理访问记录和您提供的数据。上传文件前，请阅读原始文件的保存与使用规则。'
          : 'This policy explains how RamanCloud handles visit records and the data you provide. Please review the retention and use of original files before uploading.'}</p>
      </header>
      <div className="divide-y divide-white/10">
        {sections.map(section => <section key={section.id} aria-labelledby={`privacy-${section.id}`} className="py-5 first:pt-0 space-y-3">
          <h2 id={`privacy-${section.id}`} className="text-base font-semibold text-gray-200">{section.title}</h2>
          {section.paragraphs.map((text, index) => <p key={index} className="text-sm leading-relaxed text-gray-400">{text}</p>)}
        </section>)}
        <section className="py-5 space-y-3">
          <h2 className="text-base font-semibold text-gray-200">{isZh ? '联系我们' : 'Contact'}</h2>
          <p className="text-sm leading-relaxed text-gray-400">{isZh
            ? '如有隐私问题或希望请求删除已上传文件，请联系 Ren Research Group，提供文件名和大致上传时间，不要再次发送保密原始数据。'
            : 'For privacy questions or requests to delete uploaded files, contact Ren Research Group with the filename and approximate upload time. Do not resend confidential originals.'}</p>
          <a href="mailto:bren@xmu.edu.cn" className="inline-flex items-center gap-2 text-sm text-indigo-400 hover:underline"><Mail className="h-4 w-4" />bren@xmu.edu.cn</a>
        </section>
      </div>
    </article>
  </div>;
}
