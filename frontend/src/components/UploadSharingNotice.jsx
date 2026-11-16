import React from 'react';
import { Link } from 'react-router-dom';
import { usePreferences } from '../i18n';

export default function UploadSharingNotice({ onOpenPolicy }) {
  const { t } = usePreferences();
  return <p className="text-xs leading-relaxed text-gray-500">
    {t('uploadsRetainedNotice')}{' '}
    <Link to="/privacy-policy" onClick={onOpenPolicy} className="text-indigo-400 hover:underline">{t('privacyPolicy')}</Link>
  </p>;
}
