import { formatCount, formatINR, formatPercent } from '../format'

function Card({ label, value, accent }) {
  return (
    <div className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-semibold tabular-nums ${accent ?? 'text-zinc-100'}`}>{value}</p>
    </div>
  )
}

export default function StatsCards({ metrics }) {
  if (!metrics) {
    return (
      <div className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-6 text-sm text-zinc-500">
        Upload a dataset and run reconciliation to see results.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card label="Records Processed" value={formatCount(metrics.total_records)} />
        <Card label="Matched" value={formatCount(metrics.matched_records)} accent="text-emerald-400" />
        <Card label="Exceptions" value={formatCount(metrics.exception_records)} accent="text-amber-400" />
        <Card label="Match Rate" value={formatPercent(metrics.match_rate)} accent="text-cyan-300" />
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">Amount Processed</p>
          <p className="mt-0.5 font-mono text-lg tabular-nums">{formatINR(metrics.total_expected_amount)}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">Amount Reconciled</p>
          <p className="mt-0.5 font-mono text-lg tabular-nums text-emerald-400">
            {formatINR(metrics.reconciled_amount)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">Amount Unresolved</p>
          <p className="mt-0.5 font-mono text-lg tabular-nums text-amber-400">
            {formatINR(metrics.unresolved_amount)}
          </p>
        </div>
      </div>
    </div>
  )
}
