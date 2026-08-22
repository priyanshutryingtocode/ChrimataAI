export function StatusPill({ status }) {
  const isMatched = status === 'MATCHED'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide ${
        isMatched ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/30' : 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/30'
      }`}
    >
      {status}
    </span>
  )
}

export function TypeBadge({ type }) {
  if (!type || type === 'NONE') return <span className="text-zinc-600">—</span>
  return (
    <span className="inline-flex items-center rounded px-1.5 py-0.5 font-mono text-[11px] bg-zinc-800 text-zinc-300 ring-1 ring-zinc-700">
      {type}
    </span>
  )
}

export function SourcePill({ source }) {
  const isLLM = source === 'gemini'
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
        isLLM ? 'bg-cyan-500/10 text-cyan-300 ring-1 ring-cyan-500/30' : 'bg-zinc-700/50 text-zinc-400 ring-1 ring-zinc-600'
      }`}
    >
      {isLLM ? 'Gemini' : 'Deterministic fallback'}
    </span>
  )
}
