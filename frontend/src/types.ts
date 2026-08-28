// ── Domain types ──────────────────────────────────────────

export interface Project {
  id: string
  name: string
  workspace_path: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  project_id: string
  run_id: string | null
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface Run {
  id: string
  project_id: string
  trigger_message_id: string | null
  status: RunStatus
  skill_name: string | null
  created_at: string
  updated_at: string
}

export type RunStatus =
  | 'pending'
  | 'running'
  | 'waiting_for_user'
  | 'completed'
  | 'failed'
  | 'interrupted'

export interface Artifact {
  id: string
  project_id: string
  run_id: string
  path: string
  artifact_type: string
  size: number | null
  created_at: string
}

// ── Project state (status.json) ───────────────────────────

export interface GateState {
  confirmed: boolean
  value: string | null
  confirmed_at: string | null
}

export interface ModuleState {
  status: 'pending' | 'running' | 'completed' | 'failed'
  completed_at: string | null
  checkpoint_path: string | null
  checkpoint_verified: boolean
}

export interface ParamAttempt {
  selected: boolean
  run_id: string
  tried_at: string
  [key: string]: unknown
}

export interface ProjectState {
  project_name: string
  created_at: string
  last_updated: string
  inputs: Record<string, string | null>
  gates: Record<string, GateState>
  modules: Record<string, ModuleState>
  tried_params: Record<string, ParamAttempt[]>
  next_steps: string[]
  notes: string
}

// ── SSE event types ───────────────────────────────────────

export type RunEventType =
  | 'run_started'
  | 'skill_selected'
  | 'plan_resolved'
  | 'tool_call'
  | 'tool_result'
  | 'stdout_chunk'
  | 'agent_message'
  | 'artifact_created'
  | 'run_question'
  | 'run_completed'
  | 'run_failed'
  | 'run_interrupted'

export interface RunEvent {
  id: number
  type: RunEventType
  payload: Record<string, unknown>
}
