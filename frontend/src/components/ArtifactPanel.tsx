import type { Project, Artifact } from '../types'
import { api } from '../api'

const IMAGE_TYPES = new Set(['image', 'png', 'jpg', 'jpeg', 'svg'])
const TEXT_TYPES = new Set(['text', 'json', 'html', 'md'])
const TABLE_TYPES = new Set(['table', 'csv', 'tsv'])

const TYPE_GROUPS: [string, string[]][] = [
  ['Figures', ['image']],
  ['Tables', ['table']],
  ['Reports', ['html', 'pdf']],
  ['Objects', ['rds', 'h5', 'h5ad', 'loom']],
  ['Other', []],
]

function groupArtifacts(artifacts: Artifact[]): Map<string, Artifact[]> {
  const groups = new Map<string, Artifact[]>()
  for (const a of artifacts) {
    let placed = false
    for (const [group, types] of TYPE_GROUPS.slice(0, -1)) {
      if (types.includes(a.artifact_type)) {
        if (!groups.has(group)) groups.set(group, [])
        groups.get(group)!.push(a)
        placed = true
        break
      }
    }
    if (!placed) {
      if (!groups.has('Other')) groups.set('Other', [])
      groups.get('Other')!.push(a)
    }
  }
  return groups
}

interface Props {
  project: Project
  artifacts: Artifact[]
  previewArtifact: Artifact | null
  onPreview: (a: Artifact | null) => void
}

export function ArtifactPanel({ project, artifacts, previewArtifact, onPreview }: Props) {
  const groups = groupArtifacts(artifacts)
  const fileUrl = (a: Artifact) => api.fileUrl(project.id, a.path)

  return (
    <div className="panel artifact-panel">
      <div className="panel-header">
        <span>Files / Results</span>
        {previewArtifact && (
          <button className="btn-icon" onClick={() => onPreview(null)}>×</button>
        )}
      </div>

      {previewArtifact ? (
        <div className="artifact-preview">
          <div className="preview-filename">{previewArtifact.path.split('/').pop()}</div>
          <ArtifactPreview artifact={previewArtifact} url={fileUrl(previewArtifact)} />
        </div>
      ) : (
        <div className="artifact-list">
          {artifacts.length === 0 && (
            <div className="empty-hint">No files yet.</div>
          )}
          {[...groups.entries()].map(([group, items]) => (
            <div key={group} className="artifact-group">
              <div className="artifact-group-title">{group}</div>
              {items.map(a => (
                <div
                  key={a.id}
                  className="artifact-item"
                  onClick={() => onPreview(a)}
                >
                  <span className="artifact-name">{a.path.split('/').pop()}</span>
                  <span className="artifact-size">{formatSize(a.size)}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ArtifactPreview({ artifact, url }: { artifact: Artifact; url: string }) {
  const t = artifact.artifact_type
  if (IMAGE_TYPES.has(t)) {
    return <img src={url} alt={artifact.path} style={{ maxWidth: '100%' }} />
  }
  if (TABLE_TYPES.has(t) || TEXT_TYPES.has(t)) {
    return <iframe src={url} style={{ width: '100%', height: '100%', border: 'none' }} title={artifact.path} />
  }
  if (t === 'html') {
    return <iframe src={url} style={{ width: '100%', height: '100%', border: 'none' }} title={artifact.path} sandbox="allow-scripts" />
  }
  return (
    <div className="preview-unsupported">
      <p>Preview not available for .{artifact.path.split('.').pop()} files.</p>
      <a href={url} download>Download</a>
    </div>
  )
}

function formatSize(bytes: number | null): string {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}K`
  return `${(bytes / 1024 / 1024).toFixed(1)}M`
}
