import { useEffect, useRef, useState } from 'react'
import { Bot, Send, User } from 'lucide-react'
import { api } from '../../api/client'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import { Card } from '../ui/Card'

const SUGGESTIONS = ['What should I learn next?', 'Which skills are weak?', 'What score will I get?',
  'Which difficulty suits me?', 'How am I doing?']

export default function AssistantChat({ studentId, provider }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef(null)

  useEffect(() => { setMessages([]) }, [studentId])
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'nearest' }) }, [messages])

  const ask = async (text) => {
    const question = text.trim()
    if (!question || busy) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: question }])
    setBusy(true)
    try {
      const r = await api.ai.ask(studentId, question)
      setMessages((m) => [...m, { role: 'assistant', text: r.answer, source: r.source, model: r.model, note: r.note }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', text: e.message, error: true }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="AI learning assistant"
          subtitle={provider === 'claude' ? 'Claude, grounded in your model outputs' : 'Rule-based answers from your model outputs (no API key set)'}
          action={<Badge tone={provider === 'claude' ? 'brand' : 'neutral'} icon={Bot}>{provider === 'claude' ? 'Claude API' : 'Built-in'}</Badge>}
          bodyClassName="flex flex-col gap-3">
      <div className="max-h-96 min-h-48 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {messages.length === 0 && (
          <p className="text-sm text-ink-3">Ask about your next courses, weak skills, expected quiz scores or progress. Answers use only your data and the app's models.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-2 ${m.role === 'user' ? 'justify-end' : ''}`}>
            {m.role === 'assistant' && <Bot className="mt-1 size-5 shrink-0 text-brand" aria-hidden />}
            <div className={`max-w-[85%] whitespace-pre-line rounded-xl px-3 py-2 text-sm ${
              m.role === 'user' ? 'bg-brand text-white' : m.error ? 'bg-critical-soft text-critical' : 'bg-surface-2 text-ink'}`}>
              {m.text}
              {m.role === 'assistant' && !m.error && (
                <p className="mt-1.5 text-[11px] text-ink-3">
                  {m.source === 'claude' ? `Answered by ${m.model}` : 'Built-in answer'}{m.note ? ` · ${m.note}` : ''}
                </p>
              )}
            </div>
            {m.role === 'user' && <User className="mt-1 size-5 shrink-0 text-ink-3" aria-hidden />}
          </div>
        ))}
        {busy && <p className="text-sm text-ink-3">Thinking…</p>}
        <div ref={end} />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => ask(s)} disabled={busy}
                  className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-2 hover:bg-surface-2 disabled:opacity-50">{s}</button>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(input) }} className="flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000} placeholder="Ask the assistant…"
               aria-label="Message the assistant"
               className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-3 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25" />
        <Button type="submit" icon={Send} loading={busy} disabled={!input.trim()}>Send</Button>
      </form>
    </Card>
  )
}
