import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/client'
import { Sparkles, Loader2, ArrowRight, AlertCircle, Info, Lightbulb } from 'lucide-react'
import toast from 'react-hot-toast'

const PRIORITY_CONFIG = {
  high:   { color: 'border-red-300 bg-red-50',    icon: AlertCircle, iconColor: 'text-red-500' },
  medium: { color: 'border-amber-300 bg-amber-50', icon: Lightbulb,   iconColor: 'text-amber-500' },
  low:    { color: 'border-blue-200 bg-blue-50',   icon: Info,        iconColor: 'text-blue-400' },
}

const TYPE_LABELS = {
  split:  'Split collection',
  merge:  'Merge collections',
  create: 'Create new collection',
  move:   'Move references',
}

export default function RestructurePage() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const currentProject = projects[0]

  const analyse = async () => {
    if (!currentProject) return
    setLoading(true)
    try {
      const { data } = await projectsApi.restructureSuggestions(currentProject.id)
      setResult(data)
    } catch {
      toast.error('Analysis failed. Check your API key.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-xl bg-alexandria-50 flex items-center justify-center">
          <Sparkles size={18} className="text-alexandria-600" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Library Restructure Analysis</h1>
          <p className="text-sm text-gray-500">Alexandria reviews your current structure and suggests improvements</p>
        </div>
      </div>

      <div className="card p-6 mb-6">
        <p className="text-sm text-gray-600 leading-relaxed mb-4">
          As your library grows, the initial collection structure may need adjustment. Alexandria analyses what you've actually collected versus how it's organised, then suggests concrete changes — splitting overcrowded collections, merging sparse ones, or creating new categories for emerging themes.
        </p>
        <button onClick={analyse} disabled={loading || !currentProject} className="btn-primary">
          {loading ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              Alexandria is analysing your library...
            </>
          ) : (
            <>
              <Sparkles size={15} />
              Analyse library structure
            </>
          )}
        </button>
        {!currentProject && (
          <p className="text-xs text-amber-500 mt-2">Create a project first.</p>
        )}
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

          {result.recommendations?.length > 0 ? (
            <div className="space-y-3">
              {result.recommendations.map((rec, i) => {
                const config = PRIORITY_CONFIG[rec.priority] || PRIORITY_CONFIG.low
                const Icon = config.icon
                return (
                  <div key={i} className={`border rounded-xl p-4 ${config.color}`}>
                    <div className="flex items-start gap-3">
                      <Icon size={16} className={`flex-shrink-0 mt-0.5 ${config.iconColor}`} />
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
                            {TYPE_LABELS[rec.type] || rec.type}
                          </span>
                          <span className="badge bg-white text-gray-500 text-xs">{rec.priority}</span>
                        </div>
                        <p className="text-sm text-gray-700 leading-relaxed">{rec.description}</p>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">
              <p>Alexandria found no restructuring suggestions — your library looks well organised!</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
