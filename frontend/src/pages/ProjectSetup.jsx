import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { projectsApi } from '../api/client'
import { BookOpen, Loader2, Sparkles, ChevronRight, X, Plus } from 'lucide-react'
import toast from 'react-hot-toast'

// Suggestions only — users can type anything. Covers broad research fields.
const DOMAIN_SUGGESTIONS = [
  // AI & Computing
  'AI Safety', 'AI Governance', 'Machine Learning', 'Interpretability',
  'AI Policy', 'AI Ethics', 'Robotics', 'Computer Vision', 'NLP',
  'Cybersecurity', 'Quantum Computing', 'Software Engineering', 'HCI',
  // Life Sciences
  'Biology', 'Bioinformatics', 'Genomics', 'Drug Discovery', 'Pharmacology',
  'Neuroscience', 'Ecology', 'Evolutionary Biology', 'Immunology',
  'Public Health', 'Epidemiology', 'Clinical Medicine',
  // Physical Sciences
  'Physics', 'Chemistry', 'Materials Science', 'Astronomy', 'Geology',
  'Atmospheric Science', 'Climate Science', 'Ocean Science', 'Energy',
  // Engineering
  'Mechanical Engineering', 'Electrical Engineering', 'Chemical Engineering',
  'Civil Engineering', 'Biomedical Engineering', 'Aerospace', 'Nuclear',
  // Social Sciences & Humanities
  'Economics', 'Political Science', 'Sociology', 'Psychology',
  'Philosophy', 'History', 'Law', 'Education', 'Anthropology',
  'International Relations', 'Ethics',
  // Multidisciplinary
  'Sustainability', 'Food Security', 'Urban Planning', 'Finance',
]

export default function ProjectSetup() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [project, setProject] = useState(null)
  const [domainInput, setDomainInput] = useState('')
  const [form, setForm] = useState({
    name: '',
    description: '',
    domains: [],
    goals: '',
  })

  const addDomain = (d) => {
    const clean = d.trim()
    if (clean && !form.domains.includes(clean)) {
      setForm(f => ({ ...f, domains: [...f.domains, clean] }))
    }
    setDomainInput('')
  }

  const removeDomain = (d) => setForm(f => ({ ...f, domains: f.domains.filter(x => x !== d) }))

  const handleDomainKey = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addDomain(domainInput)
    }
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { data } = await projectsApi.create(form)
      setProject(data)
      setStep(2)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
    } catch (err) {
      toast.error('Failed to create project. Check your API key.')
    } finally {
      setLoading(false)
    }
  }

  if (step === 2 && project) {
    const structure = project.initial_structure || {}
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
        <div className="w-full max-w-2xl">
          <div className="card p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 rounded-xl bg-alexandria-600 flex items-center justify-center">
                <Sparkles size={18} className="text-white" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Alexandria has prepared your library</h2>
                <p className="text-sm text-gray-500">for {project.name}</p>
              </div>
            </div>

            {structure.welcome_message && (
              <div className="bg-alexandria-50 border border-alexandria-200 rounded-xl p-4 mb-6">
                <p className="text-sm text-alexandria-800 leading-relaxed italic">"{structure.welcome_message}"</p>
                <p className="text-xs text-alexandria-600 mt-2 font-medium">— Alexandria</p>
              </div>
            )}

            {structure.collections?.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Suggested Collection Structure</h3>
                <div className="space-y-2">
                  {structure.collections.map((col, i) => (
                    <div key={i} className="border border-gray-100 rounded-lg p-3">
                      <div className="flex items-center gap-2">
                        <BookOpen size={14} className="text-alexandria-600" />
                        <span className="text-sm font-medium text-gray-800">{col.name}</span>
                      </div>
                      {col.description && <p className="text-xs text-gray-500 mt-1 ml-5">{col.description}</p>}
                      {col.children?.length > 0 && (
                        <div className="ml-5 mt-2 space-y-1">
                          {col.children.map((child, j) => (
                            <div key={j} className="flex items-center gap-1.5 text-xs text-gray-500">
                              <ChevronRight size={10} />
                              {child.name}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {structure.initial_guidance && (
              <div className="bg-gray-50 rounded-xl p-4 mb-6">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Alexandria's Guidance</h3>
                <p className="text-sm text-gray-700 leading-relaxed">{structure.initial_guidance}</p>
              </div>
            )}

            <button onClick={() => navigate('/')} className="btn-primary w-full justify-center">
              Enter your library
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>
    )
  }

  const filteredSuggestions = DOMAIN_SUGGESTIONS.filter(
    d => d.toLowerCase().includes(domainInput.toLowerCase()) && !form.domains.includes(d)
  ).slice(0, 8)

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Set up your research project</h1>
          <p className="text-gray-500 mt-2 text-sm">
            Tell Alexandria about your project and she'll design an optimal library structure.
          </p>
        </div>

        <div className="card p-8">
          <form onSubmit={handleCreate} className="space-y-5">
            <div>
              <label className="label">Project name</label>
              <input
                className="input"
                required
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Australian AI Safety Institute Reference Library"
              />
            </div>

            <div>
              <label className="label">
                Research domains
                <span className="text-gray-400 font-normal ml-1">(type and press Enter, or click suggestions)</span>
              </label>
              {form.domains.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {form.domains.map(d => (
                    <span key={d} className="inline-flex items-center gap-1 px-2.5 py-1 bg-alexandria-600 text-white text-xs rounded-full">
                      {d}
                      <button type="button" onClick={() => removeDomain(d)} className="hover:text-alexandria-200">
                        <X size={10} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="relative">
                <input
                  className="input"
                  value={domainInput}
                  onChange={e => setDomainInput(e.target.value)}
                  onKeyDown={handleDomainKey}
                  onBlur={() => domainInput && addDomain(domainInput)}
                  placeholder="e.g. AI Safety, Climate Science, Drug Discovery..."
                />
                {domainInput && filteredSuggestions.length > 0 && (
                  <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-10 overflow-hidden">
                    {filteredSuggestions.map(s => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => addDomain(s)}
                        className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                      >
                        <Plus size={12} className="text-gray-400" />{s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {form.domains.length === 0 && !domainInput && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {DOMAIN_SUGGESTIONS.slice(0, 10).map(d => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => addDomain(d)}
                      className="text-xs px-2.5 py-1 bg-gray-100 hover:bg-alexandria-50 hover:text-alexandria-700 text-gray-600 rounded-full transition-colors border border-gray-200"
                    >
                      {d}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="label">Description</label>
              <textarea
                className="input"
                required
                rows={3}
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="What is this project about? What kinds of references will you collect?"
              />
            </div>

            <div>
              <label className="label">Research goals <span className="text-gray-400 font-normal">(optional)</span></label>
              <textarea
                className="input"
                rows={2}
                value={form.goals}
                onChange={e => setForm(f => ({ ...f, goals: e.target.value }))}
                placeholder="What questions should this library help answer?"
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-3">
              {loading ? (
                <><Loader2 size={16} className="animate-spin" />Alexandria is designing your library...</>
              ) : (
                <><Sparkles size={16} />Create project with Alexandria</>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
