import React, { useEffect, useMemo, useState } from 'react'
import { useApp } from '../contexts/AppContext'

const capabilityLabel = (value) => (value ? 'Yes' : 'No')

export default function ModelDocs() {
  const { state } = useApp()
  const apiBase = state.backendUrl || 'http://127.0.0.1:2151'
  const [inventory, setInventory] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadInventory = React.useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    fetch(`${apiBase}/api/models`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
      .then(d => {
        if (cancelled) return
        setInventory(d)
        setLoading(false)
      })
      .catch(err => {
        if (cancelled) return
        setError(err?.message || 'Failed to load model inventory')
        setLoading(false)
      })
    return () => { cancelled = true }
  }, [apiBase])

  useEffect(() => {
    const cleanup = loadInventory()
    return cleanup
  }, [loadInventory])

  const rows = useMemo(() => {
    const providers = Array.isArray(inventory?.providers) ? inventory.providers : []
    return providers.filter(provider => provider.has_key || provider.provider === 'ollama')
  }, [inventory])

  return (
    <div className="md-root">
      <div className="md-hero">
        <div>
          <div className="md-eyebrow">Reference</div>
          <h2 className="md-title">Model Comparison</h2>
          <p className="md-subtitle">
            Comparison for the providers currently configured in Kendr. Capability flags are best-effort product hints for the configured model.
          </p>
        </div>
        <button className="md-refresh" onClick={loadInventory}>Reload</button>
      </div>

      {loading && <div className="md-state">Loading model inventory…</div>}
      {!loading && error && <div className="md-state md-state--error">{error}</div>}
      {!loading && !error && rows.length === 0 && (
        <div className="md-state">No configured providers yet. Add a model API key in Settings to populate this table.</div>
      )}

      {!loading && !error && rows.length > 0 && (
        <div className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Configured Model</th>
                <th>Status</th>
                <th>Context</th>
                <th>Tool Calling</th>
                <th>Vision</th>
                <th>Structured Output</th>
                <th>Reasoning</th>
                <th>Suggested Latest</th>
                <th>Suggested Best</th>
                <th>Suggested Cheapest</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((provider) => {
                const badges = provider.model_badges || {}
                const latest = Object.keys(badges).find(model => badges[model]?.includes('latest')) || '—'
                const best = Object.keys(badges).find(model => badges[model]?.includes('best')) || '—'
                const cheapest = Object.keys(badges).find(model => badges[model]?.includes('cheapest')) || '—'
                const capabilities = provider.model_capabilities || {}
                const status = provider.model_fetch_error
                  ? `Error: ${provider.model_fetch_error}`
                  : provider.ready
                    ? 'Ready'
                    : provider.note || 'Not ready'

                return (
                  <tr key={provider.provider}>
                    <td>{provider.provider}</td>
                    <td>
                      <div className="md-model-cell">
                        <span>{provider.model || '—'}</span>
                        {provider.model_badges?.[provider.model]?.map(badge => (
                          <span key={`${provider.provider}:${provider.model}:${badge}`} className={`md-chip ${badge}`}>{badge}</span>
                        ))}
                      </div>
                    </td>
                    <td className={provider.model_fetch_error ? 'md-error-text' : ''}>{status}</td>
                    <td>{provider.context_window ? `${provider.context_window.toLocaleString()} tokens` : '—'}</td>
                    <td>{capabilityLabel(capabilities.tool_calling)}</td>
                    <td>{capabilityLabel(capabilities.vision)}</td>
                    <td>{capabilityLabel(capabilities.structured_output)}</td>
                    <td>{capabilityLabel(capabilities.reasoning)}</td>
                    <td>{latest}</td>
                    <td>{best}</td>
                    <td>{cheapest}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
