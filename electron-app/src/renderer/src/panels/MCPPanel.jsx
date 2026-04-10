import React, { useState, useEffect, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'

export default function MCPPanel() {
  const { state } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'

  const [servers, setServers]     = useState([])
  const [loading, setLoading]     = useState(true)
  const [showAdd, setShowAdd]     = useState(false)
  const [scaffold, setScaffold]   = useState('')
  const [showScaffold, setShowScaffold] = useState(false)
  const [discovering, setDiscovering]   = useState(null)
  const [err, setErr]             = useState(null)

  // New server form
  const [form, setForm] = useState({ name: '', connection: '', type: 'http', description: '', auth_token: '' })
  const [configJson, setConfigJson] = useState('')

  const getServerId = (srv) => srv?.id || srv?.server_id || ''

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${base}/api/mcp/servers`)
      if (!r.ok) throw new Error(r.statusText)
      const data = await r.json()
      setServers(Array.isArray(data) ? data : (data.servers || []))
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }, [base])

  useEffect(() => { load() }, [load])

  const addServer = async () => {
    try {
      const payload = configJson.trim()
        ? { config_json: configJson }
        : form
      if (!configJson.trim() && (!form.name.trim() || !form.connection.trim())) return
      const r = await fetch(`${base}/api/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error || r.statusText)
      setShowAdd(false)
      setForm({ name: '', connection: '', type: 'http', description: '', auth_token: '' })
      setConfigJson('')
      load()
    } catch (e) { setErr(e.message) }
  }

  const removeServer = async (id) => {
    const r = await fetch(`${base}/api/mcp/servers/${id}/remove`, { method: 'POST' })
    const data = await r.json()
    if (!r.ok || data.error) throw new Error(data.error || r.statusText)
    load()
  }

  const toggleServer = async (id, enabled) => {
    const r = await fetch(`${base}/api/mcp/servers/${id}/toggle`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !enabled }),
    })
    const data = await r.json()
    if (!r.ok || data.error) throw new Error(data.error || r.statusText)
    load()
  }

  const discoverTools = async (id) => {
    setDiscovering(id)
    try {
      const r = await fetch(`${base}/api/mcp/servers/${id}/discover`, { method: 'POST' })
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error || r.statusText)
      load()
    } catch (e) { setErr(e.message) }
    finally { setDiscovering(null) }
  }

  const loadScaffold = async () => {
    try {
      const r = await fetch(`${base}/api/mcp/scaffold`)
      const data = await r.json()
      if (!r.ok || data.error) throw new Error(data.error || r.statusText)
      setScaffold(data.code || '')
      setShowScaffold(true)
    } catch (e) { setErr(e.message) }
  }

  const u = (k) => (v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="pp-root">
      {/* Header */}
      <div className="pp-topbar">
        <div className="pp-topbar-left">
          <span className="pp-page-title">MCP Servers</span>
          <span className="pp-page-sub">Connect external tool servers to extend agent capabilities</span>
        </div>
        <div className="pp-topbar-actions">
          <button className="pp-btn pp-btn--ghost" onClick={loadScaffold}>View Scaffold</button>
          <button className="pp-btn pp-btn--primary" onClick={() => setShowAdd(s => !s)}>+ Add Server</button>
        </div>
      </div>

      {err && (
        <div className="pp-error-banner">⚠ {err} <button onClick={() => setErr(null)}>✕</button></div>
      )}

      {/* Add form */}
      {showAdd && (
        <div className="pp-add-card">
          <div className="pp-add-title">Add MCP Server</div>
          <div className="pp-form-grid">
            <label className="pp-form-label">Name *</label>
            <input className="pp-input" placeholder="My Research Server" value={form.name} onChange={e => u('name')(e.target.value)} />

            <label className="pp-form-label">Connection *</label>
            <input className="pp-input" placeholder="http://localhost:8000/mcp  or  python server.py" value={form.connection} onChange={e => u('connection')(e.target.value)} />

            <label className="pp-form-label">Type</label>
            <select className="pp-select" value={form.type} onChange={e => u('type')(e.target.value)}>
              <option value="http">HTTP / SSE</option>
              <option value="stdio">Stdio (shell command)</option>
            </select>

            <label className="pp-form-label">Description</label>
            <input className="pp-input" placeholder="Optional description" value={form.description} onChange={e => u('description')(e.target.value)} />

            <label className="pp-form-label">Auth Token</label>
            <input className="pp-input" type="password" placeholder="Bearer token (optional)" value={form.auth_token} onChange={e => u('auth_token')(e.target.value)} />
          </div>
          <div className="pp-form-actions" style={{ marginTop: 12, marginBottom: 8, justifyContent: 'flex-start' }}>
            <span className="pp-form-label" style={{ marginBottom: 0 }}>Or paste MCP JSON</span>
          </div>
          <textarea
            className="pp-input"
            rows={10}
            placeholder={`{\n  "mcpServers": {\n    "aws-knowledge-mcp-server": {\n      "url": "https://knowledge-mcp.global.api.aws",\n      "type": "http",\n      "disabled": false\n    }\n  }\n}`}
            value={configJson}
            onChange={e => setConfigJson(e.target.value)}
            style={{ width: '100%', resize: 'vertical', minHeight: 200 }}
          />
          <div className="pp-form-actions">
            <button className="pp-btn pp-btn--primary" onClick={addServer} disabled={!configJson.trim() && (!form.name.trim() || !form.connection.trim())}>
              {configJson.trim() ? 'Import JSON' : 'Add Server'}
            </button>
            <button className="pp-btn pp-btn--ghost" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
          <div className="pp-form-hint">
            <strong>HTTP:</strong> Kendr connects as an MCP client to the SSE endpoint. &nbsp;
            <strong>Stdio:</strong> Kendr spawns the command and communicates via stdin/stdout.
          </div>
        </div>
      )}

      {/* Scaffold modal */}
      {showScaffold && (
        <div className="pp-modal-backdrop" onClick={() => setShowScaffold(false)}>
          <div className="pp-modal" onClick={e => e.stopPropagation()}>
            <div className="pp-modal-header">
              <span>FastMCP Server Scaffold</span>
              <button onClick={() => setShowScaffold(false)}>✕</button>
            </div>
            <pre className="pp-scaffold-code">{scaffold || 'Loading…'}</pre>
            <div className="pp-modal-footer">
              <button className="pp-btn pp-btn--primary" onClick={() => navigator.clipboard.writeText(scaffold)}>Copy</button>
            </div>
          </div>
        </div>
      )}

      {/* Server list */}
      {loading ? (
        <div className="pp-loading">Loading MCP servers…</div>
      ) : servers.length === 0 && !showAdd ? (
        <div className="pp-empty">
          <div className="pp-empty-icon">🔌</div>
          <div className="pp-empty-title">No MCP servers connected</div>
          <div className="pp-empty-sub">Add an MCP server to give your agents access to external tools. Click <strong>View Scaffold</strong> to generate a FastMCP server template.</div>
          <button className="pp-btn pp-btn--primary" style={{ marginTop: 16 }} onClick={() => setShowAdd(true)}>+ Add Your First Server</button>
        </div>
      ) : (
        <div className="pp-list">
          {servers.map(srv => (
            <div key={getServerId(srv)} className={`pp-card ${!srv.enabled ? 'pp-card--disabled' : ''}`}>
              <div className="pp-card-top">
                <div className="pp-card-icon">{srv.type === 'stdio' ? '⌨' : '🌐'}</div>
                <div className="pp-card-info">
                  <div className="pp-card-name">
                    {srv.name}
                    <span className={`pp-badge pp-badge--${srv.status || 'unknown'}`}>{srv.status || 'unknown'}</span>
                    {!srv.enabled && <span className="pp-badge pp-badge--disabled">disabled</span>}
                  </div>
                  <div className="pp-card-conn">{srv.connection}</div>
                  {srv.description && <div className="pp-card-desc">{srv.description}</div>}
                  {srv.error && <div className="pp-card-err">⚠ {srv.error}</div>}
                </div>
                <div className="pp-card-meta">
                  <span className="pp-card-type">{srv.type}</span>
                  <span className="pp-card-tools">{srv.tool_count ?? 0} tools</span>
                  {srv.last_discovered && (
                    <span className="pp-card-date">
                      {new Date(srv.last_discovered).toLocaleDateString()}
                    </span>
                  )}
                </div>
                <div className="pp-card-actions">
                  <button
                    className="pp-action-btn"
                    onClick={() => discoverTools(getServerId(srv))}
                    disabled={discovering === getServerId(srv)}
                    title="Discover tools"
                  >
                    {discovering === getServerId(srv) ? '…' : '🔍'}
                  </button>
                  <button
                    className={`pp-action-btn ${srv.enabled ? 'pp-action-btn--on' : ''}`}
                    onClick={async () => {
                      try { await toggleServer(getServerId(srv), srv.enabled) } catch (e) { setErr(e.message) }
                    }}
                    title={srv.enabled ? 'Disable' : 'Enable'}
                  >
                    {srv.enabled ? '●' : '○'}
                  </button>
                  {!srv.is_default && (
                    <button
                      className="pp-action-btn pp-action-btn--danger"
                      onClick={async () => {
                        try { await removeServer(getServerId(srv)) } catch (e) { setErr(e.message) }
                      }}
                      title="Remove"
                    >✕</button>
                  )}
                </div>
              </div>

              {/* Tool chips */}
              {Array.isArray(srv.tools) && srv.tools.length > 0 && (
                <div className="pp-tools">
                  {srv.tools.map(t => (
                    <span key={t.name} className="pp-tool-chip" title={t.description}>
                      {t.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
