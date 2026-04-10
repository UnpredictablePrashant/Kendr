import React, { useState, useEffect, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'

export default function GitPanel() {
  const { state, dispatch } = useApp()
  const [files, setFiles] = useState([])
  const [staged, setStaged] = useState([])
  const [commits, setCommits] = useState([])
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const api = window.kendrAPI
  const cwd = state.projectRoot

  const refresh = useCallback(async () => {
    if (!cwd || !api) return
    setLoading(true)
    const [statusRes, logRes] = await Promise.all([
      api.git.status(cwd),
      api.git.log(cwd, 10)
    ])
    if (!statusRes.error) {
      setFiles(statusRes.files || [])
      dispatch({ type: 'SET_GIT_STATUS', status: statusRes.files, branch: statusRes.branch })
    }
    if (!logRes.error) setCommits(logRes.commits || [])
    setLoading(false)
  }, [cwd])

  useEffect(() => { refresh() }, [cwd])

  const stageFile = async (f) => {
    await api?.git.stage(cwd, [`"${f.path}"`])
    setStaged(s => [...s.filter(x => x !== f.path), f.path])
    refresh()
  }
  const unstageFile = async (f) => {
    await api?.git.unstage(cwd, [`"${f.path}"`])
    setStaged(s => s.filter(x => x !== f.path))
    refresh()
  }
  const stageAll = async () => {
    await api?.git.stage(cwd, ['.'])
    refresh()
  }

  const commit = async () => {
    if (!message.trim()) return
    setLoading(true)
    const res = await api?.git.commit(cwd, message)
    if (!res?.error) {
      setMessage('')
      refresh()
    } else alert(res.error)
    setLoading(false)
  }

  const push = async () => {
    setLoading(true)
    const res = await api?.git.push(cwd)
    if (res?.error) alert(res.error)
    setLoading(false)
  }
  const pull = async () => {
    setLoading(true)
    const res = await api?.git.pull(cwd)
    if (res?.error) alert(res.error)
    refresh()
    setLoading(false)
  }

  const statusColor = (s) => {
    if (s === 'M') return '#e3b341'
    if (s === 'A' || s === '?') return '#89d185'
    if (s === 'D') return '#f47067'
    return '#cccccc'
  }

  if (!cwd) return (
    <div className="sidebar-empty">Open a project folder to see Git status</div>
  )

  return (
    <div className="git-panel">
      <div className="git-actions">
        <button className="icon-btn" title="Refresh" onClick={refresh}>⟳</button>
        <button className="icon-btn" title="Pull" onClick={pull}>↓</button>
        <button className="icon-btn" title="Push" onClick={push}>↑</button>
      </div>

      {/* Changes */}
      <div className="git-section">
        <div className="git-section-header">
          <span>CHANGES ({files.length})</span>
          <button className="icon-btn" title="Stage all" onClick={stageAll}>+</button>
        </div>
        {files.map(f => (
          <div key={f.path} className="git-file" onClick={() => stageFile(f)}>
            <span className="git-file-status" style={{ color: statusColor(f.status) }}>{f.status}</span>
            <span className="git-file-name">{f.path}</span>
          </div>
        ))}
        {files.length === 0 && !loading && (
          <div className="git-clean">No changes</div>
        )}
      </div>

      {/* Commit message */}
      <div className="git-commit">
        <textarea
          className="git-commit-input"
          placeholder="Commit message…"
          value={message}
          onChange={e => setMessage(e.target.value)}
          rows={3}
        />
        <button
          className="btn-primary btn-full"
          disabled={!message.trim() || loading}
          onClick={commit}
        >
          Commit
        </button>
      </div>

      {/* Recent commits */}
      <div className="git-section">
        <div className="git-section-header">RECENT COMMITS</div>
        {commits.map(c => (
          <div key={c.hash} className="git-commit-item" title={c.hash}>
            <span className="git-commit-hash">{c.hash?.slice(0, 7)}</span>
            <span className="git-commit-msg">{c.subject}</span>
            <span className="git-commit-date">{c.date}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
