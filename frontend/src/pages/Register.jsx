import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authApi } from '../api/client'
import { useAuth } from '../store/auth'
import { BookOpen, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

export default function Register() {
  const [form, setForm] = useState({ name: '', username: '', password: '' })
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    if (form.password.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    try {
      const { data } = await authApi.register(form)
      login(data.access_token, data.user)
      navigate('/projects/new')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Registration failed')
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
          <p className="text-slate-400 mt-1 text-sm">Create your research library</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Create account</h2>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="label">Display name</label>
              <input
                type="text"
                required
                className="input"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Dr Jane Smith"
              />
            </div>
            <div>
              <label className="label">Username</label>
              <input
                type="text"
                required
                className="input"
                value={form.username}
                onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                placeholder="jsmith"
                autoComplete="username"
              />
              <p className="text-xs text-gray-400 mt-1">Used to sign in — no email required</p>
            </div>
            <div>
              <label className="label">Password</label>
              <input
                type="password"
                required
                className="input"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="At least 8 characters"
                autoComplete="new-password"
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary w-full justify-center py-2.5">
              {loading && <Loader2 size={16} className="animate-spin" />}
              Create account
            </button>
          </form>
          <p className="mt-5 text-center text-sm text-gray-500">
            Already have an account?{' '}
            <Link to="/login" className="text-alexandria-600 font-medium hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
