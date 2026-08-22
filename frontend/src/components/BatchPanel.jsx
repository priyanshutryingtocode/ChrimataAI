import { useState } from 'react'
import * as api from '../api'

const FILE_FIELDS = [
  { key: 'payments', label: 'Payments', required: true },
  { key: 'settlements', label: 'Settlements', required: true },
  { key: 'orders', label: 'Orders' },
  { key: 'refunds', label: 'Refunds' },
  { key: 'groundTruth', label: 'Ground truth (optional)' },
]

export default function BatchPanel({ batches, selectedId, onSelect, onUploaded, onReconciled }) {
  const [name, setName] = useState('')
  const [files, setFiles] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  function setFile(key, file) {
    setFiles((prev) => ({ ...prev, [key]: file }))
  }

  async function handleUpload(event) {
    event.preventDefault()
    if (!files.payments || !files.settlements) {
      setError('payments.csv and settlements.csv are required')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const batch = await api.uploadBatch({ name, ...files })
      setName('')
      setFiles({})
      onUploaded(batch)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleReconcile() {
    if (!selectedId) return
    setBusy(true)
    setError(null)
    try {
      const batch = await api.reconcileBatch(selectedId)
      onReconciled(batch)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-4">
        <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">Upload dataset</h2>
        <form onSubmit={handleUpload} className="mt-3 space-y-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Batch name"
            className="w-full rounded-lg bg-zinc-950 ring-1 ring-zinc-800 px-3 py-2 text-sm placeholder:text-zinc-600 focus:outline-none focus:ring-emerald-500/50"
          />
          {FILE_FIELDS.map(({ key, label, required }) => (
            <label key={key} className="block text-xs text-zinc-400">
              <span>
                {label}
                {required && <span className="text-emerald-500"> *</span>}
              </span>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => setFile(key, e.target.files[0] || null)}
                className="mt-1 block w-full text-xs text-zinc-400 file:mr-2 file:rounded-md file:border-0 file:bg-zinc-800 file:px-2 file:py-1 file:text-xs file:text-zinc-200 hover:file:bg-zinc-700"
              />
            </label>
          ))}
          {error && <p className="text-xs text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-emerald-500/90 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-40"
          >
            Upload CSVs
          </button>
        </form>
      </section>

      <section className="rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-4">
        <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">Batches</h2>
        <ul className="mt-3 space-y-2 max-h-56 overflow-y-auto pr-1">
          {batches.length === 0 && <li className="text-xs text-zinc-600">No batches uploaded yet.</li>}
          {batches.map((batch) => (
            <li key={batch.id}>
              <button
                onClick={() => onSelect(batch.id)}
                className={`w-full rounded-lg px-3 py-2 text-left text-xs transition ${
                  batch.id === selectedId
                    ? 'bg-emerald-500/10 ring-1 ring-emerald-500/40'
                    : 'bg-zinc-950 ring-1 ring-zinc-800 hover:ring-zinc-600'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-zinc-200 truncate">
                    {batch.name || batch.id.slice(0, 8)}
                  </span>
                  <span
                    className={`ml-2 shrink-0 rounded-full px-1.5 py-0.5 text-[10px] ${
                      batch.status === 'RECONCILED'
                        ? 'bg-emerald-500/10 text-emerald-400'
                        : 'bg-zinc-800 text-zinc-500'
                    }`}
                  >
                    {batch.status}
                  </span>
                </div>
                <span className="text-zinc-500">
                  {batch.orders_count} orders · {batch.settlements_count} settlements
                </span>
              </button>
            </li>
          ))}
        </ul>
        <button
          onClick={handleReconcile}
          disabled={busy || !selectedId}
          className="mt-3 w-full rounded-lg bg-cyan-500/90 px-3 py-2 text-sm font-semibold text-zinc-950 hover:bg-cyan-400 disabled:opacity-40"
        >
          Run reconciliation
        </button>
      </section>
    </div>
  )
}
