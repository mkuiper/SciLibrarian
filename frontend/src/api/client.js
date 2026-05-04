import axios from 'axios'

// All requests go through the Vite proxy (/api → backend).
// This works in Docker (proxy targets internal network) and locally.
const BASE = '/api'

export const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const authApi = {
  login: (data) => api.post('/auth/login', data),
  register: (data) => api.post('/auth/register', data),
  me: () => api.get('/auth/me'),
}

export const projectsApi = {
  list: () => api.get('/projects'),
  get: (id) => api.get(`/projects/${id}`),
  create: (data) => api.post('/projects', data),
  update: (id, data) => api.patch(`/projects/${id}`, data),
  updateSettings: (id, data) => api.patch(`/projects/${id}/settings`, data),
  restructureSuggestions: (id) => api.post(`/projects/${id}/restructure-suggestions`),
  listDigests: (id) => api.get(`/projects/${id}/digests`),
  createDigest: (id, data) => api.post(`/projects/${id}/digests`, data),
  getDigest: (projectId, digestId) => api.get(`/projects/${projectId}/digests/${digestId}`),
  listWatchRequests: (id) => api.get(`/projects/${id}/watch-requests`),
  createWatchRequest: (id, data) => api.post(`/projects/${id}/watch-requests`, data),
}

export const collectionsApi = {
  tree: () => api.get('/collections/tree'),
  list: () => api.get('/collections'),
  get: (id) => api.get(`/collections/${id}`),
  create: (data) => api.post('/collections', data),
  update: (id, data) => api.patch(`/collections/${id}`, data),
  delete: (id) => api.delete(`/collections/${id}`),
}

export const referencesApi = {
  list: (params) => api.get('/references', { params }),
  get: (id) => api.get(`/references/${id}`),
  stats: (params) => api.get('/references/stats/summary', { params }),
  uploadPdf: (formData) => api.post('/references/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  fromUrl: (url, params) => api.post('/references/from-url', null, { params: { url, ...params } }),
  update: (id, data) => api.patch(`/references/${id}`, data),
  delete: (id) => api.delete(`/references/${id}`),
  fileUrl: (id) => `${BASE}/references/${id}/file`,
  bibtexUrl: (id) => `${BASE}/references/${id}/bibtex`,
}

export const searchApi = {
  search: (params) => api.get('/search', { params }),
}

export const reviewApi = {
  getQueue: (params) => api.get('/review/queue', { params }),
  decide: (id, data) => api.post(`/review/queue/${id}/decide`, data),
  listMonitors: () => api.get('/review/monitors'),
  createMonitor: (data) => api.post('/review/monitors', data),
  updateMonitor: (id, data) => api.patch(`/review/monitors/${id}`, data),
  deleteMonitor: (id) => api.delete(`/review/monitors/${id}`),
  runMonitor: (id) => api.post(`/review/monitors/${id}/run`),
}

export const librarianApi = {
  models: () => api.get('/librarian/models'),
  chat: async (messages, model = 'claude-sonnet-4-6', projectId, onChunk) => {
    const token = localStorage.getItem('token')
    const response = await fetch(`${BASE}/librarian/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ messages, model, project_id: projectId }),
    })
    if (!response.ok) throw new Error('Chat request failed')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let full = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value)
      full += chunk
      if (onChunk) onChunk(chunk, full)
    }
    return full
  },
}
