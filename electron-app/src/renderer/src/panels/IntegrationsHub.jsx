import { useState, useEffect, useCallback, useRef } from 'react'
import { useApp } from '../contexts/AppContext'
import MCPPanel from './MCPPanel'
import SkillsPanel from './SkillsPanel'

const TABS = [
  { id: 'overview',     label: '◎ Overview' },
  { id: 'tool-sources', label: '🔌 MCP Servers' },
  { id: 'skills',       label: '⚡ Skills' },
  { id: 'integrations', label: '🧩 Service Integrations' },
]

export default function IntegrationsHub() {
  const [tab, setTab] = useState('overview')

  return (
    <div className="kendr-page">
      <div className="surface-card surface-card--tight">
        <div className="section-header">
          <div>
            <h2>Integrations</h2>
            <p>Everything that extends what your agents can do — in one place.</p>
          </div>
        </div>
        <div className="kendr-tabs">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={`kendr-tab ${tab === item.id ? 'active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'overview'     && <ConnectorOverview onNavigate={setTab} />}
      {tab === 'tool-sources' && <MCPPanel />}
      {tab === 'skills'       && <SkillsPanel />}
      {tab === 'integrations' && <IntegrationsPanel />}
    </div>
  )
}

// ─── Overview tab ─────────────────────────────────────────────────────────────

function ConnectorOverview({ onNavigate }) {
  const { state } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'
  const [catalog, setCatalog]   = useState(null)
  const [loading, setLoading]   = useState(true)
  const [err, setErr]           = useState(null)

  const load = useCallback(async () => {
    setLoading(true); setErr(null)
    try {
      const r = await fetch(`${base}/api/connectors`)
      if (!r.ok) throw new Error(r.statusText)
      setCatalog(await r.json())
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }, [base])

  useEffect(() => { load() }, [load])

  if (loading) return <div className="pp-loading">Loading connector catalog…</div>
  if (err)     return (
    <div className="pp-error-banner">
      ⚠ {err} — Gateway may be offline.
      <button onClick={load} style={{ marginLeft: 8 }}>Retry</button>
    </div>
  )

  const connectors = catalog?.connectors || []
  const byType     = catalog?.by_type    || {}

  const skills    = byType.skill      || []
  const mcpTools  = byType.mcp_tool   || []
  const agents    = byType.task_agent || []
  const integrations = byType.integration || byType.plugin || []

  const ready       = connectors.filter(c => c.status === 'ready').length
  const needsConfig = connectors.filter(c => c.status === 'needs_config').length
  const total       = connectors.length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ── Summary bar ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { label: 'Total Connectors', value: total,          color: 'var(--text)',   bg: 'var(--bg-secondary)' },
          { label: 'Ready',            value: ready,          color: '#27ae60',       bg: '#27ae6010' },
          { label: 'Needs Config',     value: needsConfig,    color: '#e6a700',       bg: '#e6a70010' },
          { label: 'Skills Installed', value: skills.filter(s => s.status === 'ready').length, color: 'var(--accent)', bg: 'var(--accent)10' },
        ].map(({ label, value, color, bg }) => (
          <div key={label} style={{ background: bg, border: '1px solid var(--border)', borderRadius: 10, padding: '14px 18px' }}>
            <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* ── Connector type sections ── */}
      {[
        { key: 'skill',      items: skills,   label: '⚡ Skills',         tab: 'skills',       emptyAction: 'Install skills to give agents reusable capabilities.' },
        { key: 'mcp_tool',   items: mcpTools, label: '🔌 MCP Tools',      tab: 'tool-sources', emptyAction: 'Add an MCP server to expose external tools to your agents.' },
        { key: 'integration', items: integrations, label: '🧩 Service Integrations', tab: 'integrations', emptyAction: 'Configure credentials in the Service Integrations tab.' },
        { key: 'task_agent', items: agents,   label: '🤖 Built-in Agents', tab: null,           emptyAction: null },
      ].map(({ key, items, label, tab, emptyAction }) => (
        <ConnectorSection
          key={key}
          label={label}
          items={items}
          emptyAction={emptyAction}
          onNavigate={tab ? () => onNavigate(tab) : null}
        />
      ))}

      <div style={{ textAlign: 'right', marginTop: 4 }}>
        <button className="pp-btn pp-btn--ghost" onClick={load} style={{ fontSize: 12 }}>↺ Refresh catalog</button>
      </div>
    </div>
  )
}

function ConnectorSection({ label, items, emptyAction, onNavigate }) {
  const [expanded, setExpanded] = useState(true)
  return (
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'visible' }}>
      <div
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 16px', cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setExpanded(e => !e)}
      >
        <span style={{ fontWeight: 600, fontSize: 14 }}>
          {expanded ? '▾' : '▸'} {label}
          <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 400, color: 'var(--text-muted)' }}>{items.length}</span>
        </span>
        {onNavigate && (
          <button
            className="pp-btn pp-btn--ghost"
            style={{ fontSize: 12 }}
            onClick={e => { e.stopPropagation(); onNavigate() }}
          >
            Manage →
          </button>
        )}
      </div>
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 16px' }}>
          {items.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-muted)', padding: '4px 0' }}>
              {emptyAction || 'None configured.'}
              {onNavigate && (
                <button className="pp-btn pp-btn--ghost" style={{ marginLeft: 10, fontSize: 12 }} onClick={onNavigate}>
                  Set up →
                </button>
              )}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
              {items.map(c => <ConnectorCard key={c.agent_name} connector={c} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ConnectorCard({ connector: c }) {
  const [showDetails, setShowDetails] = useState(false)
  const [popoverPos, setPopoverPos] = useState({ top: 0, right: 0 })
  const btnRef = useRef(null)

  const handleInfoClick = () => {
    if (!showDetails && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect()
      setPopoverPos({
        top: rect.bottom + 6,
        right: window.innerWidth - rect.right,
      })
    }
    setShowDetails(v => !v)
  }

  const statusColor = {
    ready:           '#27ae60',
    needs_config:    '#e6a700',
    not_discovered:  '#888',
    disabled:        '#888',
  }[c.status] || '#888'

  const statusLabel = {
    ready:           '✓ Ready',
    needs_config:    '⚙ Setup needed',
    not_discovered:  '○ Not discovered',
    disabled:        '— Disabled',
  }[c.status] || c.status

  const compactDescription = String(c.description || '')
    .replace(/\s+/g, ' ')
    .trim()

  const fullDescription = String(c.description || '').trim()

  return (
    <div className="ih-connector-card" style={{
      border: `1px solid ${c.status === 'ready' ? 'var(--border)' : '#e6a70044'}`,
    }}>
      <div className="ih-connector-card-head">
        <span style={{ fontSize: 18 }}>{c.icon || '•'}</span>
        <span className="ih-connector-card-title">
          {c.display_name}
        </span>
        <button
          ref={btnRef}
          className="ih-connector-card-info-btn"
          title="View full details"
          onClick={handleInfoClick}
        >
          i
        </button>
        <span className="ih-connector-card-status" style={{ color: statusColor }}>{statusLabel}</span>
      </div>
      <div className="ih-connector-card-desc" title={compactDescription}>
        {compactDescription}
      </div>
      {c.missing_config?.length > 0 && (
        <div className="ih-connector-card-missing">
          Missing: {c.missing_config.join(', ')}
        </div>
      )}
      {c.required_inputs?.length > 0 && (
        <div className="ih-connector-card-inputs" title={c.required_inputs.join(', ')}>
          inputs: {c.required_inputs.join(', ')}
        </div>
      )}
      {showDetails && (
        <div className="ih-connector-card-popover" style={{ top: popoverPos.top, right: popoverPos.right }}>
          <div className="ih-connector-card-popover-header">
            <span>Connector Details</span>
            <button className="ih-connector-card-popover-close" onClick={() => setShowDetails(false)}>✕</button>
          </div>
          <div className="ih-connector-card-popover-row"><strong>Name:</strong> {c.display_name || c.agent_name || '-'}</div>
          <div className="ih-connector-card-popover-row"><strong>Status:</strong> {statusLabel}</div>
          <div className="ih-connector-card-popover-row"><strong>Type:</strong> {c.type || '-'}</div>
          <div className="ih-connector-card-popover-row"><strong>Agent:</strong> {c.agent_name || '-'}</div>
          <div className="ih-connector-card-popover-row"><strong>Description:</strong> {fullDescription || '-'}</div>
          <div className="ih-connector-card-popover-row">
            <strong>Inputs:</strong> {c.required_inputs?.length ? c.required_inputs.join(', ') : '-'}
          </div>
          <div className="ih-connector-card-popover-row">
            <strong>Missing Config:</strong> {c.missing_config?.length ? c.missing_config.join(', ') : '-'}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Service integrations tab ────────────────────────────────────────────────

function resolveSetupComponentId(integrationId) {
  const key = String(integrationId || '').trim().toLowerCase()
  const alias = {
    gmail: 'google_workspace',
    google_drive: 'google_workspace',
    microsoft_365: 'microsoft_graph',
    microsoft365: 'microsoft_graph',
    microsoft: 'microsoft_graph',
  }[key]
  return alias || key
}

function integrationIdFromConnector(integration) {
  const explicit = String(integration?.integration_id || integration?.id || '').trim()
  if (explicit) return explicit
  const agentName = String(integration?.agent_name || '').trim()
  if (agentName.startsWith('integration:')) return agentName.slice('integration:'.length)
  return ''
}

function IntegrationsPanel() {
  const { state, dispatch } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'
  const [integrations, setIntegrations] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr]         = useState(null)
  const [providerKeys, setProviderKeys] = useState({})
  const [keysSaved, setKeysSaved] = useState(false)
  const [keysSaving, setKeysSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setErr(null)
    try {
      const r = await fetch(`${base}/api/connectors`)
      if (!r.ok) throw new Error(r.statusText)
      const data = await r.json()
      setIntegrations(data?.by_type?.integration || data?.by_type?.plugin || [])
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }, [base])

  useEffect(() => { load() }, [load])
  useEffect(() => { setProviderKeys(state.settings || {}) }, [state.settings])

  const saveProviderKeys = async () => {
    const api = window.kendrAPI
    if (!api?.settings) return
    const providerSettingKeys = ['anthropicKey', 'openaiKey', 'openaiOrgId', 'googleKey', 'xaiKey']
    const shouldRestartBackend = providerSettingKeys.some(key => (state.settings?.[key] || '') !== (providerKeys?.[key] || ''))
    setKeysSaving(true)
    try {
      for (const [k, v] of Object.entries(providerKeys || {})) {
        if (typeof v === 'string') await api.settings.set(k, v)
      }
      dispatch({ type: 'SET_SETTINGS', settings: providerKeys })
      if (shouldRestartBackend && state.backendStatus === 'running') await api.backend?.restart()
      setKeysSaved(true)
      setTimeout(() => setKeysSaved(false), 1800)
    } finally {
      setKeysSaving(false)
    }
  }

  if (loading) return <div className="pp-loading">Loading service integrations…</div>

  return (
    <div className="pp-root">
      <div className="pp-topbar">
        <div className="pp-topbar-left">
          <span className="pp-page-title">Service Integrations</span>
          <span className="pp-page-sub">External systems your agents can connect to once credentials are configured</span>
        </div>
        <button className="pp-btn pp-btn--ghost" onClick={load}>↺ Refresh</button>
      </div>

      <div className="pp-skills-body">
        {err && (
          <div className="pp-error-banner">⚠ {err} <button onClick={() => setErr(null)}>✕</button></div>
        )}

        <div className="pp-add-card" style={{ maxWidth: 700 }}>
          <div className="pp-add-title">Model & API Keys</div>
          <div className="pp-form-grid" style={{ gridTemplateColumns: '170px 1fr' }}>
            <label className="pp-form-label">Anthropic API Key</label>
            <input className="pp-input" type="password" placeholder="sk-ant-…" value={providerKeys.anthropicKey || ''} onChange={e => setProviderKeys(v => ({ ...v, anthropicKey: e.target.value }))} />

            <label className="pp-form-label">OpenAI API Key</label>
            <input className="pp-input" type="password" placeholder="sk-…" value={providerKeys.openaiKey || ''} onChange={e => setProviderKeys(v => ({ ...v, openaiKey: e.target.value }))} />

            <label className="pp-form-label">OpenAI Org ID</label>
            <input className="pp-input" placeholder="org-…" value={providerKeys.openaiOrgId || ''} onChange={e => setProviderKeys(v => ({ ...v, openaiOrgId: e.target.value }))} />

            <label className="pp-form-label">Google API Key</label>
            <input className="pp-input" type="password" placeholder="AIza…" value={providerKeys.googleKey || ''} onChange={e => setProviderKeys(v => ({ ...v, googleKey: e.target.value }))} />

            <label className="pp-form-label">xAI API Key</label>
            <input className="pp-input" type="password" placeholder="xai-…" value={providerKeys.xaiKey || ''} onChange={e => setProviderKeys(v => ({ ...v, xaiKey: e.target.value }))} />

            <label className="pp-form-label">HuggingFace Token</label>
            <input className="pp-input" type="password" placeholder="hf_…" value={providerKeys.hfToken || ''} onChange={e => setProviderKeys(v => ({ ...v, hfToken: e.target.value }))} />

            <label className="pp-form-label">Tavily Key</label>
            <input className="pp-input" type="password" placeholder="tvly-…" value={providerKeys.tavilyKey || ''} onChange={e => setProviderKeys(v => ({ ...v, tavilyKey: e.target.value }))} />

            <label className="pp-form-label">Brave Key</label>
            <input className="pp-input" type="password" value={providerKeys.braveKey || ''} onChange={e => setProviderKeys(v => ({ ...v, braveKey: e.target.value }))} />

            <label className="pp-form-label">Serper Key</label>
            <input className="pp-input" type="password" value={providerKeys.serperKey || ''} onChange={e => setProviderKeys(v => ({ ...v, serperKey: e.target.value }))} />
          </div>
          <div className="pp-form-actions" style={{ marginTop: 10 }}>
            <button className="pp-btn pp-btn--primary" onClick={saveProviderKeys} disabled={keysSaving}>
              {keysSaving ? 'Saving…' : 'Save API Keys'}
            </button>
            {keysSaved && <span className="pp-form-label" style={{ marginBottom: 0 }}>Saved</span>}
          </div>
        </div>

        {integrations.length === 0 ? (
          <div className="pp-empty">
            <div className="pp-empty-icon">🧩</div>
            <div className="pp-empty-title">No service integrations found</div>
            <div className="pp-empty-sub">Service integrations are exposed by the Kendr backend. Make sure the gateway is running.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {['ready', 'needs_config'].map(status => {
              const group = integrations.filter(p => p.status === status)
              if (!group.length) return null
              return (
                <div key={status}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {status === 'ready' ? '✓ Configured' : '⚙ Needs Configuration'}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
                    {group.map(p => (
                      <IntegrationCard
                        key={p.agent_name}
                        integration={p}
                        base={base}
                        onSaved={load}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function IntegrationCard({ integration: p, base, onSaved }) {
  const configured = p.status === 'ready'
  const [expanded, setExpanded] = useState(false)
  const [formLoading, setFormLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState(null)
  const [fields, setFields] = useState(null)
  const [values, setValues] = useState({})
  const [componentId, setComponentId] = useState('')
  const [oauthPath, setOauthPath] = useState(null)
  const [hint, setHint] = useState(null)

  const openForm = async () => {
    if (expanded) { setExpanded(false); return }
    setExpanded(true)
    if (fields !== null) { setFormLoading(false); return }
    setFormLoading(true)
    setErr(null)

    const rawId = integrationIdFromConnector(p)
    const cid = resolveSetupComponentId(rawId)
    setComponentId(cid)

    let loaded = false
    if (cid) {
      try {
        const r = await fetch(`${base}/api/setup/component/${encodeURIComponent(cid)}`)
        const data = await r.json().catch(() => ({}))
        if (r.ok && !data.error && data.component?.fields?.length) {
          const raw = (data.raw_values && typeof data.raw_values === 'object') ? data.raw_values : {}
          const initVals = {}
          for (const f of data.component.fields) {
            const k = String(f.key || '').trim()
            if (k) initVals[k] = String(raw[k] ?? '')
          }
          setFields(data.component.fields)
          setValues(initVals)
          setOauthPath(data.component.oauth_start_path || null)
          setHint(data.component.description || data.component.setup_hint || null)
          loaded = true
        }
      } catch (_) { /* fall through to fallback */ }
    }

    if (!loaded) {
      // Fallback: render inputs for each missing_config key
      const missing = p.missing_config || []
      setFields(missing.map(k => ({ key: k, label: k, secret: true, required: true })))
      setValues(Object.fromEntries(missing.map(k => [k, ''])))
    }

    setFormLoading(false)
  }

  const save = async () => {
    setSaving(true)
    setErr(null)
    try {
      const r = await fetch(`${base}/api/setup/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ component_id: componentId || integrationIdFromConnector(p), values }),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok || data.error) throw new Error(data.error || r.statusText)
      setSaved(true)
      setTimeout(() => setSaved(false), 1800)
      await onSaved?.()
      setExpanded(false)
      setFields(null)
    } catch (e) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      background: 'var(--bg-secondary)',
      border: `1px solid ${configured ? 'var(--border)' : expanded ? '#e6a70066' : '#e6a70033'}`,
      borderRadius: 10,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      {/* Card header */}
      <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 24, lineHeight: 1 }}>{p.icon}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: 14 }}>{p.display_name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{p.category}</div>
          </div>
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 4, flexShrink: 0,
            background: configured ? '#27ae6015' : '#e6a70015',
            color: configured ? '#27ae60' : '#e6a700',
            border: `1px solid ${configured ? '#27ae6044' : '#e6a70044'}`,
            fontWeight: 600,
          }}>
            {configured ? '✓ Ready' : '⚙ Setup needed'}
          </span>
        </div>

        <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>
          {p.description}
        </div>

        {p.missing_config?.length > 0 && !expanded && (
          <div style={{ fontSize: 11, color: '#e6a700', fontFamily: 'var(--font-mono)' }}>
            Missing: {p.missing_config.join(', ')}
          </div>
        )}

        {p.metadata?.required_env_vars?.length > 0 && configured && (
          <div style={{ fontSize: 11, color: '#27ae60' }}>
            ✓ {p.metadata.required_env_vars.length} credential{p.metadata.required_env_vars.length !== 1 ? 's' : ''} configured
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="pp-btn pp-btn--ghost" style={{ fontSize: 12 }} onClick={openForm}>
            {expanded ? 'Cancel' : configured ? 'Manage Credentials' : 'Set Up →'}
          </button>
        </div>
      </div>

      {/* Inline setup form */}
      {expanded && (
        <div style={{ borderTop: '2px solid #e6a700', background: 'var(--bg)', padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
          {formLoading ? (
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading configuration…</div>
          ) : (
            <>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#e6a700' }}>Configure credentials</div>
              {hint && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{hint}</div>
              )}

              {fields?.length === 0 && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>No credentials required for this integration.</div>
              )}

              {fields?.map(field => {
                const k = String(field.key || '').trim()
                if (!k) return null
                return (
                  <div key={k} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <label style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>
                      {field.label || k}{field.required ? ' *' : ''}
                    </label>
                    <input
                      className="pp-input"
                      type={field.secret ? 'password' : 'text'}
                      placeholder={field.placeholder || field.default || ''}
                      value={values[k] || ''}
                      onChange={e => setValues(v => ({ ...v, [k]: e.target.value }))}
                    />
                    {field.hint && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{field.hint}</div>
                    )}
                  </div>
                )
              })}

              {oauthPath && (
                <button
                  className="pp-btn pp-btn--ghost"
                  style={{ alignSelf: 'flex-start', fontSize: 12 }}
                  onClick={() => window.open(`${base}${oauthPath}`, '_blank', 'noopener')}
                >
                  Start OAuth →
                </button>
              )}

              {err && <div style={{ fontSize: 12, color: '#e74c3c' }}>⚠ {err}</div>}

              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 2 }}>
                {saved && <span style={{ fontSize: 12, color: '#27ae60', alignSelf: 'center' }}>Saved</span>}
                <button className="pp-btn pp-btn--ghost" style={{ fontSize: 12 }} onClick={() => setExpanded(false)}>Cancel</button>
                <button className="pp-btn pp-btn--primary" style={{ fontSize: 12 }} onClick={save} disabled={saving}>
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
