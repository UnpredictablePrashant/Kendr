import React, { useState, useEffect } from 'react'
import { useApp } from '../contexts/AppContext'

function formatBytes(value) {
  const bytes = Number(value || 0)
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  const digits = size >= 10 || unitIndex === 0 ? 0 : 1
  return `${size.toFixed(digits)} ${units[unitIndex]}`
}

export default function ModelManager() {
  const { state } = useApp()
  const [ollamaModels, setOllamaModels] = useState([])
  const [loadingModels, setLoadingModels] = useState(true)
  const [pullTag, setPullTag] = useState('')
  const [pullState, setPullState] = useState(null)
  const [pulling, setPulling] = useState(false)
  const [pullStatus, setPullStatus] = useState(null)   // {ok, msg} or null
  const backendUrl = state.backendUrl || 'http://127.0.0.1:2151'

  const fetchModels = async () => {
    setLoadingModels(true)
    try {
      const r = await fetch(`${backendUrl}/api/models/ollama`)
      if (r.ok) {
        const data = await r.json()
        setOllamaModels(data.models || [])
      }
    } catch (_) {
    } finally {
      setLoadingModels(false)
    }
  }

  const fetchPullStatus = async () => {
    try {
      const r = await fetch(`${backendUrl}/api/models/ollama/pull/status`)
      if (!r.ok) return
      const data = await r.json()
      setPullState(data)
      const live = Boolean(data.active) && ['starting', 'running', 'cancelling'].includes(data.status)
      setPulling(live)
      if (!live && data.status === 'completed') {
        fetchModels()
      }
    } catch (_) {}
  }

  useEffect(() => {
    fetchModels()
    fetchPullStatus()
  }, [backendUrl])

  useEffect(() => {
    if (!pullState?.active || !['starting', 'running', 'cancelling'].includes(pullState.status)) return
    const timer = setInterval(() => { fetchPullStatus() }, 900)
    return () => clearInterval(timer)
  }, [backendUrl, pullState?.active, pullState?.status])

  const pullModel = async () => {
    if (!pullTag.trim() || pulling) return
    const model = pullTag.trim()
    setPullStatus(null)
    try {
      const r = await fetch(`${backendUrl}/api/models/ollama/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      })
      const data = await r.json().catch(() => ({}))
      if ((r.ok || r.status === 202) && data.ok) {
        setPulling(true)
        setPullState(data.pull || null)
        setPullStatus(null)
      } else {
        setPullStatus({ ok: false, msg: data.error || `Pull failed (${r.status})` })
      }
    } catch (e) {
      setPullStatus({ ok: false, msg: `Network error: ${e.message}` })
    }
  }

  const cancelPull = async () => {
    try {
      const r = await fetch(`${backendUrl}/api/models/ollama/pull/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await r.json().catch(() => ({}))
      if (r.ok && data.ok) {
        setPullState(data.pull || null)
        setPulling(Boolean(data.pull?.active))
      } else {
        setPullStatus({ ok: false, msg: data.error || `Cancel failed (${r.status})` })
      }
    } catch (e) {
      setPullStatus({ ok: false, msg: `Network error: ${e.message}` })
    }
  }

  const activePull = pullState && (pullState.active || ['completed', 'failed', 'cancelled'].includes(pullState.status)) ? pullState : null
  const progressPercent = Number(activePull?.percent || 0)
  const hasDeterminateProgress = Number(activePull?.total || 0) > 0
  const progressWidth = hasDeterminateProgress ? `${Math.max(0, Math.min(100, progressPercent))}%` : '35%'

  return (
    <div className="model-manager">
      <div className="sidebar-label">OLLAMA MODELS</div>

      <div className="model-pull-row">
        <input
          className="model-input"
          placeholder="e.g. llama3.2, mistral, deepseek-r1"
          value={pullTag}
          onChange={e => { setPullTag(e.target.value); setPullStatus(null) }}
          onKeyDown={e => e.key === 'Enter' && pullModel()}
          disabled={pulling}
        />
        {!pulling && (
          <button className="btn-accent" disabled={!pullTag.trim()} onClick={pullModel}>
            Pull
          </button>
        )}
        {pulling && (
          <button className="btn-danger" onClick={cancelPull}>
            Cancel
          </button>
        )}
      </div>

      {activePull && activePull.status !== 'idle' && (
        <>
          <div className="model-pull-progress">
            {activePull.message || `Downloading ${activePull.model} — this may take a few minutes…`}
          </div>
          <div className="model-download-card" aria-live="polite">
            <div className="model-download-row">
              <span className="model-name">{activePull.model}</span>
              <span className="model-download-status">
                {activePull.status === 'completed' && 'Completed'}
                {activePull.status === 'failed' && 'Failed'}
                {activePull.status === 'cancelled' && 'Cancelled'}
                {activePull.status === 'cancelling' && 'Cancelling…'}
                {['starting', 'running'].includes(activePull.status) && `${progressPercent.toFixed(1)}%`}
              </span>
            </div>
            <div className="model-download-meta">
              <span>{formatBytes(activePull.completed)} downloaded</span>
              <span>{hasDeterminateProgress ? `${formatBytes(activePull.total)} total` : 'Calculating size…'}</span>
            </div>
            <div className={`model-download-bar ${hasDeterminateProgress ? '' : 'indeterminate'}`} role="progressbar" aria-label={`Downloading ${activePull.model}`} aria-valuemin={0} aria-valuemax={hasDeterminateProgress ? Number(activePull.total || 0) : 100} aria-valuenow={hasDeterminateProgress ? Number(activePull.completed || 0) : undefined}>
              <div className="model-download-bar-fill" style={{ width: progressWidth }} />
            </div>
            {activePull.digest && (
              <div className="model-download-detail">Layer: {activePull.digest}</div>
            )}
            {activePull.error && (
              <div className="model-download-error">{activePull.error}</div>
            )}
          </div>
        </>
      )}

      {pullStatus && (
        <div className={`model-pull-result ${pullStatus.ok ? 'model-pull-result--ok' : 'model-pull-result--err'}`}>
          {pullStatus.msg}
        </div>
      )}

      {loadingModels && !pulling && (
        <div className="sidebar-empty">Checking Ollama models…</div>
      )}
      {!loadingModels && ollamaModels.length === 0 && !pulling && (
        <div className="sidebar-empty">No Ollama models found. Pull one above or start Ollama.</div>
      )}
      {!loadingModels && ollamaModels.map(m => (
        <div key={m.name || m} className="model-item">
          <span className="model-name">{m.name || m}</span>
          <span className="model-size">{m.size ? `${(m.size / 1e9).toFixed(1)} GB` : ''}</span>
        </div>
      ))}

      <div className="sidebar-label" style={{ marginTop: 16 }}>CONFIGURED PROVIDERS</div>
      <div className="model-providers">
        {['openai', 'anthropic', 'google', 'ollama'].map(p => (
          <div key={p} className="provider-row">
            <span className="provider-name">{p}</span>
            <span className="provider-badge">via kendr setup</span>
          </div>
        ))}
      </div>
    </div>
  )
}
