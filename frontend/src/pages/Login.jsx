import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuth } from '../store/auth'
import { BookOpen, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { data } = await authApi.login({ username, password })
      login(data.access_token, data.user)
      navigate('/')
    } catch {
      toast.error('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-alexandria-600 mb-4">
            <BookOpen size={26} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">SciLibrarian</h1>
          <p className="text-slate-400 mt-1 text-sm">Powered by Alexandria · AI Safety Institute</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Sign in</h2>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label">Username</label>
              <input
                type="text"
                required
                className="input"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="your username"
                autoComplete="username"
                autoFocus
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password"
                required
                className="input"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-2.5">
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              Sign in
            </button>
          </form>
          <p className="mt-5 text-center text-sm text-gray-500">
            No account?{' '}
            <Link to="/register" className="text-alexandria-600 font-medium hover:underline">
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
