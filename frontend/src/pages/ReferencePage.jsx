import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { referencesApi } from '../api/client'
import { ArrowLeft, ExternalLink, FileText, Trash2, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

const TYPE_COLORS = {
  paper: 'bg-blue-50 text-blue-700',
  policy: 'bg-purple-50 text-purple-700',
  model_card: 'bg-emerald-50 text-emerald-700',
  evaluation: 'bg-amber-50 text-amber-700',
  government: 'bg-red-50 text-red-700',
  other: 'bg-gray-100 text-gray-600',
}

export default function ReferencePage() {
  const { refId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: ref, isLoading } = useQuery({
    queryKey: ['reference', refId],
    queryFn: () => referencesApi.get(refId).then(r => r.data),
  })

  const handleDelete = async () => {
    if (!confirm('Delete this reference?')) return
    try {
      await referencesApi.delete(refId)
      queryClient.invalidateQueries({ queryKey: ['references'] })
      toast.success('Reference deleted')
      navigate('/library')
    } catch {
      toast.error('Failed to delete')
    }
  }

  if (isLoading) return (
    <div className="flex items-center justify-center py-24">
      <Loader2 size={24} className="animate-spin text-gray-300" />
    </div>
  )

  if (!ref) return (
    <div className="p-8 text-center text-gray-400">Reference not found</div>
  )

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <button onClick={() => navigate(-1)} className="btn-ghost mb-6 -ml-2 text-gray-500">
        <ArrowLeft size={15} />
        Back
      </button>

      <div className="card p-8">
        <div className="flex items-start justify-between gap-4 mb-6">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className={`badge text-xs ${TYPE_COLORS[ref.source_type] || TYPE_COLORS.other}`}>
                {ref.source_type.replace('_', ' ')}
              </span>
              {ref.year && <span className="text-sm text-gray-400">{ref.year}</span>}
            </div>
            <h1 className="text-xl font-bold text-gray-900 leading-tight">{ref.title}</h1>
            {ref.authors && (
              <p className="text-sm text-gray-500 mt-2">{ref.authors}</p>
            )}
          </div>
          <div className="flex gap-2">
            {ref.url && (
              <a href={ref.url} target="_blank" rel="noopener noreferrer" className="btn-secondary">
                <ExternalLink size={14} />
                Open
              </a>
            )}
            <button onClick={handleDelete} className="btn-ghost text-red-400 hover:text-red-600">
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {ref.summary && (
          <div className="mb-6">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Alexandria's Summary
            </h2>
            <div className="bg-alexandria-50 border border-alexandria-100 rounded-xl p-4">
              <p className="text-sm text-gray-700 leading-relaxed">{ref.summary}</p>
            </div>
          </div>
        )}

        {ref.abstract && (
          <div className="mb-6">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Abstract</h2>
            <p className="text-sm text-gray-600 leading-relaxed">{ref.abstract}</p>
          </div>
        )}

        {ref.tags?.length > 0 && (
          <div className="mb-6">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Tags</h2>
            <div className="flex flex-wrap gap-1.5">
              {ref.tags.map(t => (
                <span key={t.tag} className="badge bg-gray-100 text-gray-600">{t.tag}</span>
              ))}
            </div>
          </div>
        )}

        {ref.extra_metadata && Object.keys(ref.extra_metadata).length > 0 && (
          <div>
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Metadata</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
              {Object.entries(ref.extra_metadata).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-gray-400 capitalize">{k.replace(/_/g, ' ')}</dt>
                  <dd className="text-sm text-gray-700">{String(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}

        <div className="mt-6 pt-6 border-t border-gray-100 text-xs text-gray-400">
          Added {new Date(ref.created_at).toLocaleDateString('en-AU', { year: 'numeric', month: 'long', day: 'numeric' })}
          {ref.file_name && ` · ${ref.file_name}`}
        </div>
      </div>
    </div>
  )
}
