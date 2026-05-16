import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import { Sparkles, Loader2, AlertCircle, Info, Lightbulb, FolderPlus, Edit3, ArrowRight, GitMerge, Check, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'

const PRIORITY_BORDER = {
  high:   'border-red-300',
  medium: 'border-amber-300',
  low:    'border-blue-200',
}

const TYPE_META = {
  create_collection: { icon: FolderPlus,  label: 'Create collection',     color: 'text-emerald-600' },
  rename_collection: { icon: Edit3,       label: 'Rename collection',     color: 'text-blue-600' },
  move_references:   { icon: ArrowRight,  label: 'Move references',       color: 'text-amber-600' },
  merge_collections: { icon: GitMerge,    label: 'Merge collections',     color: 'text-purple-600' },
}

function ActionCard({ action, onApply, applying }) {
  const meta = TYPE_META[action.type] || { icon: Info, label: action.type, color: 'text-gray-500' }
  const Icon = meta.icon

  return (
    <div className={`card border-l-4 ${PRIORITY_BORDER[action.priority] || 'border-gray-200'} p-4`}>
      <div className="flex items-start gap-3">
        <Icon size={18} className={`flex-shrink-0 mt-0.5 ${meta.color}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">{meta.label}</span>
            <span className="badge bg-gray-100 text-gray-500 text-xs">{action.priority}</span>
            {action.invalid && (
              <span className="badge bg-red-50 text-red-600 text-xs flex items-center gap-1">
                <AlertTriangle size={10} /> invalid
              </span>
            )}
          </div>

          {action.reasoning && (
            <p className="text-sm text-gray-700 leading-relaxed mb-3">{action.reasoning}</p>
          )}

          {action.type === 'create_collection' && (
            <div className="text-xs text-gray-500 space-y-1 mb-3">
              <p><span className="text-gray-400">Name:</span> <span className="text-gray-700 font-medium">{action.name}</span></p>
              {action.description && <p><span className="text-gray-400">Description:</span> {action.description}</p>}
              {action.parent_id && <p><span className="text-gray-400">Parent:</span> id {action.parent_id}</p>}
              {action.reference_previews?.length > 0 && (
                <div>
                  <p className="text-gray-400 mt-1">Will populate with {action.reference_previews.length} ref(s):</p>
                  <ul className="ml-2 mt-1 space-y-0.5">
                    {action.reference_previews.slice(0, 8).map(r => (
                      <li key={r.id} className="text-gray-600 truncate">• {r.title}{r.year && <span className="text-gray-400"> ({r.year})</span>}</li>
                    ))}
                    {action.reference_previews.length > 8 && (
                      <li className="text-gray-400">…and {action.reference_previews.length - 8} more</li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          )}

          {action.type === 'rename_collection' && (
            <div className="text-xs text-gray-500 space-y-1 mb-3">
              <p><span className="text-gray-400">From:</span> <span className="text-gray-700 line-through">{action.current_name || `id ${action.collection_id}`}</span></p>
              <p><span className="text-gray-400">To:</span> <span className="text-gray-700 font-medium">{action.new_name}</span></p>
              {action.new_description && (
                <p><span className="text-gray-400">New description:</span> {action.new_description}</p>
              )}
            </div>
          )}

          {action.type === 'move_references' && (
            <div className="text-xs text-gray-500 space-y-1 mb-3">
              <p>
                <span className="text-gray-400">Move</span>{' '}
                <span className="text-gray-700 font-medium">{action.reference_previews?.length ?? 0}</span>{' '}
                <span className="text-gray-400">reference(s) into</span>{' '}
                <span className="text-gray-700 font-medium">{action.target_collection_name || `id ${action.target_collection_id}`}</span>
              </p>
              {action.reference_previews?.length > 0 && (
                <ul className="ml-2 mt-1 space-y-0.5">
                  {action.reference_previews.slice(0, 8).map(r => (
                    <li key={r.id} className="text-gray-600 truncate">• {r.title}{r.year && <span className="text-gray-400"> ({r.year})</span>}</li>
                  ))}
                  {action.reference_previews.length > 8 && (
                    <li className="text-gray-400">…and {action.reference_previews.length - 8} more</li>
                  )}
                </ul>
              )}
            </div>
          )}

          {action.type === 'merge_collections' && (
            <div className="text-xs text-gray-500 space-y-1 mb-3">
              <p>
                <span className="text-gray-400">Merge</span>{' '}
                <span className="text-gray-700 font-medium">{action.source_collection_name || `id ${action.source_collection_id}`}</span>{' '}
                <span className="text-gray-400">({action.source_ref_count ?? 0} ref(s)) into</span>{' '}
                <span className="text-gray-700 font-medium">{action.target_collection_name || `id ${action.target_collection_id}`}</span>
              </p>
              <p className="text-amber-600">⚠ source collection will be deleted after refs are moved</p>
            </div>
          )}

          {action.invalid && (
            <p className="text-xs text-red-600 mb-2">{action.invalid_reason}</p>
          )}

          <button
            onClick={() => onApply(action)}
            disabled={applying || action.invalid || action.applied}
            className={`btn-primary text-xs ${action.applied ? 'opacity-60' : ''}`}
          >
            {applying ? <Loader2 size={11} className="animate-spin" /> : action.applied ? <Check size={11} /> : null}
            {action.applied ? 'Applied' : applying ? 'Applying…' : 'Apply'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function RestructurePage() {
  const queryClient = useQueryClient()
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [applyingIndex, setApplyingIndex] = useState(null)

  const { projectId } = useProject()
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const currentProject = projects.find(p => p.id === projectId) || projects[0]

  const analyse = async () => {
    if (!currentProject) return
    setLoading(true)
    try {
      const { data } = await projectsApi.restructureSuggestions(currentProject.id)
      setResult({ ...data, actions: (data.actions || []).map(a => ({ ...a, applied: false })) })
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Analysis failed.')
    } finally {
      setLoading(false)
    }
  }

  const applyAction = async (action) => {
    if (!currentProject || !result) return
    const index = result.actions.indexOf(action)
    setApplyingIndex(index)
    try {
      const { data } = await projectsApi.applyRestructureAction(currentProject.id, action)
      const message = data.moved_count
        ? `Done — ${data.moved_count} reference(s) moved`
        : data.created_collection_id
          ? `Collection created (id ${data.created_collection_id})`
          : 'Done'
      toast.success(message)
      setResult(prev => ({
        ...prev,
        actions: prev.actions.map((a, i) => i === index ? { ...a, applied: true } : a),
      }))
      queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
      queryClient.invalidateQueries({ queryKey: ['collections-flat'] })
      queryClient.invalidateQueries({ queryKey: ['references'] })
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Action failed')
    } finally {
      setApplyingIndex(null)
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-xl bg-alexandria-50 flex items-center justify-center">
          <Sparkles size={18} className="text-alexandria-600" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Library Restructure</h1>
          <p className="text-sm text-gray-500">Alexandria reviews your structure and proposes concrete actions you can apply one at a time</p>
        </div>
      </div>

      <div className="card p-6 mb-6">
        <p className="text-sm text-gray-600 leading-relaxed mb-4">
          Alexandria looks at your collections and recent references, then suggests specific reorganisation actions:
          create new collections, rename existing ones, move references, or merge sparse collections together. Each suggestion
          shows you exactly what will change — review before clicking Apply.
        </p>
        <button onClick={analyse} disabled={loading || !currentProject} className="btn-primary">
          {loading ? (
            <><Loader2 size={15} className="animate-spin" />Alexandria is analysing…</>
          ) : (
            <><Sparkles size={15} />{result ? 'Re-analyse' : 'Analyse library structure'}</>
          )}
        </button>
        {!currentProject && <p className="text-xs text-amber-500 mt-2">Create a project first.</p>}
      </div>

      {result && (
        <div>
          {result.summary && (
            <div className="bg-slate-900 rounded-xl p-5 mb-6">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-5 h-5 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold">A</div>
                <span className="text-slate-300 text-xs font-medium">Alexandria's assessment</span>
              </div>
              <p className="text-slate-200 text-sm leading-relaxed">{result.summary}</p>
            </div>
          )}

          {result.actions?.length > 0 ? (
            <div className="space-y-3">
              {result.actions.map((action, i) => (
                <ActionCard
                  key={i}
                  action={action}
                  applying={applyingIndex === i}
                  onApply={applyAction}
                />
              ))}
            </div>
          ) : result.error ? (
            <div className="card border-l-4 border-amber-300 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle size={18} className="text-amber-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm text-gray-700 font-medium mb-1">Couldn't parse the model's response</p>
                  <p className="text-xs text-gray-500">{result.summary}</p>
                  {result.raw_excerpt && (
                    <details className="mt-3">
                      <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">View model output</summary>
                      <pre className="mt-2 text-xs bg-gray-50 p-2 rounded font-mono whitespace-pre-wrap text-gray-600">{result.raw_excerpt}</pre>
                    </details>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">
              <p>Alexandria found no restructuring actions — your library looks well organised.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
