import { useEffect, useState } from 'react'
import * as api from '../api'
import { formatINR } from '../format'
import { StatusPill, TypeBadge } from './primitives'

function WorkflowBadge({ status }) {
  const tones = {
    OPEN: 'bg-zinc-700/40 text-zinc-400 ring-zinc-600',
    PROPOSED: 'bg-cyan-500/10 text-cyan-300 ring-cyan-500/30',
    RESOLVED: 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/30',
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${tones[status] ?? tones.OPEN}`}>
      WORKFLOW {status}
    </span>
  )
}

function FinancialBadge({ status, outstanding }) {
  const reconciled = status === 'RECONCILED'
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${
        reconciled ? 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/30' : 'bg-amber-500/10 text-amber-400 ring-amber-500/30'
      }`}
    >
      {reconciled ? 'FINANCIALLY RECONCILED' : `FINANCIAL OUTSTANDING${outstanding ? ` · ${formatINR(outstanding)}` : ''}`}
    </span>
  )
}

function EvidenceViewer({ evidence }) {
  if (!evidence || !evidence.exception) return null
  const schedule = evidence.fee_tax_schedule_check
  const context = evidence.batch_context
  return (
    <details className="rounded-lg bg-zinc-950 ring-1 ring-zinc-800 p-3">
      <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Evidence pack (immutable snapshot)
      </summary>
      <div className="mt-2 space-y-2 text-[11px] text-zinc-400">
        <p>
          Variance percentile within type: <span className="font-mono text-cyan-300">{context?.variance_percentile_within_type}%</span> ·
          same-type exceptions: <span className="font-mono text-cyan-300">{context?.same_type_exception_count}</span>
        </p>
        <p>
          Fee matches schedule: <span className={schedule?.fee_matches_schedule ? 'text-emerald-400' : 'text-amber-400'}>{String(schedule?.fee_matches_schedule)}</span> ·
          Tax matches schedule: <span className={schedule?.tax_matches_schedule ? 'text-emerald-400' : 'text-amber-400'}>{String(schedule?.tax_matches_schedule)}</span>
        </p>
        {['orders', 'payments', 'settlements', 'refunds'].map((section) =>
          evidence.related_source_records?.[section]?.length > 0 ? (
            <div key={section}>
              <p className="uppercase tracking-wide text-zinc-600">{section}</p>
              {evidence.related_source_records[section].map((record) => (
                <pre key={JSON.stringify(record)} className="overflow-x-auto rounded bg-zinc-900 p-1.5 font-mono text-[10px] text-zinc-400">
                  {JSON.stringify(record)}
                </pre>
              ))}
            </div>
          ) : null,
        )}
      </div>
    </details>
  )
}

function ProposalCard({ record, onDecided }) {
  const [amount, setAmount] = useState('')
  const [approver, setApprover] = useState('dashboard-user')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setAmount(record.proposed_amount !== null && record.proposed_amount !== undefined ? String(record.proposed_amount) : '')
  }, [record.id])

  async function act(decision) {
    setBusy(true)
    setError(null)
    try {
      const updated = await api.decideResolution(record.batch_id, record.transaction_id, {
        decision,
        approvedAmount: decision === 'APPROVED' ? amount : null,
        approvedBy: approver,
        note,
      })
      onDecided(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="space-y-3 rounded-lg ring-1 ring-cyan-500/30 bg-cyan-500/5 p-3">
      <div className="flex items-center justify-between">
        <span className="rounded bg-cyan-500/15 px-2 py-0.5 font-mono text-[11px] text-cyan-300">{record.proposal_kind}</span>
        <span className="text-[10px] text-zinc-500">
          proposed by <span className={record.proposed_by === 'gemini' ? 'text-cyan-300' : 'text-zinc-400'}>{record.proposed_by}</span>
        </span>
      </div>
      <p className="text-xs leading-relaxed text-zinc-300">{record.rationale}</p>
      <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
        <div className="rounded bg-zinc-950/80 px-2 py-1">
          <p className="text-[9px] uppercase text-zinc-500">Proposed</p>
          <p className="text-zinc-300">{formatINR(record.proposed_amount)}</p>
        </div>
        <div className="rounded bg-zinc-950/80 px-2 py-1">
          <p className="text-[9px] uppercase text-zinc-500">Approved</p>
          <p className="text-zinc-300">{record.approved_amount === null ? '—' : formatINR(record.approved_amount)}</p>
        </div>
        <div className="rounded bg-zinc-950/80 px-2 py-1">
          <p className="text-[9px] uppercase text-zinc-500">Reconciled</p>
          <p className="text-zinc-300">{formatINR(record.reconciled_adjustment_amount ?? 0)}</p>
        </div>
      </div>

      {record.workflow_status === 'PROPOSED' ? (
        <div className="space-y-2 border-t border-zinc-700/60 pt-2">
          <div className="grid grid-cols-2 gap-2">
            <label className="text-[10px] text-zinc-500">
              Approved amount
              <input
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                inputMode="decimal"
                className="mt-0.5 w-full rounded bg-zinc-950 ring-1 ring-zinc-700 px-2 py-1 font-mono text-xs text-zinc-200 focus:outline-none focus:ring-emerald-500/50"
              />
            </label>
            <label className="text-[10px] text-zinc-500">
              Approved by
              <input
                value={approver}
                onChange={(event) => setApprover(event.target.value)}
                className="mt-0.5 w-full rounded bg-zinc-950 ring-1 ring-zinc-700 px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:ring-emerald-500/50"
              />
            </label>
          </div>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Decision note"
            className="w-full rounded bg-zinc-950 ring-1 ring-zinc-700 px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-emerald-500/50"
          />
          {error && <p className="text-[11px] text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button
              onClick={() => act('APPROVED')}
              disabled={busy}
              className="flex-1 rounded-lg bg-emerald-500/90 px-3 py-1.5 text-xs font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-40"
            >
              Approve
            </button>
            <button
              onClick={() => act('REJECTED')}
              disabled={busy}
              className="flex-1 rounded-lg bg-zinc-700 px-3 py-1.5 text-xs font-semibold text-zinc-200 hover:bg-zinc-600 disabled:opacity-40"
            >
              Reject
            </button>
          </div>
          <p className="text-[10px] leading-snug text-zinc-600">
            Approving a VENDOR_QUERY / LINK_RECORD / RETRY resolves the workflow action only — the financial discrepancy
            stays outstanding unless an ADJUSTMENT is applied by the engine.
          </p>
        </div>
      ) : (
        <div className="space-y-1 border-t border-zinc-700/60 pt-2">
          <p className="text-[11px] text-zinc-400">
            {record.workflow_status} by <span className="text-zinc-200">{record.approved_by}</span>
            {record.human_note ? ` · “${record.human_note}”` : ''}
          </p>
          {record.audit?.length > 0 && (
            <div className="space-y-0.5">
              {record.audit.map((event, index) => (
                <p key={index} className="font-mono text-[10px] text-zinc-600">
                  {event.timestamp?.slice(0, 19)} · {event.event} · financial effect {formatINR(event.financial_effect ?? 0)}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

export default function ExceptionExplorer({ result, batchId, onClose, onDecided }) {
  const [resolution, setResolution] = useState(null)
  const [evidence, setEvidence] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setResolution(null)
    setEvidence(null)
    setError(null)
    if (!result || !batchId) return
    api
      .listResolutions(batchId, { transactionId: result.transaction_id })
      .then((records) => {
        if (records.length > 0) setResolution(records[0])
      })
      .catch(() => {})
    api
      .getEvidence(batchId, result.transaction_id)
      .then((payload) => setEvidence(payload.evidence))
      .catch(() => {})
  }, [result?.transaction_id, batchId])

  if (!result) return null

  async function generateProposal() {
    setBusy(true)
    setError(null)
    try {
      const record = await api.createProposal(batchId, result.transaction_id)
      setResolution(record)
      onDecided?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const workflow = resolution?.workflow_status ?? 'OPEN'
  const financial = resolution?.financial_status ?? 'UNRESOLVED'
  const outstanding = financial === 'UNRESOLVED' ? Math.abs(result.variance ?? 0) - (resolution?.reconciled_adjustment_amount ?? 0) : 0

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
          <button onClick={onClose} className="rounded-md bg-zinc-800 px-2 py-1 text-xs text-zinc-400 hover:bg-zinc-700">
            Close ✕
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          <WorkflowBadge status={workflow} />
          <FinancialBadge status={financial} outstanding={outstanding > 0 ? outstanding : 0} />
        </div>

        <section className="rounded-lg bg-zinc-950 ring-1 ring-zinc-800 p-4">
          <div className="grid grid-cols-2 gap-3 font-mono text-sm tabular-nums">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Expected (gross)</p>
              <p className="text-zinc-200">{formatINR(result.expected_amount)}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Deductions</p>
              <p className="text-zinc-400">
                {result.net_expected === null || result.net_expected === undefined
                  ? '—'
                  : formatINR(Number(result.expected_amount) - Number(result.net_expected))}
              </p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Net Expected</p>
              <p className="text-zinc-200">{formatINR(result.net_expected)}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">Settled</p>
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

        <section>
          <h3 className="text-xs uppercase tracking-wide text-zinc-500">Engine reason</h3>
          <p className="mt-1 rounded-lg bg-zinc-950 ring-1 ring-zinc-800 p-3 text-xs leading-relaxed text-zinc-300">
            {result.reason || '—'}
          </p>
        </section>

        {result.status === 'EXCEPTION' && (
          <section className="space-y-3">
            <h3 className="text-xs uppercase tracking-wide text-zinc-500">Resolution</h3>
            {workflow === 'OPEN' && (
              <div className="space-y-2">
                <button
                  onClick={generateProposal}
                  disabled={busy}
                  className="w-full rounded-lg bg-cyan-500/90 px-3 py-2 text-xs font-semibold text-zinc-950 hover:bg-cyan-400 disabled:opacity-40"
                >
                  {busy ? 'Investigating…' : 'Generate resolution proposal'}
                </button>
                {error && <p className="text-[11px] text-red-400">{error}</p>}
              </div>
            )}
            {resolution && <ProposalCard record={resolution} onDecided={(updated) => { setResolution(updated); onDecided?.() }} />}
          </section>
        )}

        <EvidenceViewer evidence={evidence} />

        <section>
          <h3 className="text-xs uppercase tracking-wide text-zinc-500">
            Confidence · {Math.round((result.confidence ?? 0) * 100)}% · matched via {result.match_method.replace('_', ' ')}
          </h3>
          <div className="mt-1.5 h-1.5 w-full rounded-full bg-zinc-800">
            <div className="h-full rounded-full bg-cyan-400" style={{ width: `${Math.round((result.confidence ?? 0) * 100)}%` }} />
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
