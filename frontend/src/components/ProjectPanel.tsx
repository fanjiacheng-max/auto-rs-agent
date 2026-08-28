import { useState, useEffect } from 'react'
import type { Project, Run, RunStatus } from '../types'
import { api } from '../api'
import { Spinner } from './ErrorBoundary'

interface Props {
  projects: Project[]
  loading: boolean
  currentProject: Project | null
  selectedRunId: string | null
  onSelect: (p: Project) => void
  onSelectRun: (run: Run | null) => void
  onProjectsChange: () => void
}

const STATUS_ICON: Record<RunStatus, string> = {
  pending: '○', running: '●', waiting_for_user: '⏸',
  completed: '✓', failed: '✗', interrupted: '⬛',
}
const STATUS_COLOR: Record<RunStatus, string> = {
  pending: '#4a5568', running: '#60a5fa', waiting_for_user: '#fcd34d',
  completed: '#34d399', failed: '#f87171', interrupted: '#9ca3af',
}

export function ProjectPanel({
  projects, loading, currentProject, selectedRunId,
  onSelect, onSelectRun, onProjectsChange,
}: Props) {
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [runs, setRuns] = useState<Run[]>([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!currentProject) { setRuns([]); return }
    setRunsLoading(true)
    api.listRuns(currentProject.id)
      .then(r => setRuns(r.slice(0, 8)))
      .catch(() => setRuns([]))
      .finally(() => setRunsLoading(false))
  }, [currentProject?.id])

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) return
    await api.createProject(name)
    setNewName('')
    setCreating(false)
    onProjectsChange()
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('Delete this project?')) return
    await api.deleteProject(id)
    onProjectsChange()
  }

  const handleSelectProject = (p: Project) => {
    onSelect(p)
    onSelectRun(null)   // reset to current conversation
    setExpanded(false)
  }

  return (
    <div className="panel project-panel">
      <div className="panel-header">
        <div className="project-panel-header-inner">
          <span className="app-name">Research Agent</span>
          <span className="app-subtitle">Biomedical Analysis</span>
        </div>
        <button className="btn-icon" onClick={() => setCreating(true)} title="New project">+</button>
      </div>

      {creating && (
        <div className="create-form">
          <input
            autoFocus value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setCreating(false) }}
            placeholder="Project name"
          />
          <button onClick={handleCreate}>Create</button>
          <button onClick={() => setCreating(false)}>Cancel</button>
        </div>
      )}

      <ul className="project-list">
        <li className="project-list-label">Projects</li>

        {loading && (
          <li style={{ padding: '12px', display: 'flex', justifyContent: 'center' }}>
            <Spinner size={16} />
          </li>
        )}

        {projects.map(p => (
          <li key={p.id}>
            <div
              className={`project-item ${p.id === currentProject?.id ? 'active' : ''}`}
              onClick={() => handleSelectProject(p)}
            >
              <span className="project-name">{p.name}</span>
              <button className="btn-icon btn-delete" onClick={e => handleDelete(e, p.id)} title="Delete">×</button>
            </div>

            {/* Run history — only for active project */}
            {p.id === currentProject?.id && (
              <div className="run-history">
                {runsLoading
                  ? <div className="run-history-loading"><Spinner size={12} /></div>
                  : runs.length > 0 && (
                    <>
                      <div
                        className="run-history-toggle"
                        onClick={() => setExpanded(e => !e)}
                      >
                        {expanded ? '▾' : '▸'} History ({runs.length})
                        {!selectedRunId && <span className="run-current-badge">current</span>}
                      </div>
                      {expanded && (
                        <ul className="run-list">
                          {/* "Current conversation" entry */}
                          <li
                            className={`run-item ${!selectedRunId ? 'run-item-active' : ''}`}
                            onClick={() => onSelectRun(null)}
                          >
                            <span style={{ color: '#60a5fa', fontSize: 11 }}>◎</span>
                            <span className="run-item-label">Current</span>
                          </li>
                          {runs.map(r => (
                            <li
                              key={r.id}
                              className={`run-item ${r.id === selectedRunId ? 'run-item-active' : ''}`}
                              onClick={() => onSelectRun(r)}
                            >
                              <span style={{ color: STATUS_COLOR[r.status], fontSize: 11 }}>
                                {STATUS_ICON[r.status]}
                              </span>
                              <span className="run-item-label">
                                {r.skill_name ?? 'run'}
                              </span>
                              <span className="run-item-time">
                                {r.created_at.slice(11, 16)}
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </>
                  )
                }
              </div>
            )}
          </li>
        ))}

        {!loading && projects.length === 0 && (
          <li className="empty-hint">No projects yet.<br />Click + to create one.</li>
        )}
      </ul>
    </div>
  )
}
