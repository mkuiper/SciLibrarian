import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { referencesApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import { Loader2, ArrowLeft, X } from 'lucide-react'

function FieldRow({ label, values, render }) {
  return (
    <tr>
      <td className="align-top text-xs font-semibold text-gray-500 uppercase tracking-wide py-3 pr-4 w-32 border-b border-gray-100">
        {label}
      </td>
      {values.map((v, i) => (
        <td key={i} className="align-top py-3 px-3 text-sm text-gray-700 border-b border-gray-100">
          {render ? render(v) : (v || <span className="text-gray-300">—</span>)}
        </td>
      ))}
    </tr>
  )
}

export default function ComparePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { projectId } = useProject()
  const idsParam = searchParams.get('ids') || ''
  const ids = idsParam.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n))

  const { data: refs = [], isLoading } = useQuery({
    queryKey: ['compare', ids.join(','), projectId],
    queryFn: () => referencesApi.batch(ids, projectId).then(r => r.data),
    enabled: ids.length > 0,
  })

  const removeFromCompare = (idToRemove) => {
    const remaining = ids.filter(i => i !== idToRemove)
    if (remaining.length === 0) {
      navigate('/library')
    } else {
      navigate(`/compare?ids=${remaining.join(',')}`)
    }
  }

  if (ids.length === 0) {
    return (
      <div className="p-6 max-w-5xl mx-auto text-center py-16">
        <h2 className="text-lg font-semibold text-gray-700">Nothing to compare</h2>
        <p className="text-sm text-gray-500 mt-2">Pick 2–8 references from the library and click "Compare".</p>
        <Link to="/library" className="btn-primary mt-4 inline-flex"><ArrowLeft size={14} /> Back to library</Link>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center py-16">
        <Loader2 size={22} className="animate-spin text-gray-300" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Compare references</h1>
          <p className="text-xs text-gray-400 mt-0.5">{refs.length} reference{refs.length !== 1 ? 's' : ''} side by side</p>
        </div>
        <Link to="/library" className="btn-ghost text-sm"><ArrowLeft size={14} /> Library</Link>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50">
              <th className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wide py-3 pl-4 pr-4 w-32"></th>
              {refs.map(r => (
                <th key={r.id} className="text-left py-3 px-3 min-w-[260px]">
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/references/${r.id}`} className="text-sm font-semibold text-alexandria-700 hover:underline line-clamp-3">
                      {r.title}
                    </Link>
                    <button
                      onClick={() => removeFromCompare(r.id)}
                      className="text-gray-300 hover:text-gray-600 shrink-0"
                      title="Remove from compare"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <FieldRow label="Authors" values={refs.map(r => r.authors)} />
            <FieldRow label="Year" values={refs.map(r => r.year)} />
            <FieldRow label="Type" values={refs.map(r => r.source_type?.replace('_', ' '))} />
            <FieldRow
              label="Main finding"
              values={refs.map(r => r.extra_metadata?.findings?.main_finding)}
            />
            <FieldRow
              label="Method"
              values={refs.map(r => r.extra_metadata?.findings?.method)}
            />
            <FieldRow
              label="Limitations"
              values={refs.map(r => r.extra_metadata?.findings?.limitations)}
            />
            <FieldRow
              label="Tags"
              values={refs.map(r => r.tags || [])}
              render={(tags) => tags.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {tags.slice(0, 8).map(t => (
                    <span key={t.tag} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{t.tag}</span>
                  ))}
                </div>
              ) : <span className="text-gray-300">—</span>}
            />
            <FieldRow
              label="Summary"
              values={refs.map(r => r.summary)}
              render={(summary) => summary ? (
                <p className="text-sm text-gray-600 leading-relaxed line-clamp-6">{summary}</p>
              ) : <span className="text-gray-300">—</span>}
            />
            <FieldRow label="DOI" values={refs.map(r => r.doi)} />
            <FieldRow label="arXiv" values={refs.map(r => r.arxiv_id)} />
          </tbody>
        </table>
      </div>
    </div>
  )
}
