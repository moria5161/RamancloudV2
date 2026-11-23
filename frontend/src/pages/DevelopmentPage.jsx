import React from 'react';
import { Atom, Database, GitBranch } from 'lucide-react';
import { usePreferences } from '../i18n';

const moduleIcons = {
  spectralUnmixing: GitBranch,
  libraryMatching: Database,
  structureGeneration: Atom,
};

export default function DevelopmentPage({ module }) {
  const { t } = usePreferences();
  const Icon = moduleIcons[module] || Atom;
  return <div className="h-full overflow-y-auto px-6 py-10 sm:px-8">
    <header className="flex items-center gap-3 text-gray-200">
      <Icon size={26} className="shrink-0 text-indigo-400" />
      <h1 className="text-2xl font-semibold break-words">{t(module)}</h1>
    </header>
    <p className="mt-8 text-sm text-gray-500" role="status">{t('underDevelopment')}</p>
  </div>;
}
