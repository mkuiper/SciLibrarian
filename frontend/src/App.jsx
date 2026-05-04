import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/auth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Register from './pages/Register'
import Dashboard from './pages/Dashboard'
import Library from './pages/Library'
import ProjectSetup from './pages/ProjectSetup'
import ReviewQueue from './pages/ReviewQueue'
import Monitors from './pages/Monitors'
import DigestPage from './pages/DigestPage'
import ReferencePage from './pages/ReferencePage'
import Settings from './pages/Settings'
import WatchRequests from './pages/WatchRequests'
import RestructurePage from './pages/RestructurePage'

function PrivateRoute({ children }) {
  const { user } = useAuth()
  return user ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <Layout />
              </PrivateRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="library" element={<Library />} />
            <Route path="library/:collectionId" element={<Library />} />
            <Route path="references/:refId" element={<ReferencePage />} />
            <Route path="projects/new" element={<ProjectSetup />} />
            <Route path="review" element={<ReviewQueue />} />
            <Route path="monitors" element={<Monitors />} />
            <Route path="watch-requests" element={<WatchRequests />} />
            <Route path="digests" element={<DigestPage />} />
            <Route path="settings" element={<Settings />} />
            <Route path="restructure" element={<RestructurePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
