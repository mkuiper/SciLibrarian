import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { collectionsApi, projectsApi } from '../api/client'
import { useAuth } from '../store/auth'
import toast from 'react-hot-toast'
import CollectionTree from './CollectionTree'
import {
  BookOpen, LayoutDashboard, Inbox, Radio,
  Plus, ChevronDown, ChevronRight, LogOut, FolderPlus,
  Sparkles, Eye, LayoutGrid, SlidersHorizontal, FolderTree, Trash2, Tag,
  ScrollText,
} from 'lucide-react'

const navItem = 'flex items-center gap-2.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors'
const activeClass = 'bg-alexandria-600 text-white'
const inactiveClass = 'text-slate-300 hover:bg-slate-700 hover:text-white'

export default function Sidebar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [collectionsOpen, setCollectionsOpen] = useState(true)
  const [deletingProject, setDeletingProject] = useState(false)

  const deleteProject = async (project) => {
    if (!confirm(`Delete project "${project.name}"?\n\nThis will permanently delete all its collections, references, monitors, and digests. This cannot be undone.`)) return
    setDeletingProject(true)
    try {
      await projectsApi.delete(project.id)
      localStorage.removeItem('active_project_id')
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
      toast.success(`Project "${project.name}" deleted`)
      navigate('/')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to delete project')
    } finally {
      setDeletingProject(false)
    }
  }

  // Projects must be loaded before currentProject and currentProjectId are computed
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const [activeProjectId, setActiveProjectId] = useState(() => {
    const stored = localStorage.getItem('active_project_id')
    return stored ? parseInt(stored) : null
  })

  const currentProject = projects.find(p => p.id === activeProjectId) || projects[0] || null
  const currentProjectId = currentProject?.id || null

  const switchProject = (id) => {
    setActiveProjectId(id)
    localStorage.setItem('active_project_id', String(id))
  }

  const { data: tree = [] } = useQuery({
    queryKey: ['collections-tree', currentProjectId],
    queryFn: () => collectionsApi.tree(currentProjectId).then(r => r.data),
  })

  return (
    <aside className="w-64 flex-shrink-0 bg-slate-900 flex flex-col h-full">
      <div className="px-4 py-5 border-b border-slate-700">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-alexandria-600 flex items-center justify-center">
            <BookOpen size={16} className="text-white" />
          </div>
          <div>
            <p className="text-white font-semibold text-sm">SciLibrarian</p>
            <p className="text-slate-400 text-xs">Alexandria</p>
          </div>
        </div>
      </div>

      {projects.length > 0 && (
        <div className="px-4 py-3 border-b border-slate-700">
          <p className="text-slate-500 text-xs uppercase tracking-wider mb-1">Project</p>
          <div className="flex items-center gap-1">
            {projects.length === 1 ? (
              <p className="text-slate-200 text-sm font-medium truncate flex-1">{projects[0].name}</p>
            ) : (
              <select
                value={currentProject?.id || ''}
                onChange={e => switchProject(parseInt(e.target.value))}
                className="flex-1 bg-slate-800 text-slate-200 text-xs border border-slate-600 rounded-lg px-2 py-1.5 focus:outline-none focus:border-alexandria-500"
              >
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            )}
            {currentProject && (
              <button
                onClick={() => deleteProject(currentProject)}
                disabled={deletingProject}
                className="text-slate-600 hover:text-red-400 transition-colors flex-shrink-0 p-1"
                title="Delete this project"
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        </div>
      )}

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-0.5">
        <NavLink to="/" end className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <LayoutDashboard size={16} />Dashboard
        </NavLink>
        <NavLink to="/library" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <BookOpen size={16} />Library
        </NavLink>
        <NavLink to="/review" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <Inbox size={16} />Review Queue
        </NavLink>
        <NavLink to="/monitors" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <Radio size={16} />Monitors
        </NavLink>
        <NavLink to="/watch-requests" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <Eye size={16} />Watch Requests
        </NavLink>
        <NavLink to="/digests" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <Sparkles size={16} />Monthly Digest
        </NavLink>
        <NavLink to="/literature-review" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <ScrollText size={16} />Literature Review
        </NavLink>
        <NavLink to="/collections" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <FolderTree size={16} />Collections
        </NavLink>
        <NavLink to="/restructure" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <LayoutGrid size={16} />Restructure
        </NavLink>
        <NavLink to="/tags" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <Tag size={16} />Tag Browser
        </NavLink>
        <NavLink to="/how-it-works" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <BookOpen size={16} />How it works
        </NavLink>

        <div className="pt-4">
          <button
            onClick={() => setCollectionsOpen(v => !v)}
            className="flex items-center justify-between w-full px-3 py-1.5 text-slate-400 text-xs uppercase tracking-wider hover:text-slate-300"
          >
            <span>Collections</span>
            {collectionsOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>

          {collectionsOpen && (
            <div className="mt-1">
              {tree.length === 0 ? (
                <p className="px-3 py-2 text-slate-500 text-xs">No collections yet</p>
              ) : (
                <CollectionTree nodes={tree} depth={0} />
              )}
              <button
                onClick={() => navigate('/collections')}
                className="flex items-center gap-2 w-full px-3 py-1.5 text-slate-500 hover:text-slate-300 text-xs mt-1 transition-colors"
              >
                <FolderPlus size={12} />
                Manage collections
              </button>
            </div>
          )}
        </div>
      </nav>

      <div className="px-3 py-4 border-t border-slate-700 space-y-0.5">
        <button
          onClick={() => navigate('/projects/new')}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-700 hover:text-white rounded-lg transition-colors"
        >
          <Plus size={16} />New Project
        </button>
        <NavLink to="/config" className={({ isActive }) => `${navItem} ${isActive ? activeClass : inactiveClass}`}>
          <SlidersHorizontal size={16} />Configuration
        </NavLink>

        <div className="flex items-center justify-between px-3 py-2 mt-1">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-full bg-slate-600 flex items-center justify-center text-white text-xs font-medium flex-shrink-0">
              {user?.name?.[0]?.toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="text-slate-200 text-xs font-medium truncate">{user?.name}</p>
              <p className="text-slate-500 text-xs truncate">@{user?.username}</p>
            </div>
          </div>
          <button onClick={logout} className="text-slate-500 hover:text-slate-300 transition-colors ml-2" title="Sign out">
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  )
}
