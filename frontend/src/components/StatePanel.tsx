import type { Project, ProjectState, GateState, ModuleState, ParamAttempt } from '../types'

interface Props {
  project: Project
  state: ProjectState | null
}

const STATUS_ICON: Record<string, string> = {
  completed: '✓', running: '●', failed: '✗', pending: '○',
}
const STATUS_COLOR: Record<string, string> = {
  completed: '#34d399', running: '#60a5fa', failed: '#f87171', pending: '#6b7280',
}

export function StatePanel({ project: _project, state }: Props) {
  if (!state) return <div className="state-panel-empty">No project state yet.</div>

  return (
    <div className="state-panel">

      {/* Inputs */}
      <section className="state-section">
        <div className="state-section-title">Inputs</div>
        {Object.entries(state.inputs).map(([k, v]) => (
          <div key={k} className="state-row">
            <span className="state-key">{k}</span>
            <span className="state-val">{v ?? <em className="state-null">not set</em>}</span>
          </div>
        ))}
      </section>

      {/* Gates */}
      <section className="state-section">
        <div className="state-section-title">Scientific Gates</div>
        {Object.entries(state.gates).map(([name, g]: [string, GateState]) => (
          <div key={name} className="state-row">
            <span className={`gate-dot ${g.confirmed ? 'gate-ok' : 'gate-pending'}`}>
              {g.confirmed ? '✓' : '○'}
            </span>
            <span className="state-key">{name}</span>
            {g.confirmed && g.value && (
              <span className="state-val gate-value">{String(g.value).slice(0, 40)}</span>
            )}
          </div>
        ))}
      </section>

      {/* Modules */}
      {Object.keys(state.modules).length > 0 && (
        <section className="state-section">
          <div className="state-section-title">Pipeline Modules</div>
          {Object.entries(state.modules).map(([name, m]: [string, ModuleState]) => (
            <div key={name} className="state-row">
              <span style={{ color: STATUS_COLOR[m.status] ?? '#6b7280', fontSize: 12 }}>
                {STATUS_ICON[m.status] ?? '?'}
              </span>
              <span className="state-key">{name}</span>
              {m.completed_at && (
                <span className="state-val" style={{ fontSize: 10 }}>
                  {m.completed_at.slice(11, 16)}
                </span>
              )}
            </div>
          ))}
        </section>
      )}

      {/* Tried params summary */}
      {Object.keys(state.tried_params).length > 0 && (
        <section className="state-section">
          <div className="state-section-title">Tried Params</div>
          {Object.entries(state.tried_params).map(([mod, attempts]: [string, ParamAttempt[]]) => (
            <details key={mod} className="tried-params-group">
              <summary>{mod} ({attempts.length} attempt{attempts.length > 1 ? 's' : ''})</summary>
              {attempts.map((a, i) => {
                const { selected, run_id: _r, tried_at: _t, ...params } = a
                return (
                  <div key={i} className={`tried-attempt ${selected ? 'selected' : ''}`}>
                    {selected && <span className="selected-badge">selected</span>}
                    {Object.entries(params).map(([k, v]) => (
                      <span key={k} className="param-kv">
                        {k}={v === null ? 'null' : String(v)}
                      </span>
                    ))}
                  </div>
                )
              })}
            </details>
          ))}
        </section>
      )}

      {/* Next steps */}
      {state.next_steps.length > 0 && (
        <section className="state-section">
          <div className="state-section-title">Next Steps</div>
          {state.next_steps.map((s, i) => (
            <div key={i} className="next-step">→ {s}</div>
          ))}
        </section>
      )}

      {/* Notes */}
      {state.notes && (
        <section className="state-section">
          <div className="state-section-title">Notes</div>
          <pre className="notes-text">{state.notes}</pre>
        </section>
      )}

    </div>
  )
}
