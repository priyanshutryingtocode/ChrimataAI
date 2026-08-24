import { formatINR, formatPercent, formatSeconds } from '../format'

function Chip({ label, value, tone = 'zinc' }) {
  const tones = {
    zinc: 'bg-zinc-800/60 text-zinc-300 ring-zinc-700',
    green: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/30',
    amber: 'bg-amber-500/10 text-amber-400 ring-amber-500/30',
    red: 'bg-red-500/10 text-red-400 ring-red-500/30',
    cyan: 'bg-cyan-500/10 text-cyan-300 ring-cyan-500/30',
  }
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ${tones[tone]}`}>
      {label}: {value}
    </span>
  )
}

export default function MetricsBar({ metrics }) {
  if (!metrics) return null

  const evaluated = metrics.evaluated_against_ground_truth
  const workflow = metrics.workflow
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-4">
      <Chip label="Throughput" value={`${Math.round(metrics.throughput_per_second)} rec/s`} tone="cyan" />
      <Chip label="Processing time" value={formatSeconds(metrics.elapsed_seconds)} />
      {evaluated ? (
        <>
          <Chip label="Precision" value={formatPercent(metrics.matching_precision)} tone="green" />
          <Chip label="Exception recall" value={formatPercent(metrics.exception_recall)} tone="green" />
          <Chip label="False-match rate" value={formatPercent(metrics.false_match_rate)} tone="red" />
          <span className="text-[11px] text-zinc-600 ml-1">evaluated against ground truth</span>
        </>
      ) : (
        <span className="text-[11px] text-zinc-600">
          No ground truth provided — precision/recall not evaluated
        </span>
      )}
      {workflow && workflow.total_exceptions > 0 && (
        <>
          <span className="mx-1 h-4 w-px bg-zinc-700" />
          <Chip
            label="Workflow resolved"
            value={`${workflow.workflow_resolved_exceptions}/${workflow.total_exceptions} (${formatPercent(workflow.workflow_resolution_rate, 1)})`}
            tone="green"
          />
          <Chip
            label="Financially reconciled"
            value={`${formatINR(workflow.amount_financially_reconciled)} of ${formatINR(workflow.total_exception_amount)} (${formatPercent(workflow.financial_resolution_rate, 1)})`}
            tone={workflow.amount_financially_reconciled > 0 ? 'green' : 'amber'}
          />
          <Chip label="Outstanding" value={formatINR(workflow.amount_outstanding)} tone="amber" />
          {workflow.proposed_exceptions > 0 && (
            <Chip label="Pending decisions" value={String(workflow.proposed_exceptions)} tone="cyan" />
          )}
        </>
      )}
    </div>
  )
}
