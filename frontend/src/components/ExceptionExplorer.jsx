import { formatINR } from '../format'
import { StatusPill, TypeBadge } from './primitives'

export default function ExceptionExplorer({ result, onClose }) {
  if (!result) return null
  const confidencePct = Math.round((result.confidence ?? 0) * 100)

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <aside className="relative h-full w-full max-w-md overflow-y-auto bg-zinc-900 ring-1 ring-zinc-700 shadow-2xl p-6 space-y-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="font-mono text-lg font-semibold text-zinc-100">{result.transaction_id}</p>
            <div className="mt-1 flex items-center gap-2">
              <StatusPill status={result.status} />
              <TypeBadge type={result.exception_type} />
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700"
          >
            Close ✕
          </button>
        </div>

        <section className="rounded-lg bg-zinc-950 ring-1 ring-zinc-800 p-4">
          <div className="grid grid-cols-2 gap-3 font-mono text-sm tabular-nums">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Expected</p>
              <p className="text-zinc-200">{formatINR(result.expected_amount)}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Actual</p>
              <p className="text-zinc-200">{formatINR(result.actual_amount)}</p>
            </div>
          </div>
          <div className="mt-3 border-t border-zinc-800 pt-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">Variance</p>
            <p className={`font-mono text-2xl font-semibold tabular-nums ${result.variance !== 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {formatINR(result.variance)}
            </p>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className="text-xs uppercase tracking-wide text-zinc-500">Known deductions</h3>
          <div className="flex gap-4 font-mono text-xs text-zinc-300">
            <span>Fee: {formatINR(result.fee)}</span>
            <span>Tax: {formatINR(result.tax)}</span>
          </div>
        </section>

        <section>
          <h3 className="text-xs uppercase tracking-wide text-zinc-500">Engine reason</h3>
          <p className="mt-1 rounded-lg bg-zinc-950 ring-1 ring-zinc-800 p-3 text-xs leading-relaxed text-zinc-300">
            {result.reason || '—'}
          </p>
        </section>

        {result.related_records?.length > 0 && (
          <section>
            <h3 className="text-xs uppercase tracking-wide text-zinc-500">Related records</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {result.related_records.map((id) => (
                <span key={id} className="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-cyan-300">
                  {id}
                </span>
              ))}
            </div>
          </section>
        )}

        <section>
          <h3 className="text-xs uppercase tracking-wide text-zinc-500">
            Confidence · {confidencePct}% · matched via {result.match_method.replace('_', ' ')}
          </h3>
          <div className="mt-1.5 h-1.5 w-full rounded-full bg-zinc-800">
            <div className="h-full rounded-full bg-cyan-400" style={{ width: `${confidencePct}%` }} />
          </div>
        </section>

        {result.recommendation && (
          <section className="rounded-lg border-l-4 border-amber-500/70 bg-amber-500/10 p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-amber-400">Recommended action</h3>
            <p className="mt-1 text-xs leading-relaxed text-amber-100">{result.recommendation}</p>
          </section>
        )}
      </aside>
    </div>
  )
}
