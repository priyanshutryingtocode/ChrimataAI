import { useEffect, useRef, useState } from 'react'
import * as api from '../api'
import { SourcePill } from './primitives'

const SUGGESTIONS = [
  'How many transactions are unresolved?',
  'What is the total unresolved amount?',
  'What are the top three exception types?',
  'Which transaction has the largest unexplained variance?',
]

function AssistantMessage({ message }) {
  const answer = message.data
  return (
    <div className="rounded-lg bg-zinc-800/60 ring-1 ring-zinc-700 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span
          className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
            answer.kind === 'NOT_FOUND'
              ? 'bg-red-500/10 text-red-400'
              : 'bg-emerald-500/10 text-emerald-400'
          }`}
        >
          {answer.kind}
        </span>
        <SourcePill source={answer.source} />
      </div>
      <p className="whitespace-pre-line text-xs leading-relaxed text-zinc-200">{answer.answer}</p>

      {Object.keys(answer.key_figures || {}).length > 0 && (
        <dl className="grid grid-cols-2 gap-1.5">
          {Object.entries(answer.key_figures).map(([label, value]) => (
            <div key={label} className="rounded bg-zinc-950/80 px-2 py-1.5">
              <dt className="text-[10px] uppercase tracking-wide text-zinc-500 truncate">{label}</dt>
              <dd className="font-mono text-xs tabular-nums text-cyan-300">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {(answer.confirmed_facts?.length > 0 ||
        answer.probable_explanations?.length > 0 ||
        answer.recommendations?.length > 0) && (
        <div className="space-y-1.5 border-t border-zinc-700/60 pt-2">
          {answer.confirmed_facts?.map((fact, i) => (
            <p key={`f${i}`} className="text-[11px] text-zinc-400">
              <span className="font-semibold text-emerald-500">Fact:</span> {fact}
            </p>
          ))}
          {answer.probable_explanations?.map((exp, i) => (
            <p key={`e${i}`} className="text-[11px] text-zinc-400">
              <span className="font-semibold text-amber-500">Probable:</span> {exp}
            </p>
          ))}
          {answer.recommendations?.map((rec, i) => (
            <p key={`r${i}`} className="text-[11px] text-zinc-400">
              <span className="font-semibold text-cyan-400">Action:</span> {rec}
            </p>
          ))}
        </div>
      )}

      {answer.cited_transactions?.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-0.5">
          {answer.cited_transactions.map((id) => (
            <span key={id} className="rounded bg-zinc-950 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300 ring-1 ring-zinc-700">
              {id}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ControllerChat({ batchId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    setMessages([])
    setInput('')
  }, [batchId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages])

  async function send(questionText) {
    const question = (questionText ?? input).trim()
    if (!question || !batchId || busy) return
    setBusy(true)
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: question }])
    try {
      const data = await api.controllerQuery(batchId, question)
      setMessages((prev) => [...prev, { role: 'assistant', data }])
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', data: { kind: 'ERROR', source: '', answer: err.message } },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="flex min-h-80 flex-1 flex-col rounded-xl bg-zinc-900/60 ring-1 ring-zinc-800 p-4">
      <h2 className="text-sm font-semibold tracking-wide text-zinc-400 uppercase">AI Controller</h2>
      <div ref={scrollRef} className="mt-3 flex-1 space-y-2 overflow-y-auto pr-1 max-h-[420px]">
        {messages.length === 0 && (
          <p className="text-xs leading-relaxed text-zinc-600">
            Ask about this batch. Answers come from stored reconciliation results only.
          </p>
        )}
        {messages.map((message, index) =>
          message.role === 'user' ? (
            <div key={index} className="ml-6 rounded-lg bg-emerald-500/10 ring-1 ring-emerald-500/30 px-3 py-2 text-xs text-emerald-100">
              {message.text}
            </div>
          ) : (
            <AssistantMessage key={index} message={message} />
          ),
        )}
        {busy && <p className="text-[11px] text-zinc-600 animate-pulse">Controller is thinking…</p>}
      </div>

      <div className="mt-2 flex flex-wrap gap-1">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => send(suggestion)}
            disabled={busy || !batchId}
            className="rounded-full bg-zinc-800/70 px-2 py-0.5 text-[10px] text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 disabled:opacity-40"
          >
            {suggestion}
          </button>
        ))}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          send()
        }}
        className="mt-2 flex gap-2"
      >
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={batchId ? 'Ask a question…' : 'Select a batch first'}
          disabled={!batchId || busy}
          className="min-w-0 flex-1 rounded-lg bg-zinc-950 ring-1 ring-zinc-800 px-3 py-2 text-xs placeholder:text-zinc-600 focus:outline-none focus:ring-emerald-500/50 disabled:opacity-40"
        />
        <button
          type="submit"
          disabled={busy || !batchId}
          className="rounded-lg bg-emerald-500/90 px-3 text-sm font-semibold text-zinc-950 hover:bg-emerald-400 disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </section>
  )
}
