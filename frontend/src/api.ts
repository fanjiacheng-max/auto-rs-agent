import type { Project, Message, Run, Artifact, ProjectState, RunEvent } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  // Projects
  listProjects: () => request<Project[]>('/projects'),
  createProject: (name: string) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify({ name }) }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),
  renameProject: (id: string, name: string) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),

  // Messages
  listMessages: (projectId: string) =>
    request<Message[]>(`/projects/${projectId}/messages`),
  sendMessage: (projectId: string, content: string) =>
    request<{ message: Message; run: Run }>(`/projects/${projectId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  // Runs
  getRun: (runId: string) => request<Run>(`/runs/${runId}`),
  listRuns: (projectId: string) =>
    request<Run[]>(`/projects/${projectId}/runs`),
  getRunEvents: (runId: string) =>
    request<RunEvent[]>(`/runs/${runId}/events-json`),
  stopRun: (runId: string) =>
    request<void>(`/runs/${runId}/stop`, { method: 'POST' }),
  replyToRun: (runId: string, content: string) =>
    request<void>(`/runs/${runId}/reply`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  // Artifacts
  listArtifacts: (projectId: string) =>
    request<Artifact[]>(`/projects/${projectId}/artifacts`),

  // Project state
  getProjectState: (projectId: string) =>
    request<ProjectState>(`/projects/${projectId}/state`),

  // File preview URL
  fileUrl: (projectId: string, path: string) =>
    `${BASE}/projects/${projectId}/files/${path}`,
}
