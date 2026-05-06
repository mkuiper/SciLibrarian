import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/client'

/**
 * Returns the currently active project.
 * Active project is persisted in localStorage; falls back to first project.
 */
export function useProject() {
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const storedId = localStorage.getItem('active_project_id')
  const activeId = storedId ? parseInt(storedId) : null
  const project = projects.find(p => p.id === activeId) || projects[0] || null

  return { project, projects, projectId: project?.id || null }
}
