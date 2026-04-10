import React, { useState, useEffect, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'

const TYPE_ICONS  = { skill: '⚡', mcp_server: '🔌', api: '🌐', agent: '🤖', tool: '🔧' }
const STATUS_CLS  = { active: 'ok', verified: 'info', draft: 'warn', disabled: 'muted', error: 'err', deprecated: 'muted' }
const TYPES       = ['all', 'agent', 'skill', 'mcp_server', 'api', 'tool']
const STATUSES    = ['all', 'active', 'verified', 'draft', 'disabled', 'error']

export default function AgentsPanel() {
  const { state } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'

  const [caps, setCaps]           = useState([])
  const [agents, setAgents]       = useState([])
  const [loading, setLoading]     = useState(true)
  const [tab, setTab]             = useState('capabilities')  // capabilities | agents | discovery
  const [typeFilter, setTypeFilter]   = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch]       = useState('')
  const [selected, setSelected]   = useState(null)
  const [err, setErr]             = useState(null)
  const [discovery, setDiscovery] = useState(null)

  const loadCaps = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (typeFilter !== 'all')   params.set('type', typeFilter)
      if (statusFilter !== 'all') params.set('status', statusFilter)
      if (search.trim())          params.set('q', search.trim())
      const r = await fetch(`${base}/api/capabilities?${params}`)
      const data = await r.json()
      setCaps(Array.isArray(data) ? data : (data.capabilities || data.items || []))
    } catch (e) { setErr(e.message) }
  }, [base, typeFilter, statusFilter, search])

  const loadAgents = useCallback(async () => {
    try {
      const r = await fetch(`${base}/api/capabilities?type=agent&status=active`)
      const data = await r.json()
      setAgents(Array.isArray(data) ? data : (data.capabilities || []))
    } catch {}
  }, [base])

  const loadDiscovery = useCallback(async () => {
    try {
      const r = await fetch(`${base}/api/capabilities/discovery/cards`)
      const data = await r.json()
      setDiscovery(data)
    } catch {}
  }, [base])

  useEffect(() => {
    setLoading(true)
    Promise.all([loadCaps(), loadAgents()]).finally(() => setLoading(false))
  }, [loadCaps, loadAgents])

  useEffect(() => {
    if (tab === 'discovery' && !discovery) loadDiscovery()
  }, [tab, discovery, loadDiscovery])

  const publishCap = async (id) => {
    await fetch(`${base}/api/capabilities/${id}/publish`, { method: 'POST' })
    loadCaps()
  }
  const disableCap = async (id) => {
    await fetch(`${base}/api/capabilities/${id}/disable`, { method: 'POST' })
    loadCaps()
  }

  const filteredCaps = caps.filter(c => {
    if (search.trim()) {
      const q = search.toLowerCase()
      return (c.name || '').toLowerCase().includes(q) || (c.description || '').toLowerCase().includes(q)
    }
    return true
  })

  return (
    <div className="pp-root">
      <div className="pp-topbar">
        <div className="pp-topbar-left">
          <span className="pp-page-title">Agents & Capabilities</span>
          <span className="pp-page-sub">Manage agents, tools, APIs, and all registered capabilities</span>
        </div>
      </div>

      {err && <div className="pp-error-banner">⚠ {err} <button onClick={() => setErr(null)}>✕</button></div>}

      {/* Tabs */}
      <div className="pp-tabs">
        {[['capabilities','Capabilities'], ['agents','Active Agents'], ['discovery','Discovery Cards']].map(([id, label]) => (
          <button
            key={id}
            className={`pp-tab ${tab === id ? 'active' : ''}`}
            onClick={() => setTab(id)}
          >{label}</button>
        ))}
      </div>

      {/* ── Capabilities tab ── */}
      {tab === 'capabilities' && (
        <>
          <div className="pp-filters">
            <input
              className="pp-search"
              placeholder="Search capabilities…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <select className="pp-select pp-select--sm" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
              {TYPES.map(t => <option key={t} value={t}>{t === 'all' ? 'All types' : t}</option>)}
            </select>
            <select className="pp-select pp-select--sm" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              {STATUSES.map(s => <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>)}
            </select>
          </div>

          {loading ? (
            <div className="pp-loading">Loading capabilities…</div>
          ) : filteredCaps.length === 0 ? (
            <div className="pp-empty">
              <div className="pp-empty-icon">🤖</div>
              <div className="pp-empty-title">No capabilities found</div>
              <div className="pp-empty-sub">Capabilities are auto-discovered from agents, MCP servers, and API integrations.</div>
            </div>
          ) : (
            <div className="pp-cap-layout">
              <div className="pp-cap-list">
                {filteredCaps.map(c => (
                  <div
                    key={c.capability_id}
                    className={`pp-cap-row ${selected?.capability_id === c.capability_id ? 'selected' : ''}`}
                    onClick={() => setSelected(c)}
                  >
                    <span className="pp-cap-icon">{TYPE_ICONS[c.type] || '📦'}</span>
                    <div className="pp-cap-row-info">
                      <span className="pp-cap-row-name">{c.name}</span>
                      <span className="pp-cap-row-key">{c.capability_key}</span>
                    </div>
                    <span className={`pp-badge pp-badge--${STATUS_CLS[c.status] || 'muted'}`}>{c.status}</span>
                    <span className="pp-cap-row-type">{c.type}</span>
                  </div>
                ))}
              </div>

              {/* Detail panel */}
              {selected ? (
                <div className="pp-cap-detail">
                  <div className="pp-detail-header">
                    <span className="pp-detail-icon">{TYPE_ICONS[selected.type] || '📦'}</span>
                    <div>
                      <div className="pp-detail-name">{selected.name}</div>
                      <div className="pp-detail-key">{selected.capability_key}</div>
                    </div>
                    <span className={`pp-badge pp-badge--${STATUS_CLS[selected.status] || 'muted'}`}>{selected.status}</span>
                  </div>
                  <div className="pp-detail-desc">{selected.description || 'No description.'}</div>
                  <div className="pp-detail-meta">
                    <MetaRow label="Type"       value={selected.type} />
                    <MetaRow label="Version"    value={selected.version} />
                    <MetaRow label="Visibility" value={selected.visibility} />
                    <MetaRow label="Health"     value={selected.health_status || '—'} />
                    <MetaRow label="Owner"      value={selected.owner_user_id || '—'} />
                  </div>
                  {selected.tags_json && (() => {
                    try {
                      const tags = JSON.parse(selected.tags_json)
                      return tags.length ? (
                        <div className="pp-detail-tags">
                          {tags.map(t => <span key={t} className="pp-tool-chip">{t}</span>)}
                        </div>
                      ) : null
                    } catch { return null }
                  })()}
                  <div className="pp-detail-actions">
                    {selected.status === 'draft' && (
                      <button className="pp-btn pp-btn--primary" onClick={() => publishCap(selected.capability_id)}>Publish</button>
                    )}
                    {selected.status === 'active' && (
                      <button className="pp-btn pp-btn--danger" onClick={() => disableCap(selected.capability_id)}>Disable</button>
                    )}
                    <button className="pp-btn pp-btn--ghost" onClick={() => setSelected(null)}>Close</button>
                  </div>
                </div>
              ) : (
                <div className="pp-cap-detail pp-cap-detail--empty">
                  <span>Select a capability to view details</span>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Active Agents tab ── */}
      {tab === 'agents' && (
        <div className="pp-agents-grid">
          {agents.length === 0 ? (
            <div className="pp-empty">
              <div className="pp-empty-icon">🤖</div>
              <div className="pp-empty-title">No active agents</div>
            </div>
          ) : agents.map(a => (
            <div key={a.capability_id} className="pp-agent-card">
              <div className="pp-agent-card-icon">🤖</div>
              <div className="pp-agent-card-name">{a.name}</div>
              <div className="pp-agent-card-desc">{(a.description || '').slice(0, 100)}</div>
              <div className="pp-agent-card-footer">
                <span className={`pp-badge pp-badge--${STATUS_CLS[a.status] || 'muted'}`}>{a.status}</span>
                {a.tags_json && (() => {
                  try {
                    return JSON.parse(a.tags_json).slice(0, 3).map(t => (
                      <span key={t} className="pp-tool-chip pp-tool-chip--sm">{t}</span>
                    ))
                  } catch { return null }
                })()}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Discovery tab ── */}
      {tab === 'discovery' && (
        <div className="pp-discovery">
          {!discovery ? (
            <div className="pp-loading">Loading discovery cards…</div>
          ) : (
            <div className="pp-agents-grid">
              {(Array.isArray(discovery) ? discovery : (discovery.cards || [])).map((card, i) => (
                <div key={i} className={`pp-agent-card ${card.is_active === false ? 'pp-agent-card--inactive' : ''}`}>
                  <div className="pp-agent-card-icon">{card.is_active ? '✅' : '⚙'}</div>
                  <div className="pp-agent-card-name">{card.display_name || card.agent_name}</div>
                  <div className="pp-agent-card-desc">{(card.description || '').slice(0, 120)}</div>
                  {card.needs_config && (
                    <div className="pp-agent-card-warn">
                      ⚠ Needs config: {(card.missing_vars || []).join(', ')}
                    </div>
                  )}
                  <div className="pp-agent-card-footer">
                    <span className={`pp-badge ${card.is_active ? 'pp-badge--ok' : 'pp-badge--warn'}`}>
                      {card.is_active ? 'active' : 'inactive'}
                    </span>
                    {card.category && <span className="pp-tool-chip pp-tool-chip--sm">{card.category}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function MetaRow({ label, value }) {
  return (
    <div className="pp-meta-row">
      <span className="pp-meta-label">{label}</span>
      <span className="pp-meta-value">{value}</span>
    </div>
  )
}
