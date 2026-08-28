import { useState, useEffect, useCallback } from 'react'
import type { Project, Artifact, ProjectState, Run } from './types'
import { api } from './api'
import { ProjectPanel } from './components/ProjectPanel'
import { ChatPanel } from './components/ChatPanel'
import { ArtifactPanel } from './components/ArtifactPanel'
import { StatePanel } from './components/StatePanel'

type RightTab = 'files' | 'state'

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [currentProject, setCurrentProject] = useState<Project | null>(null)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [artifacts, setArtifacts] = useState<Artifact[]>([])
  const [previewArtifact, setPreviewArtifact] = useState<Artifact | null>(null)
  const [projectState, setProjectState] = useState<ProjectState | null>(null)
  const [rightTab, setRightTab] = useState<RightTab>('files')

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true)
    try {
      const list = await api.listProjects()
      setProjects(list)
      if (currentProject && !list.find(p => p.id === currentProject.id)) {
        setCurrentProject(list[0] ?? null)
      }
    } finally {
      setProjectsLoading(false)
    }
  }, [currentProject])

  const loadArtifacts = useCallback(async () => {
    if (!currentProject) return
    setArtifacts(await api.listArtifacts(currentProject.id))
  }, [currentProject])

  const loadState = useCallback(async () => {
    if (!currentProject) return
    try {
      setProjectState(await api.getProjectState(currentProject.id))
    } catch {
      setProjectState(null)
    }
  }, [currentProject])

  useEffect(() => { loadProjects() }, [])

  useEffect(() => {
    setArtifacts([])
    setPreviewArtifact(null)
    setProjectState(null)
    setSelectedRun(null)
    loadArtifacts()
    loadState()
  }, [currentProject?.id])

  const handleSelectProject = (p: Project) => {
    setCurrentProject(p)
    setSelectedRun(null)
  }

  return (
    <div className="app-layout">
      <ProjectPanel
        projects={projects}
        loading={projectsLoading}
        currentProject={currentProject}
        selectedRunId={selectedRun?.id ?? null}
        onSelect={handleSelectProject}
        onSelectRun={setSelectedRun}
        onProjectsChange={loadProjects}
      />

      <div className="center-panel">
        {currentProject ? (
          <ChatPanel
            key={`${currentProject.id}-${selectedRun?.id ?? 'live'}`}
            project={currentProject}
            viewRun={selectedRun}
            onArtifactsChange={loadArtifacts}
            onStateChange={loadState}
          />
        ) : (
          <div className="empty-state">
            <p>Select or create a project to start.</p>
          </div>
        )}
      </div>

      <div className="right-panel">
        {currentProject && (
          <>
            <div className="right-tabs">
              <button
                className={`right-tab ${rightTab === 'files' ? 'active' : ''}`}
                onClick={() => setRightTab('files')}
              >Files</button>
              <button
                className={`right-tab ${rightTab === 'state' ? 'active' : ''}`}
                onClick={() => setRightTab('state')}
              >State</button>
            </div>
            {rightTab === 'files' ? (
              <ArtifactPanel
                project={currentProject}
                artifacts={artifacts}
                previewArtifact={previewArtifact}
                onPreview={setPreviewArtifact}
              />
            ) : (
              <StatePanel project={currentProject} state={projectState} />
            )}
          </>
        )}
      </div>
    </div>
  )
}
