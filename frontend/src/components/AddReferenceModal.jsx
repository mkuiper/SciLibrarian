import { useState, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { referencesApi, librarianApi, projectsApi } from '../api/client'
import { X, Upload, Link, Loader2, FileText, FolderOpen, List, CheckCircle, AlertCircle } from 'lucide-react'
import toast from 'react-hot-toast'

const TABS = [
  { id: 'pdf',     icon: FileText,   label: 'PDF' },
  { id: 'multi',   icon: FolderOpen, label: 'Batch PDFs / ZIP' },
  { id: 'url',     icon: Link,       label: 'URL' },
  { id: 'urls',    icon: List,       label: 'Bulk URLs' },
]

function BatchResults({ results }) {
  if (!results) return null
  return (
    <div className="mt-4 rounded-xl border border-gray-100 overflow-hidden">
      <div className={`px-4 py-2 text-xs font-semibold ${
        results.failed === 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'
      }`}>
        {results.succeeded}/{results.total} processed successfully
        {results.failed > 0 && ` · ${results.failed} failed`}
      </div>
      <div className="max-h-48 overflow-y-auto divide-y divide-gray-50">
        {results.results?.map((r, i) => (
          <div key={i} className="flex items-center gap-2 px-4 py-2">
            <CheckCircle size={12} className="text-emerald-500 flex-shrink-0" />
            <span className="text-xs text-gray-700 truncate">{r.title}</span>
          </div>
        ))}
        {results.errors?.map((e, i) => (
          <div key={i} className="flex items-start gap-2 px-4 py-2">
            <AlertCircle size={12} className="text-red-400 flex-shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-xs text-gray-600 truncate">{e.filename || e.url}</p>
              <p className="text-xs text-red-400">{e.error?.slice(0, 80)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function AddReferenceModal({ onClose, collectionId, projectId }) {
  const [tab, setTab] = useState('pdf')
  const [url, setUrl] = useState('')
  const [bulkUrls, setBulkUrls] = useState('')
  const [model, setModel] = useState('')
  const [file, setFile] = useState(null)
  const [multiFiles, setMultiFiles] = useState([])
  const [zipFile, setZipFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [batchResults, setBatchResults] = useState(null)
  const fileRef = useRef()
  const multiRef = useRef()
  const zipRef = useRef()
  const queryClient = useQueryClient()

  const { data: modelGroups = {} } = useQuery({
    queryKey: ['librarian-models'],
    queryFn: () => librarianApi.models().then(r => r.data),
  })
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const effectiveModel = model || projects[0]?.settings?.ingestion_model || 'claude-sonnet-4-6'
  const allModels = Object.entries(modelGroups).flatMap(([provider, ms]) =>
    ms.map(m => ({ ...m, provider }))
  )

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['references'] })
    queryClient.invalidateQueries({ queryKey: ['ref-stats'] })
  }

  const submit = async () => {
    setLoading(true)
    setBatchResults(null)
    try {
      if (tab === 'pdf') {
        if (!file) { toast.error('Select a PDF'); return }
        const fd = new FormData()
        fd.append('file', file)
        fd.append('model', effectiveModel)
        if (collectionId) fd.append('collection_id', String(collectionId))
        if (projectId) fd.append('project_id', String(projectId))
        await referencesApi.uploadPdf(fd)
        toast.success('Reference added')
        invalidate()
        onClose()

      } else if (tab === 'multi') {
        const isZip = zipFile && zipFile.name.toLowerCase().endsWith('.zip')
        const files = isZip ? null : multiFiles

        if (isZip) {
          const fd = new FormData()
          fd.append('file', zipFile)
          fd.append('model', effectiveModel)
          if (collectionId) fd.append('collection_id', String(collectionId))
          if (projectId) fd.append('project_id', String(projectId))
          const { data } = await referencesApi.uploadZip(fd)
          setBatchResults(data)
          if (data.succeeded > 0) invalidate()
          toast.success(`${data.succeeded}/${data.total} references added from ZIP`)
        } else {
          if (!files.length) { toast.error('Select files or a ZIP'); return }
          const fd = new FormData()
          files.forEach(f => fd.append('files', f))
          fd.append('model', effectiveModel)
          if (collectionId) fd.append('collection_id', String(collectionId))
          if (projectId) fd.append('project_id', String(projectId))
          const { data } = await referencesApi.uploadBulk(fd)
          setBatchResults(data)
          if (data.succeeded > 0) invalidate()
          toast.success(`${data.succeeded}/${data.total} references added`)
        }

      } else if (tab === 'url') {
        if (!url) { toast.error('Enter a URL'); return }
        await referencesApi.fromUrl(url, {
          model: effectiveModel,
          collection_id: collectionId,
          project_id: projectId,
        })
        toast.success('Reference added')
        invalidate()
        onClose()

      } else if (tab === 'urls') {
        const urls = bulkUrls.split('\n').map(u => u.trim()).filter(Boolean)
        if (!urls.length) { toast.error('Enter at least one URL'); return }
        const { data } = await referencesApi.fromUrlsBulk({
          urls,
          model: effectiveModel,
          collection_id: collectionId || null,
          project_id: projectId || null,
        })
        setBatchResults(data)
        if (data.succeeded > 0) invalidate()
        toast.success(`${data.succeeded}/${data.total} URLs ingested`)
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to process — check your AI API key')
    } finally {
      setLoading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const dropped = [...e.dataTransfer.files]
    if (tab === 'pdf') {
      const f = dropped.find(f => f.name.toLowerCase().endsWith('.pdf'))
      if (f) setFile(f)
    } else if (tab === 'multi') {
      const pdfs = dropped.filter(f => f.name.toLowerCase().endsWith('.pdf'))
      const zip = dropped.find(f => f.name.toLowerCase().endsWith('.zip'))
      if (zip) setZipFile(zip)
      else if (pdfs.length) setMultiFiles(pdfs)
    }
  }

  const isBatchTab = tab === 'multi' || tab === 'urls'
  const canClose = !loading || batchResults

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <h2 className="text-base font-semibold text-gray-900">Add reference</h2>
          <button onClick={onClose} disabled={loading && !batchResults} className="text-gray-400 hover:text-gray-600">
            <X size={20} />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-6">
          {/* Tab selector */}
          <div className="flex rounded-xl bg-gray-100 p-1 mb-5">
            {TABS.map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                onClick={() => { setTab(id); setBatchResults(null) }}
                disabled={loading}
                className={`flex-1 flex items-center justify-center gap-1 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  tab === id ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Icon size={12} />{label}
              </button>
            ))}
          </div>

          {/* Single PDF */}
          {tab === 'pdf' && (
            <div
              onDrop={handleDrop}
              onDragOver={e => e.preventDefault()}
              onClick={() => fileRef.current?.click()}
              className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-alexandria-400 transition-colors"
            >
              <input ref={fileRef} type="file" accept=".pdf" onChange={e => setFile(e.target.files[0])} className="hidden" />
              {file ? (
                <>
                  <FileText size={32} className="text-alexandria-600 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-800">{file.name}</p>
                  <p className="text-xs text-gray-400 mt-1">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                </>
              ) : (
                <>
                  <Upload size={28} className="text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-600">Drop a PDF or <span className="text-alexandria-600 font-medium">browse</span></p>
                  <p className="text-xs text-gray-400 mt-1">Alexandria extracts text, generates summary and metadata</p>
                </>
              )}
            </div>
          )}

          {/* Batch PDFs / ZIP */}
          {tab === 'multi' && (
            <div
              onDrop={handleDrop}
              onDragOver={e => e.preventDefault()}
              className="border-2 border-dashed border-gray-200 rounded-xl p-6 text-center cursor-pointer hover:border-alexandria-400 transition-colors"
              onClick={() => (zipFile || multiFiles.length) ? null : multiRef.current?.click()}
            >
              <input ref={multiRef} type="file" accept=".pdf" multiple onChange={e => { setMultiFiles([...e.target.files]); setZipFile(null) }} className="hidden" />
              <input ref={zipRef} type="file" accept=".zip" onChange={e => { setZipFile(e.target.files[0]); setMultiFiles([]) }} className="hidden" />

              {zipFile ? (
                <>
                  <FolderOpen size={28} className="text-alexandria-600 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-800">{zipFile.name}</p>
                  <p className="text-xs text-gray-400 mt-1">{(zipFile.size / 1024 / 1024).toFixed(1)} MB · ZIP archive</p>
                  <button onClick={e => { e.stopPropagation(); setZipFile(null) }} className="text-xs text-red-400 mt-2 hover:underline">Remove</button>
                </>
              ) : multiFiles.length > 0 ? (
                <>
                  <CheckCircle size={28} className="text-emerald-500 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-800">{multiFiles.length} PDF{multiFiles.length > 1 ? 's' : ''} selected</p>
                  <p className="text-xs text-gray-400 mt-1">{multiFiles.map(f => f.name).slice(0, 3).join(', ')}{multiFiles.length > 3 ? ` + ${multiFiles.length - 3} more` : ''}</p>
                  <button onClick={e => { e.stopPropagation(); setMultiFiles([]) }} className="text-xs text-red-400 mt-2 hover:underline">Clear</button>
                </>
              ) : (
                <>
                  <FolderOpen size={28} className="text-gray-300 mx-auto mb-3" />
                  <p className="text-sm text-gray-600">Drop PDFs or a ZIP file here</p>
                  <div className="flex gap-2 justify-center mt-3">
                    <button onClick={e => { e.stopPropagation(); multiRef.current?.click() }} className="btn-secondary text-xs">
                      Select PDFs
                    </button>
                    <button onClick={e => { e.stopPropagation(); zipRef.current?.click() }} className="btn-secondary text-xs">
                      Upload ZIP
                    </button>
                  </div>
                  <p className="text-xs text-gray-400 mt-3">Up to 30 PDFs · Alexandria processes each one</p>
                </>
              )}
            </div>
          )}

          {/* Single URL */}
          {tab === 'url' && (
            <div>
              <label className="label">URL</label>
              <input
                className="input"
                type="url"
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://arxiv.org/abs/..."
                autoFocus
              />
              <p className="text-xs text-gray-400 mt-1.5">Works with arXiv, government sites, journal pages, and most web content</p>
            </div>
          )}

          {/* Bulk URLs */}
          {tab === 'urls' && (
            <div>
              <label className="label">URLs <span className="text-gray-400 font-normal">— one per line</span></label>
              <textarea
                className="input font-mono text-xs leading-relaxed"
                rows={8}
                value={bulkUrls}
                onChange={e => setBulkUrls(e.target.value)}
                placeholder={'https://arxiv.org/abs/2212.08073\nhttps://arxiv.org/abs/2303.08774\nhttps://example.gov/policy.pdf'}
                autoFocus
              />
              <p className="text-xs text-gray-400 mt-1.5">
                {bulkUrls.split('\n').filter(u => u.trim()).length} URL{bulkUrls.split('\n').filter(u => u.trim()).length !== 1 ? 's' : ''} · up to 30 · processed concurrently
              </p>
            </div>
          )}

          {/* Model selector */}
          <div className="mt-4">
            <label className="label">Processing model</label>
            <select value={model} onChange={e => setModel(e.target.value)} className="input text-sm">
              <option value="">Project default ({projects[0]?.settings?.ingestion_model || 'claude-sonnet-4-6'})</option>
              {Object.entries(modelGroups).map(([provider, ms]) => (
                <optgroup key={provider} label={provider}>
                  {ms.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                </optgroup>
              ))}
            </select>
          </div>

          <BatchResults results={batchResults} />
        </div>

        <div className="flex gap-3 px-6 py-4 border-t border-gray-100 flex-shrink-0">
          <button onClick={onClose} disabled={loading && !batchResults} className="btn-secondary flex-1 justify-center">
            {batchResults ? 'Close' : 'Cancel'}
          </button>
          {!batchResults && (
            <button onClick={submit} disabled={loading} className="btn-primary flex-1 justify-center">
              {loading ? (
                <><Loader2 size={15} className="animate-spin" />Alexandria is processing...</>
              ) : isBatchTab ? 'Process batch' : 'Add to library'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
