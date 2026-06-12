import { useTranslation } from 'react-i18next';

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const currentLang = i18n.language === 'en-US' ? 'en-US' : 'zh-CN';

  const setLang = (lang: 'zh-CN' | 'en-US') => {
    i18n.changeLanguage(lang);
  };

  return (
    <div className="flex items-center gap-1 bg-gray-800/50 p-1 rounded-lg">
      <button
        onClick={() => setLang('zh-CN')}
        className={`px-2 py-1 rounded-md text-xs font-medium transition ${
          currentLang === 'zh-CN'
            ? 'bg-[#2D6B5E] text-white'
            : 'text-gray-400 hover:text-gray-200'
        }`}
      >
        中
      </button>
      <button
        onClick={() => setLang('en-US')}
        className={`px-2 py-1 rounded-md text-xs font-medium transition ${
          currentLang === 'en-US'
            ? 'bg-[#2D6B5E] text-white'
            : 'text-gray-400 hover:text-gray-200'
        }`}
      >
        EN
      </button>
    </div>
  );
}
