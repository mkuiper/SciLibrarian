import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { projectsApi, referencesApi, reviewApi } from '../api/client'
import { useAuth } from '../store/auth'
import { useProject } from '../hooks/useProject'
import { BookOpen, Inbox, Sparkles, Plus, ArrowRight, Radio } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

function StatCard({ icon: Icon, label, value, color, onClick }) {
  return (
    <button onClick={onClick} className="card p-5 text-left hover:shadow-md transition-shadow w-full">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${color}`}>
        <Icon size={18} className="text-white" />
      </div>
      <p className="text-2xl font-bold text-gray-900">{value ?? 0}</p>
      <p className="text-sm text-gray-500 mt-0.5">{label}</p>
    </button>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const { project: currentProject, projectId } = useProject()

  const { data: stats } = useQuery({
    queryKey: ['ref-stats', projectId],
    queryFn: () => referencesApi.stats(projectId ? { project_id: projectId } : {}).then(r => r.data),
    enabled: !!projectId,
  })

  const { data: recentRefs = [] } = useQuery({
    queryKey: ['references', 'recent', projectId],
    queryFn: () => referencesApi.list({ project_id: projectId, limit: 5 }).then(r => r.data),
    enabled: !!projectId,
  })

  const { data: queueItems = [] } = useQuery({
    queryKey: ['review-queue', 'pending', projectId],
    queryFn: () => reviewApi.getQueue({ status: 'pending', project_id: projectId, limit: 5 }).then(r => r.data),
  })

  const { data: monitors = [] } = useQuery({
    queryKey: ['monitors', projectId],
    queryFn: () => reviewApi.listMonitors(projectId ? { project_id: projectId } : {}).then(r => r.data),
  })

  const structure = currentProject?.initial_structure
  const activeMonitors = monitors.filter(m => m.enabled).length

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome back, {user?.name?.split(' ')[0]}
        </h1>
        {currentProject ? (
          <p className="text-gray-500 mt-1 text-sm">{currentProject.name} · {currentProject.domain}</p>
        ) : (
          <p className="text-gray-500 mt-1 text-sm">No project yet</p>
        )}
      </div>

      {!currentProject && (
        <div className="card p-8 mb-8 text-center border-dashed border-2 border-gray-200">
          <BookOpen size={32} className="text-gray-300 mx-auto mb-3" />
          <h3 className="text-lg font-semibold text-gray-700 mb-2">Set up your first project</h3>
          <p className="text-gray-500 text-sm mb-4">Tell Alexandria about your research and she'll design your library structure.</p>
          <button onClick={() => navigate('/projects/new')} className="btn-primary">
            <Plus size={16} />Create project
          </button>
        </div>
      )}

      {currentProject && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          <StatCard icon={BookOpen} label="References" value={stats?.total} color="bg-alexandria-600" onClick={() => navigate('/library')} />
          <StatCard icon={Inbox} label="Pending review" value={queueItems.length} color="bg-amber-500" onClick={() => navigate('/review')} />
          <StatCard icon={Radio} label="Active monitors" value={activeMonitors} color="bg-emerald-500" onClick={() => navigate('/monitors')} />
        </div>
      )}

      {/* Source type breakdown */}
      {stats?.by_type && Object.keys(stats.by_type).length > 0 && (
        <div className="card p-5 mb-6">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Library breakdown</h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.by_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
              <button
                key={type}
                onClick={() => navigate(`/library?type=${type}`)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors border border-gray-100"
              >
                <span className="text-sm font-semibold text-gray-800">{count}</span>
                <span className="text-xs text-gray-500">{type.replace('_', ' ')}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-700">Recent additions</h2>
            <button onClick={() => navigate('/library')} className="text-xs text-alexandria-600 hover:underline flex items-center gap-1">
              View all <ArrowRight size={12} />
            </button>
          </div>
          {recentRefs.length === 0 ? (
            <p className="text-sm text-gray-400">No references yet. Add your first one from the Library.</p>
          ) : (
            <div className="space-y-3">
              {recentRefs.map(ref => (
                <button key={ref.id} onClick={() => navigate(`/references/${ref.id}`)} className="w-full text-left group">
                  <p className="text-sm font-medium text-gray-800 group-hover:text-alexandria-600 transition-colors line-clamp-1">{ref.title}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {ref.authors?.split(',')[0] || 'Unknown'} · {formatDistanceToNow(new Date(ref.created_at), { addSuffix: true })}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>

        {currentProject && structure?.welcome_message && (
          <div className="card p-5 bg-gradient-to-br from-slate-900 to-slate-800">
            <div className="flex items-center gap-2 mb-3">
              <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold">A</div>
              <span className="text-slate-300 text-xs font-medium">Alexandria</span>
            </div>
            <p className="text-slate-200 text-sm leading-relaxed italic">"{structure.welcome_message}"</p>
            <button onClick={() => navigate('/digests')} className="mt-4 flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors">
              <Sparkles size={12} />View monthly digest
            </button>
          </div>
        )}

        {queueItems.length > 0 && (
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-700">Review queue</h2>
              <button onClick={() => navigate('/review')} className="text-xs text-alexandria-600 hover:underline flex items-center gap-1">
                Review all <ArrowRight size={12} />
              </button>
            </div>
            <div className="space-y-3">
              {queueItems.map(item => (
                <div key={item.id} className="border-l-2 border-amber-400 pl-3">
                  <p className="text-sm font-medium text-gray-800 line-clamp-1">{item.title}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{item.source} · {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
