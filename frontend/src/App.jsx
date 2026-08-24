import { useCallback, useEffect, useState } from 'react'
import * as api from './api'
import BatchPanel from './components/BatchPanel.jsx'
import StatsCards from './components/StatsCards.jsx'
import MetricsBar from './components/MetricsBar.jsx'
import ResultsTable from './components/ResultsTable.jsx'
import ExceptionExplorer from './components/ExceptionExplorer.jsx'
import ControllerChat from './components/ControllerChat.jsx'

export default function App() {
  const [batches, setBatches] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [error, setError] = useState(null)
  const [selectedResult, setSelectedResult] = useState(null)
  const [resolutionVersion, setResolutionVersion] = useState(0)

  const refreshBatches = useCallback(async () => {
    try {
      setBatches(await api.listBatches())
    } catch (err) {
      setError(`Backend unreachable: ${err.message}. Is uvicorn running on :8000?`)
    }
  }, [])

  const loadMetrics = useCallback(async (batchId) => {
    setMetrics(null)
    if (!batchId) return
    try {
      const batch = await api.getBatch(batchId)
      if (batch.status !== 'RECONCILED') return
      setMetrics(await api.getMetrics(batchId))
    } catch {
      /* metrics stay null until reconciled */
    }
  }, [])

  useEffect(() => {
    refreshBatches()
  }, [refreshBatches])

  useEffect(() => {
    loadMetrics(selectedId)
    setSelectedResult(null)
  }, [selectedId, loadMetrics])

  const handleResolutionChanged = useCallback(() => {
    setResolutionVersion((version) => version + 1)
  }, [])

  useEffect(() => {
    if (!selectedId) return
    loadMetrics(selectedId)
  }, [resolutionVersion, selectedId, loadMetrics])

  function handleUploaded(batch) {
    setSelectedId(batch.id)
    refreshBatches()
  }

  function handleReconciled(batch) {
    setSelectedId(batch.id)
    refreshBatches()
    loadMetrics(batch.id)
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-zinc-800 bg-zinc-950/90 px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <h1 className="text-lg font-bold tracking-widest text-zinc-100">
            Chrimata - Finance Controller
            <span className="ml-3 rounded bg-zinc-800 px-2 py-0.5 align-middle font-mono text-[10px] font-normal text-emerald-400">
              RAZORPAY BUILDATHON · TRACK 04
            </span>
          </h1>
          <span className="font-mono text-[11px] text-zinc-600">made by Priyanshu Srivastava</span>
        </div>
      </header>

      {error && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded-lg border-l-4 border-red-500 bg-red-500/10 px-4 py-3 text-xs text-red-300">{error}</div>
        </div>
      )}

      <main className="mx-auto grid max-w-7xl gap-4 px-6 py-6 lg:grid-cols-[320px_1fr]">
        <aside className="space-y-4">
          <BatchPanel
            batches={batches}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onUploaded={handleUploaded}
            onReconciled={handleReconciled}
          />
          <ControllerChat batchId={selectedId} />
        </aside>

        <section className="space-y-4">
          <StatsCards metrics={metrics} />
          <MetricsBar metrics={metrics} />
          {metrics && (
            <ResultsTable
              batchId={selectedId}
              onSelectRow={setSelectedResult}
              resolutionVersion={resolutionVersion}
            />
          )}
        </section>
      </main>

      <ExceptionExplorer
        result={selectedResult}
        batchId={selectedId}
        onClose={() => setSelectedResult(null)}
        onDecided={handleResolutionChanged}
      />
    </div>
  )
}
