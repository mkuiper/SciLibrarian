import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi, collectionsApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import ReactMarkdown from 'react-markdown'
import { Sparkles, Plus, Loader2, Mail, Trash2, BookOpen, List, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { format, subMonths, startOfMonth, endOfMonth, subDays } from 'date-fns'

const DIGEST_TYPES = [
  {
    value: 'state_of_art',
    label: 'State of the Art',
    icon: Sparkles,
    description: 'Broad synthesis — themes, contradictions, coverage gaps',
  },
  {
    value: 'whats_new',
    label: "What's New",
    icon: Zap,
    description: 'Focused briefing on recent additions only',
  },
  {
    value: 'reading_list',
    label: 'Reading List',
    icon: List,
    description: 'Prioritised reading list with rationale for each pick',
  },
]

function DateRangePreset({ label, onClick, active }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-1 text-xs rounded-md border transition-all ${
        active ? 'bg-alexandria-600 text-white border-alexandria-600' : 'border-gray-200 text-gray-500 hover:border-alexandria-300'
      }`}
    >
      {label}
    </button>
  )
}

export default function DigestPage() {
  const [selectedDigest, setSelectedDigest] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [collectionId, setCollectionId] = useState('')
  const [tag, setTag] = useState('')
  const [digestType, setDigestType] = useState('state_of_art')
  const [sendEmail, setSendEmail] = useState(false)
  const [periodStart, setPeriodStart] = useState(() => format(startOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'))
  const [periodEnd, setPeriodEnd] = useState(() => format(endOfMonth(subMonths(new Date(), 1)), 'yyyy-MM-dd'))
  const queryClient = useQueryClient()
  const { project: currentProject, projectId } = useProject()

  const { data: collections = [] } = useQuery({
    queryKey: ['collections-flat', projectId],
    queryFn: () => collectionsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
  })

  const { data: digests = [], isLoading } = useQuery({
    queryKey: ['digests', projectId],
    queryFn: () => projectsApi.listDigests(projectId).then(r => r.data),
    enabled: !!projectId,
  })

  const applyPreset = (months) => {
    const ref = months === 0 ? new Date() : subMonths(new Date(), months)
    setPeriodStart(format(startOfMonth(ref), 'yyyy-MM-dd'))
    setPeriodEnd(format(endOfMonth(ref), 'yyyy-MM-dd'))
  }

  const applyDaysPreset = (days) => {
    const end = new Date()
    const start = subDays(end, days)
    setPeriodStart(format(start, 'yyyy-MM-dd'))
    setPeriodEnd(format(end, 'yyyy-MM-dd'))
  }

  const isPresetActive = (months) => {
    const ref = months === 0 ? new Date() : subMonths(new Date(), months)
    return periodStart === format(startOfMonth(ref), 'yyyy-MM-dd')
  }

  const generateDigest = async () => {
    if (!currentProject) { toast.error('No project selected'); return }
    setGenerating(true)
    try {
      const settings = currentProject.settings || {}
      const model = settings.digest_model || settings.librarian_model || 'claude-sonnet-4-6'
      const { data } = await projectsApi.createDigest(currentProject.id, {
        period_start: new Date(periodStart).toISOString(),
        period_end: new Date(periodEnd + 'T23:59:59').toISOString(),
        model,
        collection_id: collectionId ? parseInt(collectionId) : null,
        tag: tag.trim() || null,
        digest_type: digestType,
        send_email: sendEmail,
      })
      queryClient.invalidateQueries({ queryKey: ['digests', projectId] })
      setSelectedDigest(data)
      toast.success(sendEmail ? 'Digest generated and emailed' : 'Digest generated')
    } catch {
      toast.error('Failed to generate digest. Check your API key and model selection.')
    } finally {
      setGenerating(false)
    }
  }

  const deleteDigest = async (digest) => {
    if (!confirm(`Delete "${digest.title}"? This cannot be undone.`)) return
    try {
      await projectsApi.deleteDigest(currentProject.id, digest.id)
      queryClient.invalidateQueries({ queryKey: ['digests', projectId] })
      if (selectedDigest?.id === digest.id) setSelectedDigest(null)
      toast.success('Digest deleted')
    } catch {
      toast.error('Failed to delete digest')
    }
  }

  const selectedType = DIGEST_TYPES.find(t => t.value === digestType)
  const active = selectedDigest || digests[0]

  // Scope description for the hint line
  const scopeHint = tag.trim()
    ? `Topic digest: everything tagged "#${tag.trim()}"`
    : collectionId
    ? `Collection digest: "${collections.find(c => c.id === parseInt(collectionId))?.name}"`
    : 'Project digest: all collections'

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Digests</h1>
          <p className="text-sm text-gray-500 mt-1">
            Alexandria synthesises your library into a focused research report.
          </p>
        </div>
      </div>

      {/* Generator panel */}
      <div className="card p-5 mb-6 space-y-4">
        <h2 className="text-sm font-semibold text-gray-700">Generate new digest</h2>

        {/* Digest type selector */}
        <div>
          <label className="label mb-2">Type</label>
          <div className="grid grid-cols-3 gap-2">
            {DIGEST_TYPES.map(({ value, label, icon: Icon, description }) => (
              <button
                key={value}
                type="button"
                onClick={() => setDigestType(value)}
                className={`p-3 rounded-lg border text-left transition-all ${
                  digestType === value
                    ? 'border-alexandria-500 bg-alexandria-50 text-alexandria-800'
                    : 'border-gray-200 text-gray-600 hover:border-gray-300'
                }`}
              >
                <div className="flex items-center gap-1.5 mb-1">
                  <Icon size={13} />
                  <span className="text-xs font-medium">{label}</span>
                </div>
                <p className="text-xs text-gray-400 leading-tight">{description}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Scope row */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Collection scope</label>
            <select
              className="input"
              value={collectionId}
              onChange={e => { setCollectionId(e.target.value); setTag('') }}
            >
              <option value="">Entire project</option>
              {collections.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Topic / tag focus <span className="text-gray-400 font-normal">(overrides collection)</span></label>
            <input
              className="input"
              placeholder="e.g. alignment, interpretability"
              value={tag}
              onChange={e => { setTag(e.target.value); if (e.target.value) setCollectionId('') }}
            />
          </div>
        </div>

        {/* Date range row */}
        <div>
          <label className="label mb-2">Period</label>
          <div className="flex gap-1.5 mb-2 flex-wrap">
            <DateRangePreset label="This month" onClick={() => applyPreset(0)} active={isPresetActive(0)} />
            <DateRangePreset label="Last month" onClick={() => applyPreset(1)} active={isPresetActive(1)} />
            <DateRangePreset label="Last 3 months" onClick={() => applyPreset(3)} active={isPresetActive(3)} />
            <DateRangePreset label="Last 6 months" onClick={() => applyPreset(6)} active={isPresetActive(6)} />
            <DateRangePreset label="Last 30 days" onClick={() => applyDaysPreset(30)} active={false} />
            <DateRangePreset label="Last 90 days" onClick={() => applyDaysPreset(90)} active={false} />
          </div>
          <div className="flex gap-3 items-center">
            <input type="date" className="input flex-1" value={periodStart} onChange={e => setPeriodStart(e.target.value)} />
            <span className="text-gray-400 text-sm">to</span>
            <input type="date" className="input flex-1" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)} />
          </div>
        </div>

        {/* Actions row */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-2">
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

        <p className="text-xs text-gray-400 border-t border-gray-100 pt-2">
          {scopeHint}
          {' · '}{selectedType?.label}
          {' · '}Uses {currentProject?.settings?.digest_model || currentProject?.settings?.librarian_model || 'claude-sonnet-4-6'}
        </p>
      </div>

      {/* Digest history */}
      {digests.length > 0 && (
        <div className="flex gap-2 mb-6 flex-wrap">
          {digests.map(d => (
            <div key={d.id} className="flex items-center gap-1">
              <button
                onClick={() => setSelectedDigest(d)}
                className={`px-3 py-1.5 text-xs rounded-lg border transition-all ${
                  active?.id === d.id
                    ? 'bg-alexandria-600 text-white border-alexandria-600'
                    : 'border-gray-200 text-gray-600 hover:border-alexandria-300'
                }`}
              >
                {d.title}
              </button>
              <button
                onClick={() => deleteDigest(d)}
                className="p-1 text-gray-300 hover:text-red-400 transition-colors"
                title="Delete digest"
              >
                <Trash2 size={12} />
              </button>
            </div>
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
          <p className="text-gray-400 text-sm max-w-sm mx-auto">
            Generate your first digest above. Alexandria reads your actual reference summaries and
            full text to synthesise a focused report.
          </p>
        </div>
      ) : (
        <div className="card p-8">
          <div className="flex items-start justify-between mb-6 pb-4 border-b border-gray-100">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold">A</div>
                <span className="text-sm font-medium text-gray-700">Alexandria</span>
              </div>
              <p className="text-xs text-gray-400">
                {active.new_references} new references · Generated {format(new Date(active.created_at), 'd MMMM yyyy')}
              </p>
            </div>
            <button
              onClick={() => deleteDigest(active)}
              className="p-1.5 text-gray-300 hover:text-red-400 transition-colors"
              title="Delete this digest"
            >
              <Trash2 size={15} />
            </button>
          </div>
          <div className="prose-alexandria max-w-none">
            <ReactMarkdown>{active.content}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}
