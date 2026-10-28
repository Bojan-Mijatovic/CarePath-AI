import { type Lang, useLang } from '../lib/i18n'

/** IT | EN switch (delivery plan D30); the demo runs in Italian. */
export default function LangSwitch({ onChange }: { onChange: (lang: Lang) => void }) {
  const { lang, t } = useLang()
  return (
    <div className="lang" role="group" aria-label={t('top.language')}>
      {(['it', 'en'] as const).map((l) => (
        <button key={l} type="button" aria-pressed={lang === l} onClick={() => onChange(l)}>
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
