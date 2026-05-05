import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi, collectionsApi } from '../api/client'
import ReactMarkdown from 'react-markdown'
import { Sparkles, Plus, Loader2, Mail } from 'lucide-react'
import toast from 'react-hot-toast'
import { format, subMonths, startOfMonth, endOfMonth } from 'date-fns'

export default function DigestPage() {
  const [selectedDigest, setSelectedDigest] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [collectionId, setCollectionId] = useState('')
  const [sendEmail, setSendEmail] = useState(false)
  const queryClient = useQueryClient()

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const currentProject = projects[0]

  const { data: collections = [] } = useQuery({
    queryKey: ['collections-flat'],
    queryFn: () => collectionsApi.list().then(r => r.data),
  })

  const { data: digests = [], isLoading } = useQuery({
    queryKey: ['digests', currentProject?.id],
    queryFn: () => projectsApi.listDigests(currentProject.id).then(r => r.data),
    enabled: !!currentProject,
  })

  const generateDigest = async () => {
    if (!currentProject) { toast.error('No project selected'); return }
    setGenerating(true)
    const lastMonth = subMonths(new Date(), 1)
    try {
      const settings = currentProject.settings || {}
      const model = settings.digest_model || settings.librarian_model || 'claude-sonnet-4-6'
      const { data } = await projectsApi.createDigest(currentProject.id, {
        period_start: startOfMonth(lastMonth).toISOString(),
        period_end: endOfMonth(lastMonth).toISOString(),
        model,
        collection_id: collectionId ? parseInt(collectionId) : null,
        send_email: sendEmail,
      })
      queryClient.invalidateQueries({ queryKey: ['digests', currentProject.id] })
      setSelectedDigest(data)
      toast.success(sendEmail ? 'Digest generated and emailed' : 'Digest generated')
    } catch {
      toast.error('Failed to generate digest. Check your API key.')
    } finally {
      setGenerating(false)
    }
  }

  const active = selectedDigest || digests[0]

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Monthly Digest</h1>
          <p className="text-sm text-gray-500 mt-1">
            Alexandria synthesises the state of the art from your library's actual references.
          </p>
        </div>
      </div>

      {/* Generator panel */}
      <div className="card p-5 mb-6">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Generate new digest</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-48">
            <label className="label">Scope</label>
            <select
              className="input"
              value={collectionId}
              onChange={e => setCollectionId(e.target.value)}
            >
              <option value="">Entire project</option>
              {collections.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2 mb-0.5">
            <input
              type="checkbox"
              id="send-email"
              checked={sendEmail}
              onChange={e => setSendEmail(e.target.checked)}
              className="rounded"
            />
            <label htmlFor="send-email" className="text-sm text-gray-600 flex items-center gap-1">
              <Mail size={13} />Send to mailing list
            </label>
          </div>
          <button
            onClick={generateDigest}
            disabled={generating || !currentProject}
            className="btn-primary"
          >
            {generating ? (
              <><Loader2 size={15} className="animate-spin" />Alexandria is writing...</>
            ) : (
              <><Sparkles size={15} />Generate</>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-3">
          {collectionId
            ? `Collection digest: deep dive on "${collections.find(c => c.id === parseInt(collectionId))?.name}"`
            : 'Project digest: state-of-the-art across all collections'}
          {' · '}Uses {(currentProject?.settings?.digest_model || currentProject?.settings?.librarian_model || 'claude-sonnet-4-6')}
        </p>
      </div>

      {/* Digest history tabs */}
      {digests.length > 1 && (
        <div className="flex gap-2 mb-6 flex-wrap">
          {digests.map(d => (
            <button
              key={d.id}
              onClick={() => setSelectedDigest(d)}
              className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                active?.id === d.id
                  ? 'bg-alexandria-600 text-white border-alexandria-600'
                  : 'border-gray-200 text-gray-600 hover:border-alexandria-300'
              }`}
            >
              {d.title}
            </button>
          ))}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-gray-300" />
        </div>
      ) : !active ? (
        <div className="text-center py-20">
          <div className="w-16 h-16 rounded-2xl bg-alexandria-50 flex items-center justify-center mx-auto mb-4">
            <Sparkles size={28} className="text-alexandria-400" />
          </div>
          <h3 className="text-gray-600 font-medium mb-2">No digests yet</h3>
          <p className="text-gray-400 text-sm">
            Generate your first digest above. Alexandria will synthesise the state of the art from your library's references.
          </p>
        </div>
      ) : (
        <div className="card p-8">
          <div className="flex items-center justify-between mb-6 pb-4 border-b border-gray-100">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold">A</div>
                <span className="text-sm font-medium text-gray-700">Alexandria</span>
              </div>
              <p className="text-xs text-gray-400">
                {active.new_references} new references · Generated {format(new Date(active.created_at), 'd MMMM yyyy')}
              </p>
            </div>
          </div>
          <div className="prose-alexandria max-w-none">
            <ReactMarkdown>{active.content}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
