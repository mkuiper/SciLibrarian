import { useState, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { referencesApi, librarianApi, projectsApi } from '../api/client'
import { X, Upload, Link, Loader2, FileText } from 'lucide-react'
import toast from 'react-hot-toast'

export default function AddReferenceModal({ onClose, collectionId }) {
  const [tab, setTab] = useState('pdf')
  const [url, setUrl] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-6')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const fileRef = useRef()
  const queryClient = useQueryClient()

  const { data: modelGroups = {} } = useQuery({
    queryKey: ['librarian-models'],
    queryFn: () => librarianApi.models().then(r => r.data),
  })

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const projectIngestionModel = projects[0]?.settings?.ingestion_model
  const effectiveModel = model === 'claude-sonnet-4-6' && projectIngestionModel
    ? projectIngestionModel
    : model

  const allModels = Object.entries(modelGroups).flatMap(([provider, ms]) =>
    ms.map(m => ({ ...m, provider }))
  )

  const handleFile = (e) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f?.type === 'application/pdf') setFile(f)
  }

  const submit = async () => {
    setLoading(true)
    try {
      if (tab === 'pdf') {
        if (!file) { toast.error('Select a PDF file'); return }
        const fd = new FormData()
        fd.append('file', file)
        fd.append('model', model)
        if (collectionId) fd.append('collection_id', String(collectionId))
        await referencesApi.uploadPdf(fd)
      } else {
        if (!url) { toast.error('Enter a URL'); return }
        await referencesApi.fromUrl(url, { model, collection_id: collectionId })
      }
      toast.success('Alexandria has processed and filed your reference')
      queryClient.invalidateQueries({ queryKey: ['references'] })
      onClose()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to process reference')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Add reference</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>

        <div className="p-6">
          <div className="flex rounded-xl bg-gray-100 p-1 mb-5">
            {[['pdf', <FileText size={14} />, 'PDF Upload'], ['url', <Link size={14} />, 'From URL']].map(([t, icon, label]) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-sm font-medium rounded-lg transition-all ${tab === t ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}
              >
                {icon}{label}
              </button>
            ))}
          </div>

          {tab === 'pdf' ? (
            <div
              onDrop={handleDrop}
              onDragOver={e => e.preventDefault()}
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-alexandria-400 transition-colors"
            >
              <input ref={fileRef} type="file" accept=".pdf" onChange={handleFile} className="hidden" />
              {file ? (
                <div>
                  <FileText size={32} className="text-alexandria-600 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-800">{file.name}</p>
                  <p className="text-xs text-gray-400 mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              ) : (
                <div>
                  <Upload size={28} className="text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-600">Drop a PDF here or <span className="text-alexandria-600 font-medium">browse</span></p>
                  <p className="text-xs text-gray-400 mt-1">Alexandria will extract text, generate a summary and metadata</p>
                </div>
              )}
            </div>
          ) : (
            <div>
              <label className="label">URL</label>
              <input
                className="input"
                type="url"
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://arxiv.org/abs/..."
              />
              <p className="text-xs text-gray-400 mt-1.5">Works with arXiv, government sites, journal pages, and most web content</p>
            </div>
          )}

          <div className="mt-4">
            <label className="label">Processing model</label>
            <select value={model} onChange={e => setModel(e.target.value)} className="input">
              {allModels.length > 0
                ? Object.entries(modelGroups).map(([provider, ms]) => (
                    <optgroup key={provider} label={provider}>
                      {ms.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </optgroup>
                  ))
                : (
                  <>
                    <option value="claude-sonnet-4-6">Claude Sonnet 4.6</option>
                    <option value="claude-haiku-4-5-20251001">Claude Haiku 4.5 (faster)</option>
                  </>
                )
              }
            </select>
            {projectIngestionModel && projectIngestionModel !== model && (
              <p className="text-xs text-gray-400 mt-1">Project default: {projectIngestionModel}</p>
            )}
          </div>
        </div>

        <div className="flex gap-3 px-6 pb-6">
          <button onClick={onClose} className="btn-secondary flex-1 justify-center">Cancel</button>
          <button onClick={submit} disabled={loading} className="btn-primary flex-1 justify-center">
            {loading ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                Alexandria is processing...
              </>
            ) : 'Add to library'}
          </button>
        </div>
      </div>
    </div>
  )
}
