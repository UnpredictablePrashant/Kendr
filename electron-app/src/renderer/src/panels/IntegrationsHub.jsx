import { useState, useEffect, useCallback } from 'react'
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
    <div style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
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

  return (
    <div style={{
      background: 'var(--bg)',
      border: `1px solid ${c.status === 'ready' ? 'var(--border)' : '#e6a70044'}`,
      borderRadius: 8,
      padding: '10px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 18 }}>{c.icon || '•'}</span>
        <span style={{ fontWeight: 600, fontSize: 13, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {c.display_name}
        </span>
        <span style={{ fontSize: 11, color: statusColor, fontWeight: 500, flexShrink: 0 }}>{statusLabel}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{c.description}</div>
      {c.missing_config?.length > 0 && (
        <div style={{ fontSize: 11, color: '#e6a700', marginTop: 2 }}>
          Missing: {c.missing_config.join(', ')}
        </div>
      )}
      {c.required_inputs?.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace', marginTop: 2 }}>
          inputs: {c.required_inputs.join(', ')}
        </div>
      )}
    </div>
  )
}

// ─── Service integrations tab ────────────────────────────────────────────────

function IntegrationsPanel() {
  const { state } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'
  const [integrations, setIntegrations] = useState([])
  const [loading, setLoading] = useState(true)
  const [err, setErr]         = useState(null)

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

      {err && (
        <div className="pp-error-banner">⚠ {err} <button onClick={() => setErr(null)}>✕</button></div>
      )}

      {integrations.length === 0 ? (
        <div className="pp-empty">
          <div className="pp-empty-icon">🧩</div>
          <div className="pp-empty-title">No service integrations found</div>
          <div className="pp-empty-sub">Service integrations are exposed by the Kendr backend. Make sure the gateway is running.</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Group by status */}
          {['ready', 'needs_config'].map(status => {
            const group = integrations.filter(p => p.status === status)
            if (!group.length) return null
            return (
              <div key={status}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  {status === 'ready' ? '✓ Configured' : '⚙ Needs Configuration'}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
                  {group.map(p => <IntegrationCard key={p.agent_name} integration={p} />)}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div style={{ marginTop: 24, padding: '14px 16px', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 10, fontSize: 13, color: 'var(--text-muted)' }}>
        💡 To configure an integration, set the required environment variables in{' '}
        <strong>Settings → API Keys</strong>, then restart the backend.
      </div>
    </div>
  )
}

function IntegrationCard({ integration: p }) {
  const configured = p.status === 'ready'
  return (
    <div style={{
      background: 'var(--bg-secondary)',
      border: `1px solid ${configured ? 'var(--border)' : '#e6a70033'}`,
      borderRadius: 10,
      padding: '14px 16px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 24, lineHeight: 1 }}>{p.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{p.display_name}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{p.category}</div>
        </div>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 4,
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

      {p.missing_config?.length > 0 && (
        <div style={{ background: '#e6a70010', border: '1px solid #e6a70033', borderRadius: 6, padding: '8px 10px', fontSize: 12 }}>
          <div style={{ fontWeight: 600, color: '#e6a700', marginBottom: 4 }}>Required environment variables:</div>
          {p.missing_config.map(v => (
            <div key={v} style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              • {v}
            </div>
          ))}
        </div>
      )}

      {p.metadata?.required_env_vars?.length > 0 && configured && (
        <div style={{ fontSize: 11, color: '#27ae60', display: 'flex', alignItems: 'center', gap: 4 }}>
          ✓ {p.metadata.required_env_vars.length} credential{p.metadata.required_env_vars.length !== 1 ? 's' : ''} configured
        </div>
      )}
    </div>
  )
}
