import { useLang } from '../lib/i18n'

export type OriginKind = 'code' | 'model' | 'person'

/** Who made what the audience reads (D66): code computes, the language model only phrases, a person decides
 * (CLAUDE.md rule 1). `model` only where the data says so: an action's or a report's `wording`, or the
 * Investigator's claims and conclusion, which have no template (Solution Plan §8). */
export default function Origin({ kind }: { kind: OriginKind }) {
  const { t } = useLang()
  return (
    <span className={`origin origin-${kind}`} title={t(`origin.${kind}.tip`)}>
      {t(`origin.${kind}`)}
    </span>
  )
}
