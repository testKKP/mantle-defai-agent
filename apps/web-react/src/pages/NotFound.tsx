import { Link } from 'react-router-dom';
import { Activity } from 'lucide-react';
import { useTranslation } from 'react-i18next';

export default function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-[#2D6B5E] to-[#4A9B8C] flex items-center justify-center mb-6">
        <Activity className="w-8 h-8 text-white" />
      </div>
      <h1 className="text-7xl font-bold text-white mb-2">404</h1>
      <p className="text-xl text-gray-400 mb-8">{t('notFound.pageNotFound')}</p>
      <Link
        to="/"
        className="px-6 py-2.5 rounded-lg bg-[#111827] border border-gray-700 text-gray-200 text-sm font-medium hover:border-[#4A9B8C] hover:text-[#7ED7C4] transition"
      >
        {t('notFound.backToHome')}
      </Link>
    </div>
  );
}
