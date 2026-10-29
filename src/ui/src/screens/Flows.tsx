import { type Pathway, type PathwayStatus, type SankeyRow, useApi } from '../lib/api'
import { formatNumber, type Key, useLang } from '../lib/i18n'

const STATUSES: PathwayStatus[] = ['on_track', 'due_soon', 'overdue', 'dropped']
const W = 900
const H = 440
const TOP = 34 // column headings
const NODE_W = 14
const GAP = 10
const X_LEFT = 230
const X_RIGHT = W - 230 - NODE_W

type Node = { key: string | null; patients: number; y: number; h: number }

/** Nodes of one column in pathway order, then "none", stacked from the top with the same scale on both sides. */
function column(rows: SankeyRow[], side: 'from_step' | 'to_step', order: (string | null)[], scale: number): Map<string | null, Node> {
  const nodes = new Map<string | null, Node>()
  let y = TOP
  for (const key of order) {
    const patients = rows.filter((r) => r[side] === key).reduce((s, r) => s + r.patients, 0)
    if (!patients) continue
    nodes.set(key, { key, patients, y, h: patients * scale })
    y += patients * scale + GAP
  }
  return nodes
}

/** Percorsi (delivery plan 2.16): where patients stand in the pathway, as two columns (SPEC §5.2: a periodic
 * step leads to itself, so last step done and next step are separate columns, not a cycle). */
export default function Flows({ day, pathwayId }: { day: number | null; pathwayId: string | null }) {
  const { lang, t } = useLang()
  const { data: rows, error } = useApi<SankeyRow[]>(pathwayId ? `/api/sankey?pathway_id=${pathwayId}` : null, day)
  const { data: pathway, error: pathwayError } = useApi<Pathway>(pathwayId ? `/api/pathways/${pathwayId}` : null)
  if (error || pathwayError) return <p className="placeholder">{t('error.load', { detail: error ?? pathwayError ?? '' })}</p>
  if (!rows || !pathway) return <p className="placeholder">{t('loading')}</p>

  const labels = new Map(pathway.steps.map((s) => [s.id, s.label[lang]]))
  const name = (step: string | null) => (step === null ? t('sankey.none') : (labels.get(step) ?? step))
  const order: (string | null)[] = [...pathway.steps.map((s) => s.id), null]
  const total = rows.reduce((s, r) => s + r.patients, 0)
  const most = Math.max(...(['from_step', 'to_step'] as const).map((side) => new Set(rows.map((r) => r[side])).size))
  const scale = total ? (H - TOP - GAP * (most - 1)) / total : 0
  const left = column(rows, 'from_step', order, scale)
  const right = column(rows, 'to_step', order, scale)
  const rank = (step: string | null) => order.indexOf(step)

  // Each link leaves its left node and enters its right node at the next free offset.
  const links = rows
    .filter((r) => r.patients > 0)
    .sort((a, b) => rank(a.from_step) - rank(b.from_step) || rank(a.to_step) - rank(b.to_step) || STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status))
  const outY = new Map<SankeyRow, number>()
  const used = new Map<string | null, number>()
  for (const r of links) {
    const n = left.get(r.from_step)!
    outY.set(r, n.y + (used.get(r.from_step) ?? 0))
    used.set(r.from_step, (used.get(r.from_step) ?? 0) + r.patients * scale)
  }
  const inY = new Map<SankeyRow, number>()
  used.clear()
  for (const r of [...links].sort((a, b) => rank(a.to_step) - rank(b.to_step) || rank(a.from_step) - rank(b.from_step) || STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status))) {
    const n = right.get(r.to_step)!
    inY.set(r, n.y + (used.get(r.to_step) ?? 0))
    used.set(r.to_step, (used.get(r.to_step) ?? 0) + r.patients * scale)
  }
  const n = (x: number) => formatNumber(lang, x)
  const x0 = X_LEFT + NODE_W
  const mid = (x0 + X_RIGHT) / 2

  return (
    <div className="flows">
      <p className="lead">{t('sankey.intro')}</p>
      <section className="panel">
        <svg className="sankey" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('sankey.label')}>
          <text x={X_LEFT + NODE_W} y={16} textAnchor="end" className="sankey-head">{t('sankey.from')}</text>
          <text x={X_RIGHT} y={16} className="sankey-head">{t('sankey.to')}</text>
          {links.map((r) => {
            const h = Math.max(r.patients * scale, 0.5)
            const a = outY.get(r)!
            const b = inY.get(r)!
            return (
              <path
                key={`${r.from_step}-${r.to_step}-${r.status}`}
                className={`link status-${r.status}`}
                d={`M${x0},${a}C${mid},${a} ${mid},${b} ${X_RIGHT},${b}L${X_RIGHT},${b + h}C${mid},${b + h} ${mid},${a + h} ${x0},${a + h}Z`}
              >
                <title>{t('sankey.link', { from: name(r.from_step), to: name(r.to_step), status: t(`status.${r.status}` as Key), patients: n(r.patients) })}</title>
              </path>
            )
          })}
          {[...left.values()].map((node) => (
            <g key={`l-${node.key}`}>
              <rect x={X_LEFT} y={node.y} width={NODE_W} height={Math.max(node.h, 1)} className="node" />
              <text x={X_LEFT - 8} y={node.y + node.h / 2} textAnchor="end" dominantBaseline="middle">
                {name(node.key)} · {n(node.patients)}
              </text>
            </g>
          ))}
          {[...right.values()].map((node) => (
            <g key={`r-${node.key}`}>
              <rect x={X_RIGHT} y={node.y} width={NODE_W} height={Math.max(node.h, 1)} className="node" />
              <text x={X_RIGHT + NODE_W + 8} y={node.y + node.h / 2} dominantBaseline="middle">
                {name(node.key)} · {n(node.patients)}
              </text>
            </g>
          ))}
        </svg>
        <div className="legend">
          {STATUSES.map((s) => (
            <span key={s} className="legend-item">
              <span className={`swatch status-${s}`} aria-hidden="true" />
              {t(`status.${s}` as Key)} · {n(rows.filter((r) => r.status === s).reduce((sum, r) => sum + r.patients, 0))}
            </span>
          ))}
        </div>
      </section>
    </div>
  )
}
