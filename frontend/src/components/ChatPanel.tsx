import { useState, useEffect, useRef } from 'react'
import type { Project, Run, RunEvent } from '../types'
import { api } from '../api'
import { useRunEvents } from '../hooks/useRunEvents'
import { Spinner, InlineError } from './ErrorBoundary'

interface ChatEntry {
  id: string
  type: 'message' | 'event'
  role?: 'user' | 'assistant'
  content?: string
  event?: RunEvent
}

interface Props {
  project: Project
  viewRun: Run | null       // null = live, non-null = historical read-only
  onArtifactsChange: () => void
  onStateChange: () => void
}

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'interrupted'])

export function ChatPanel({ project, viewRun, onArtifactsChange, onStateChange }: Props) {
  const [entries, setEntries] = useState<ChatEntry[]>([])
  const [input, setInput] = useState('')
  const [replyInput, setReplyInput] = useState('')
  const [activeRun, setActiveRun] = useState<Run | null>(null)
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const isHistorical = viewRun !== null
  const isWaitingForUser = !isHistorical && activeRun?.status === 'waiting_for_user'
  const isRunning = !isHistorical && activeRun &&
    !TERMINAL_STATUSES.has(activeRun.status) && !isWaitingForUser

  // Live mode: load conversation messages
  useEffect(() => {
    if (isHistorical) return
    setEntries([])
    setActiveRun(null)
    setError(null)
    setLoading(true)
    api.listMessages(project.id)
      .then(msgs => setEntries(msgs.map(m => ({
        id: m.id, type: 'message', role: m.role, content: m.content,
      }))))
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [project.id, isHistorical])

  // Historical mode: load run events once
  useEffect(() => {
    if (!isHistorical || !viewRun) return
    setEntries([])
    setError(null)
    setLoading(true)
    api.getRunEvents(viewRun.id)
      .then(events => setEntries(events.map(ev => ({
        id: `ev-${ev.id}`, type: 'event', event: ev,
      }))))
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [viewRun?.id, isHistorical])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries])

  // SSE subscription — only in live mode
  useRunEvents((!isHistorical && activeRun?.id) ? activeRun.id : null, (event) => {
    setEntries(prev => [...prev, { id: `ev-${event.id}`, type: 'event', event }])
    if (event.type === 'artifact_created') onArtifactsChange()
    if (event.type === 'plan_resolved' || event.type === 'run_completed') onStateChange()
    if (event.type === 'run_question') {
      setActiveRun(prev => prev ? { ...prev, status: 'waiting_for_user' } : null)
      setSending(false)
    }
    if (['run_completed', 'run_failed', 'run_interrupted'].includes(event.type)) {
      setActiveRun(prev => prev ? {
        ...prev, status: event.type === 'run_completed' ? 'completed' : 'failed',
      } : null)
      setSending(false)
    }
  })

  const handleSend = async () => {
    const content = input.trim()
    if (!content || sending) return
    setSending(true)
    setInput('')
    setError(null)
    setEntries(prev => [...prev, {
      id: `temp-${Date.now()}`, type: 'message', role: 'user', content,
    }])
    try {
      const { run } = await api.sendMessage(project.id, content)
      setActiveRun(run)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSending(false)
    }
  }

  const handleReply = async () => {
    const content = replyInput.trim()
    if (!content || !activeRun) return
    setReplyInput('')
    setEntries(prev => [...prev, {
      id: `temp-${Date.now()}`, type: 'message', role: 'user', content,
    }])
    setActiveRun(prev => prev ? { ...prev, status: 'running' } : null)
    setSending(true)
    try {
      await api.replyToRun(activeRun.id, content)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSending(false)
    }
  }

  return (
    <div className="panel chat-panel">
      <div className="panel-header">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span>{project.name}</span>
          {isHistorical && viewRun && (
            <span style={{ fontSize: 10, color: '#6b7280' }}>
              Viewing · {viewRun.skill_name ?? 'run'} · {viewRun.created_at.slice(0,16).replace('T',' ')}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {!isHistorical && activeRun && (
            <span className={`run-status run-status-${activeRun.status}`}>{activeRun.status}</span>
          )}
          {isHistorical && viewRun && (
            <span className={`run-status run-status-${viewRun.status}`}>{viewRun.status}</span>
          )}
          {isRunning && (
            <button className="btn-stop" onClick={() => api.stopRun(activeRun!.id)}>■ Stop</button>
          )}
        </div>
      </div>

      <div className="chat-messages">
        {loading && (
          <div style={{ display:'flex', justifyContent:'center', padding:24 }}>
            <Spinner size={20} />
          </div>
        )}
        {error && <InlineError message={error} />}
        {!loading && entries.map(e => <ChatEntryRow key={e.id} entry={e} />)}
        {isHistorical && !loading && entries.length === 0 && !error && (
          <div style={{ color:'#4a5568', padding:16, fontSize:13 }}>No events for this run.</div>
        )}
        <div ref={bottomRef} />
      </div>

      {isWaitingForUser && (
        <div className="reply-bar">
          <div className="reply-bar-label">⏸ Agent is waiting for your response</div>
          <div className="reply-bar-input">
            <input autoFocus value={replyInput}
              onChange={e => setReplyInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleReply() }}
              placeholder="Type your reply…" />
            <button className="btn-send" onClick={handleReply} disabled={!replyInput.trim()}>
              Reply
            </button>
          </div>
        </div>
      )}

      {!isHistorical && !isWaitingForUser && (
        <div className="chat-input-area">
          <textarea value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder={sending ? 'Agent is running…' : 'Describe your analysis task…'}
            disabled={sending} rows={3} />
          <button className="btn-send" onClick={handleSend} disabled={sending || !input.trim()}>
            Send
          </button>
        </div>
      )}

      {isHistorical && (
        <div className="history-readonly-bar">
          🔒 Read-only — select "Current" in the left panel to send messages
        </div>
      )}
    </div>
  )
}

// ── Entry renderers ───────────────────────────────────────────────────────

function ChatEntryRow({ entry }: { entry: ChatEntry }) {
  if (entry.type === 'message') {
    return (
      <div className={`chat-message ${entry.role}`}>
        <span className="role-label">{entry.role === 'user' ? 'You' : 'Agent'}</span>
        <p>{entry.content}</p>
      </div>
    )
  }
  return <EventRow event={entry.event!} />
}

function EventRow({ event }: { event: RunEvent }) {
  const p = event.payload

  switch (event.type) {
    case 'run_started':
      return <div className="event event-info">▶ Run started</div>

    case 'skill_selected':
      return (
        <div className="event event-info">
          🔧 Using skill: <strong>{String(p.skill)}</strong>
        </div>
      )

    case 'plan_resolved': {
      const toRun = (p.to_run as string[]) ?? []
      const cached = (p.cached as string[]) ?? []
      const gates = (p.blocking_gates as string[]) ?? []
      return (
        <div className="event event-plan">
          <div className="plan-title">📋 Execution plan</div>
          {cached.length > 0 && <div className="plan-cached">✓ Cached: {cached.join(' → ')}</div>}
          {toRun.length > 0 && <div className="plan-run">▶ Will run: {toRun.join(' → ')}</div>}
          {gates.length > 0 && <div className="plan-gates">⚠ Awaiting: {gates.join(', ')}</div>}
        </div>
      )
    }

    case 'tool_call': {
      const cmd = p.command
        ? <code>{String(p.command)}</code>
        : <code>{JSON.stringify(p.args)}</code>
      return (
        <div className="event event-tool">
          $ {String(p.tool) === 'run_command' ? cmd : <><em>{String(p.tool)}</em>({cmd})</>}
        </div>
      )
    }

    case 'stdout_chunk':
      return <div className="event event-stdout"><pre>{String(p.chunk)}</pre></div>

    case 'tool_result': {
      const result = String(p.result ?? '')
      if (!result) return null
      return (
        <details className="event event-result">
          <summary>{String(p.tool)} result</summary>
          <pre>{result.slice(0, 2000)}</pre>
        </details>
      )
    }

    case 'agent_message':
      return (
        <div className="chat-message assistant">
          <span className="role-label">Agent</span>
          <p style={{ whiteSpace: 'pre-wrap' }}>{String(p.text)}</p>
        </div>
      )

    case 'artifact_created':
      return (
        <div className="event event-artifact">
          📄 New file: <code>{String(p.path)}</code>
        </div>
      )

    case 'run_question':
      return (
        <div className="event event-question">
          <div>❓ {String(p.question)}</div>
          {Array.isArray(p.choices) && (
            <div className="choices">
              {(p.choices as string[]).map(c => (
                <span key={c} className="choice-tag">{c}</span>
              ))}
            </div>
          )}
        </div>
      )

    case 'run_completed':
      return <div className="event event-success">✓ Analysis complete</div>

    case 'run_failed':
      return <div className="event event-error">✗ Failed: {String(p.error)}</div>

    case 'run_interrupted':
      return <div className="event event-warn">⬛ Run stopped</div>

    default:
      return null
  }
}
