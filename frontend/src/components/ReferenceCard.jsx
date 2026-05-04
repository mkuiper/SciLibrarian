import { useNavigate } from 'react-router-dom'
import { FileText, Globe, Shield, Cpu, ClipboardList, Newspaper, ExternalLink } from 'lucide-react'
import clsx from 'clsx'

const TYPE_CONFIG = {
  paper:       { icon: FileText,     color: 'bg-blue-50 text-blue-700',    label: 'Paper' },
  policy:      { icon: Shield,       color: 'bg-purple-50 text-purple-700', label: 'Policy' },
  model_card:  { icon: Cpu,          color: 'bg-emerald-50 text-emerald-700', label: 'Model Card' },
  evaluation:  { icon: ClipboardList,color: 'bg-amber-50 text-amber-700',  label: 'Evaluation' },
  government:  { icon: Shield,       color: 'bg-red-50 text-red-700',      label: 'Government' },
  news:        { icon: Newspaper,    color: 'bg-gray-50 text-gray-600',    label: 'News' },
  other:       { icon: Globe,        color: 'bg-gray-50 text-gray-600',    label: 'Other' },
}

export default function ReferenceCard({ reference: r }) {
  const navigate = useNavigate()
  const config = TYPE_CONFIG[r.source_type] || TYPE_CONFIG.other
  const Icon = config.icon

  return (
    <div
      className="card p-5 hover:shadow-md transition-all cursor-pointer group"
      onClick={() => navigate(`/references/${r.id}`)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={clsx('badge', config.color)}>
              <Icon size={10} className="mr-1" />
              {config.label}
            </span>
            {r.year && <span className="text-xs text-gray-400">{r.year}</span>}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 group-hover:text-alexandria-700 transition-colors line-clamp-2">
            {r.title}
          </h3>
          {r.authors && (
            <p className="text-xs text-gray-500 mt-1 line-clamp-1">{r.authors}</p>
          )}
          {r.summary && (
            <p className="text-xs text-gray-500 mt-2 line-clamp-2 leading-relaxed">{r.summary}</p>
          )}
          {r.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-3">
              {r.tags.slice(0, 5).map(t => (
                <span key={t.tag} className="badge bg-gray-100 text-gray-500 text-xs">{t.tag}</span>
              ))}
              {r.tags.length > 5 && <span className="text-xs text-gray-400">+{r.tags.length - 5}</span>}
            </div>
          )}
        </div>
        {r.url && (
          <a
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            className="text-gray-300 hover:text-alexandria-500 transition-colors flex-shrink-0 mt-0.5"
          >
            <ExternalLink size={14} />
          </a>
        )}
      </div>
    </div>
  )
}
