import { useEffect, useState } from 'react'
import * as api from '../api'
import { formatINR } from '../format'
import { StatusPill, TypeBadge } from './primitives'

const TABS = [
  { key: '', label: 'All' },
  { key: 'MATCHED', label: 'Matched' },
  { key: 'EXCEPTION', label: 'Exceptions' },
]

export default function ResultsTable({ batchId, onSelectRow }) {
  const [tab, setTab] = useState('')
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState({ total: 0, items: [] })
  const [loading, setLoading] = useState(false)
  const limit = 25

  useEffect(() => {
    if (!batchId) return
    let cancelled = false
    setLoading(true)
    api
      .getResults(batchId, { status: tab || undefined, limit, offset })
      .then((payload) => {
        if (!cancelled) setData(payload)
      })
      .catch(() => {
        if (!cancelled) setData({ total: 0, items: [] })
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [batchId, tab, offset])

  function changeTab(key) {
    setTab(key)
    setOffset(0)
  }

  const rangeStart = data.total === 0 ? 0 : offset + 1
  const rangeEnd = Math.min(offset + limit, data.total)

  return (
    <div className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-4">
        <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">Reconciliation results</h2>
        <span className="text-xs text-zinc-600">
          {rangeStart}–{rangeEnd} of {data.total}
        </span>
      </div>
      <div className="flex gap-1 px-4 pt-3">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => changeTab(key)}
            className={`rounded-md px-3 py-1 text-xs font-medium transition ${
              tab === key ? 'bg-emerald-500/15 text-emerald-300' : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-y border-zinc-800 bg-zinc-950/50 text-[11px] uppercase tracking-wide text-zinc-500">
              <th className="px-4 py-2 font-medium">Transaction</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium text-right">Expected</th>
              <th className="px-3 py-2 font-medium text-right">Actual</th>
              <th className="px-3 py-2 font-medium text-right">Variance</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-xs text-zinc-600">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-xs text-zinc-600">
                  No records.
                </td>
              </tr>
            )}
            {!loading &&
              data.items.map((row) => (
                <tr
                  key={row.transaction_id}
                  onClick={() => onSelectRow(row)}
                  className="cursor-pointer border-b border-zinc-800/60 hover:bg-zinc-800/40"
                >
                  <td className="px-4 py-2 font-mono text-xs">{row.transaction_id}</td>
                  <td className="px-3 py-2">
                    <StatusPill status={row.status} />
                  </td>
                  <td className="px-3 py-2">
                    <TypeBadge type={row.exception_type} />
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                    {formatINR(row.expected_amount)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs tabular-nums text-zinc-400">
                    {formatINR(row.actual_amount)}
                  </td>
                  <td
                    className={`px-3 py-2 text-right font-mono text-xs tabular-nums ${
                      row.variance !== 0 ? 'text-amber-400' : 'text-zinc-500'
                    }`}
                  >
                    {formatINR(row.variance)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-end gap-2 px-4 py-3">
        <button
          onClick={() => setOffset(Math.max(0, offset - limit))}
          disabled={offset === 0}
          className="rounded-md bg-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-30"
        >
          Prev
        </button>
        <button
          onClick={() => setOffset(offset + limit)}
          disabled={rangeEnd >= data.total}
          className="rounded-md bg-zinc-800 px-3 py-1 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-30"
        >
          Next
        </button>
      </div>
    </div>
  )
}
