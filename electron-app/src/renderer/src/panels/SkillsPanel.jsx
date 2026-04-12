import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useApp } from '../contexts/AppContext'

// ─── helpers ────────────────────────────────────────────────────────────────

function groupBy(arr, key) {
  return arr.reduce((acc, item) => {
    const k = item[key] || 'Other'
    if (!acc[k]) acc[k] = []
    acc[k].push(item)
    return acc
  }, {})
}

function sandboxPresentation(sandbox) {
  const mode = String(sandbox?.mode || '').trim().toLowerCase()
  if (mode === 'bubblewrap') return { label: 'Sandboxed', tone: 'ok' }
  if (mode === 'blocked') return { label: 'Blocked', tone: 'err' }
  if (mode === 'process_isolated_only') return { label: 'Process only', tone: 'warn' }
  if (mode === 'configurable') return { label: 'Configurable', tone: 'warn' }
  if (mode === 'full_access') return { label: 'Full access', tone: 'err' }
  if (mode === 'in_process') return { label: 'No sandbox', tone: 'muted' }
  return { label: 'Unknown', tone: 'muted' }
}

function badgeStyle(tone) {
  if (tone === 'ok') return { background: '#27ae6018', color: '#27ae60', border: '1px solid #27ae6044' }
  if (tone === 'warn') return { background: '#f39c1218', color: '#d68910', border: '1px solid #f39c1244' }
  if (tone === 'err') return { background: '#e74c3c18', color: '#e74c3c', border: '1px solid #e74c3c44' }
  return { background: 'var(--bg)', color: 'var(--text-muted)', border: '1px solid var(--border)' }
}

function SandboxBadge({ sandbox }) {
  const visual = sandboxPresentation(sandbox)
  return (
    <span style={{ fontSize: 11, padding: '1px 7px', borderRadius: 4, fontWeight: 600, ...badgeStyle(visual.tone) }}>
      {visual.label}
    </span>
  )
}

function SandboxDetail({ sandbox, compact = false }) {
  if (!sandbox) return null
  const reason = String(sandbox.reason || '').trim()
  const installHint = String(sandbox.install_hint || '').trim()
  const mode = String(sandbox.mode || '').trim().toLowerCase()
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <SandboxBadge sandbox={sandbox} />
        {sandbox.provider && sandbox.provider !== 'none' && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{sandbox.provider}</span>
        )}
      </div>
      {!compact && reason && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.45 }}>{reason}</div>
      )}
      {!compact && installHint && (mode === 'blocked' || mode === 'process_isolated_only') && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.45 }}>{installHint}</div>
      )}
    </div>
  )
}

function RuntimeSandboxBanner({ runtime }) {
  if (!runtime || runtime.available) return null
  return (
    <div
      style={{
        background: 'rgba(243,156,18,.10)',
        border: '1px solid rgba(243,156,18,.28)',
        borderRadius: 10,
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>Sandbox limited</span>
        <SandboxBadge sandbox={{ mode: runtime.supported ? 'blocked' : 'process_isolated_only' }} />
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        {runtime.reason || 'Sandbox support is not fully available in this environment.'}
      </div>
      {runtime.install_hint && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
          {runtime.install_hint}
        </div>
      )}
    </div>
  )
}

function _safeJsonParse(value) {
  try { return JSON.parse(value) } catch { return null }
}

function _defaultDesktopForm() {
  return {
    action: 'list_apps',
    app: 'generic',
    access_mode: 'sandbox',
    app_name: '',
    office_app: 'outlook',
    phone_number: '',
    handle: '',
    message: '',
    document_path: '',
    url: '',
    timeout: 10,
  }
}

function _desktopFormFromInputs(inputs) {
  const source = (inputs && typeof inputs === 'object') ? inputs : {}
  return {
    ..._defaultDesktopForm(),
    action: String(source.action || 'list_apps'),
    app: String(source.app || 'generic'),
    access_mode: String(source.access_mode || 'sandbox'),
    app_name: String(source.app_name || ''),
    office_app: String(source.office_app || 'outlook'),
    phone_number: String(source.phone_number || ''),
    handle: String(source.handle || ''),
    message: String(source.message || ''),
    document_path: String(source.document_path || ''),
    url: String(source.url || ''),
    timeout: Number.isFinite(Number(source.timeout)) ? Number(source.timeout) : 10,
  }
}

function _desktopInputsFromForm(form) {
  const source = form || _defaultDesktopForm()
  const action = String(source.action || 'list_apps')
  const app = String(source.app || 'generic')
  const payload = {
    action,
    app,
    access_mode: String(source.access_mode || 'sandbox'),
  }
  const timeout = Number(source.timeout)
  if (Number.isFinite(timeout) && timeout > 0) payload.timeout = timeout
  if (action === 'open_app') {
    if (app === 'generic' && String(source.app_name || '').trim()) payload.app_name = String(source.app_name).trim()
    if (app === 'microsoft_365' && String(source.office_app || '').trim()) payload.office_app = String(source.office_app).trim()
  }
  if (action === 'open_chat') {
    if (app === 'whatsapp' && String(source.phone_number || '').trim()) payload.phone_number = String(source.phone_number).trim()
    if (app === 'telegram' && String(source.handle || '').trim()) payload.handle = String(source.handle).trim()
    if (String(source.message || '').trim()) payload.message = String(source.message).trim()
  }
  if (action === 'open_document' && String(source.document_path || '').trim()) {
    payload.document_path = String(source.document_path).trim()
  }
  if (action === 'open_url' && String(source.url || '').trim()) {
    payload.url = String(source.url).trim()
  }
  return payload
}

// ─── root panel ─────────────────────────────────────────────────────────────

export default function SkillsPanel() {
  const { state } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'

  const [tab, setTab]               = useState('all')   // 'all' | 'installed'
  const [data, setData]             = useState(null)    // marketplace payload
  const [loading, setLoading]       = useState(true)
  const [err, setErr]               = useState(null)
  const [search, setSearch]         = useState('')
  const [category, setCategory]     = useState('')

  const [createOpen, setCreateOpen] = useState(false)
  const [testSkill, setTestSkill]   = useState(null)   // skill row to test
  const [actionBusy, setActionBusy] = useState(null)   // catalog_id being actioned

  const load = useCallback(async () => {
    setLoading(true); setErr(null)
    try {
      const params = new URLSearchParams()
      if (search) params.set('q', search)
      if (category) params.set('category', category)
      const r = await fetch(`${base}/api/marketplace/skills?${params}`)
      if (!r.ok) throw new Error(r.statusText)
      setData(await r.json())
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }, [base, search, category])

  useEffect(() => { load() }, [load])

  const handleInstall = async (catalogId) => {
    setActionBusy(catalogId)
    try {
      const r = await fetch(`${base}/api/marketplace/skills/${catalogId}/install`, { method: 'POST' })
      if (!r.ok) throw new Error((await r.json()).error || r.statusText)
      await load()
    } catch (e) { setErr(e.message) }
    finally { setActionBusy(null) }
  }

  const handleUninstall = async (catalogId) => {
    setActionBusy(catalogId)
    try {
      const r = await fetch(`${base}/api/marketplace/skills/${catalogId}/uninstall`, { method: 'POST' })
      if (!r.ok) throw new Error((await r.json()).error || r.statusText)
      await load()
    } catch (e) { setErr(e.message) }
    finally { setActionBusy(null) }
  }

  const handleDeleteCustom = async (skillId) => {
    if (!confirm('Delete this skill?')) return
    try {
      const r = await fetch(`${base}/api/marketplace/skills/${skillId}/delete`, { method: 'POST' })
      if (!r.ok) throw new Error((await r.json()).error || r.statusText)
      await load()
    } catch (e) { setErr(e.message) }
  }

  const catalog = data?.catalog || []
  const custom  = data?.custom  || []
  const categories = data?.categories || []
  const installedCount = data?.installed_count ?? 0
  const sandboxRuntime = data?.sandbox_runtime || null

  // Filter logic
  const filteredCatalog = catalog.filter(s => {
    if (tab === 'installed' && !s.is_installed) return false
    return true
  })
  const filteredCustom = custom.filter(s => {
    if (tab === 'installed' && !s.is_installed) return false
    return true
  })

  // Group catalog by category
  const grouped = groupBy(filteredCatalog, 'category')
  const catOrder = ['Recommended', 'Development', 'Research', 'Documents', 'Communication', 'Data']
  const sortedCats = [
    ...catOrder.filter(c => grouped[c]),
    ...Object.keys(grouped).filter(c => !catOrder.includes(c)).sort(),
  ]

  return (
    <div className="pp-root">
      {/* ── Header ── */}
      <div className="pp-topbar">
        <div className="pp-topbar-left">
          <span className="pp-page-title">Skills</span>
          <span className="pp-page-sub">Make Kendr work your way</span>
        </div>
        <div className="pp-topbar-actions">
          {installedCount > 0 && (
            <span className="pp-badge pp-badge--ok">{installedCount} installed</span>
          )}
          {sandboxRuntime && (
            <span className={`pp-badge ${sandboxRuntime.available ? 'pp-badge--ok' : 'pp-badge--warn'}`}>
              {sandboxRuntime.available ? 'Sandbox ready' : 'Sandbox limited'}
            </span>
          )}
          <button className="pp-btn pp-btn--ghost" onClick={load}>↺ Refresh</button>
          <button
            className="pp-btn pp-btn--primary"
            onClick={() => setCreateOpen(true)}
            style={{ background: 'var(--accent)', color: '#fff', border: 'none', padding: '5px 14px', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}
          >
            + Create
          </button>
        </div>
      </div>

      {err && (
        <div className="pp-error-banner">
          ⚠ {err}
          <button onClick={() => setErr(null)}>✕</button>
        </div>
      )}

      <RuntimeSandboxBanner runtime={sandboxRuntime} />

      {/* ── Tabs + Search ── */}
      <div className="pp-filters" style={{ gap: 8 }}>
        {[['all', 'All Skills'], ['installed', 'Installed']].map(([val, label]) => (
          <button
            key={val}
            className={`pp-tab ${tab === val ? 'active' : ''}`}
            style={{ padding: '5px 14px', borderBottom: 'none', borderRadius: 6, border: `1px solid ${tab === val ? 'var(--accent)' : 'var(--border)'}`, fontWeight: tab === val ? 600 : 400 }}
            onClick={() => setTab(val)}
          >{label}</button>
        ))}
        <input
          className="pp-search"
          placeholder="Search skills…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ flex: 1 }}
        />
        {categories.length > 0 && (
          <select
            value={category}
            onChange={e => setCategory(e.target.value)}
            style={{ background: 'var(--bg-secondary)', color: 'var(--text)', border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px', fontSize: 13 }}
          >
            <option value="">All Categories</option>
            {categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
      </div>

      {/* ── Body ── */}
      {loading ? (
        <div className="pp-loading">Loading skills…</div>
      ) : (
        <div className="pp-skills-body">

          {/* Custom skills section (if any) */}
          {filteredCustom.length > 0 && (
            <SkillSection title="Personal" emoji="✨">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                {filteredCustom.map(skill => (
                  <CustomSkillCard
                    key={skill.skill_id}
                    skill={skill}
                    onTest={() => setTestSkill(skill)}
                    onDelete={() => handleDeleteCustom(skill.skill_id)}
                  />
                ))}
              </div>
            </SkillSection>
          )}

          {/* Catalog sections by category */}
          {sortedCats.length === 0 && filteredCustom.length === 0 ? (
            <div className="pp-empty">
              <div className="pp-empty-icon">⚡</div>
              <div className="pp-empty-title">No skills found</div>
              <div className="pp-empty-sub">Try a different search or create your own skill.</div>
            </div>
          ) : sortedCats.map(cat => (
            <SkillSection key={cat} title={cat} emoji={CAT_EMOJI[cat] || '🔧'}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                {grouped[cat].map(skill => (
                  <CatalogSkillCard
                    key={skill.id}
                    skill={skill}
                    busy={actionBusy === skill.id}
                    onInstall={() => handleInstall(skill.id)}
                    onUninstall={() => handleUninstall(skill.id)}
                    onTest={skill.is_installed && skill.skill_id
                      ? () => setTestSkill({ ...skill, skill_id: skill.skill_id })
                      : null}
                  />
                ))}
              </div>
            </SkillSection>
          ))}
        </div>
      )}

      {/* ── Modals ── */}
      {createOpen && (
        <CreateSkillModal
          base={base}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); load() }}
        />
      )}
      {testSkill && (
        <TestSkillModal
          base={base}
          skill={testSkill}
          onClose={() => setTestSkill(null)}
        />
      )}
    </div>
  )
}

// ─── category emoji map ──────────────────────────────────────────────────────

const CAT_EMOJI = {
  Recommended: '⭐',
  Development: '💻',
  Research: '🔬',
  Documents: '📄',
  Communication: '💬',
  Data: '📊',
  Custom: '✨',
}

// ─── section wrapper ─────────────────────────────────────────────────────────

function SkillSection({ title, emoji, children }) {
  return (
    <div className="pp-cat-section" style={{ marginBottom: 24 }}>
      <div className="pp-cat-header" style={{ marginBottom: 12 }}>
        <span className="pp-cat-name">{emoji} {title}</span>
      </div>
      {children}
    </div>
  )
}

// ─── catalog skill card ──────────────────────────────────────────────────────

function CatalogSkillCard({ skill, busy, onInstall, onUninstall, onTest }) {
  const installed = skill.is_installed
  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: `1px solid ${installed ? 'var(--accent)' : 'var(--border)'}`,
        borderRadius: 10,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        opacity: busy ? 0.7 : 1,
        transition: 'border-color 0.2s',
      }}
    >
      {/* top row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 26, lineHeight: 1 }}>{skill.icon || '🔧'}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 2 }}>{skill.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{skill.description}</div>
        </div>
        {/* install / uninstall button */}
        <div style={{ flexShrink: 0 }}>
          {installed ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' }}>
              <span style={{ fontSize: 11, color: 'var(--accent)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 3 }}>
                ✓ Installed
              </span>
              {onTest && (
                <button
                  onClick={onTest}
                  style={{ fontSize: 11, padding: '2px 8px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-muted)', cursor: 'pointer' }}
                >
                  Test
                </button>
              )}
              <button
                onClick={onUninstall}
                disabled={busy}
                style={{ fontSize: 11, padding: '2px 8px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-muted)', cursor: 'pointer' }}
              >
                {busy ? '…' : 'Remove'}
              </button>
            </div>
          ) : (
            <button
              onClick={onInstall}
              disabled={busy}
              style={{
                width: 28, height: 28, borderRadius: '50%',
                background: 'var(--bg)', border: '1px solid var(--border)',
                fontSize: 18, lineHeight: '28px', textAlign: 'center',
                cursor: busy ? 'not-allowed' : 'pointer', color: 'var(--text)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
              title="Install skill"
            >
              {busy ? '…' : '+'}
            </button>
          )}
        </div>
      </div>

      {/* tags */}
      {skill.tags?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {skill.tags.slice(0, 4).map((t, i) => (
            <span key={i} className="pp-intent-chip" style={{ fontSize: 11 }}>{t}</span>
          ))}
        </div>
      )}

      {/* requires config */}
      {skill.requires_config?.length > 0 && (
        <div style={{ fontSize: 11, color: 'var(--warn, #e6a700)', display: 'flex', alignItems: 'center', gap: 4 }}>
          ⚙ Requires: {skill.requires_config.join(', ')}
        </div>
      )}

      <SandboxDetail sandbox={skill.sandbox} compact />
    </div>
  )
}

// ─── custom skill card ───────────────────────────────────────────────────────

function CustomSkillCard({ skill, onTest, onDelete }) {
  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 10,
        padding: '14px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ fontSize: 26, lineHeight: 1 }}>{skill.icon || '⚡'}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 2 }}>{skill.name}</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.4 }}>{skill.description || 'No description.'}</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end', flexShrink: 0 }}>
          <span style={{ fontSize: 11, padding: '2px 7px', background: 'var(--bg)', borderRadius: 4, border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
            {skill.skill_type}
          </span>
          <button
            onClick={onTest}
            style={{ fontSize: 11, padding: '2px 8px', background: 'transparent', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-muted)', cursor: 'pointer' }}
          >Test</button>
          <button
            onClick={onDelete}
            style={{ fontSize: 11, padding: '2px 8px', background: 'transparent', border: '1px solid #c0392b44', borderRadius: 4, color: '#e74c3c', cursor: 'pointer' }}
          >Delete</button>
        </div>
      </div>
      {skill.tags?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {skill.tags.slice(0, 4).map((t, i) => (
            <span key={i} className="pp-intent-chip" style={{ fontSize: 11 }}>{t}</span>
          ))}
        </div>
      )}
      <SandboxDetail sandbox={skill.sandbox} compact />
    </div>
  )
}

// ─── create skill modal ──────────────────────────────────────────────────────

const STARTER_PYTHON = `# Available variables:
#   inputs (dict)  — the inputs passed to this skill
#   output         — set this to your result
#
# Example:
query = inputs.get('query', '')
output = f"Processed: {query.upper()}"
`

const STARTER_PROMPT = `You are a helpful assistant.

User query: {query}

Respond with a concise, accurate answer.
`

function CreateSkillModal({ base, onClose, onCreated }) {
  const [name, setName]         = useState('')
  const [desc, setDesc]         = useState('')
  const [category, setCategory] = useState('Custom')
  const [icon, setIcon]         = useState('⚡')
  const [type, setType]         = useState('python')  // 'python' | 'prompt'
  const [code, setCode]         = useState(STARTER_PYTHON)
  const [tags, setTags]         = useState('')
  const [err, setErr]           = useState(null)
  const [busy, setBusy]         = useState(false)

  useEffect(() => {
    setCode(type === 'python' ? STARTER_PYTHON : STARTER_PROMPT)
  }, [type])

  const submit = async () => {
    if (!name.trim()) { setErr('Name is required.'); return }
    if (!code.trim()) { setErr('Code / prompt is required.'); return }
    setBusy(true); setErr(null)
    try {
      const r = await fetch(`${base}/api/marketplace/skills/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          description: desc.trim(),
          category: category.trim() || 'Custom',
          icon: icon.trim() || '⚡',
          skill_type: type,
          code: code,
          tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        }),
      })
      const data = await r.json()
      if (!r.ok || !data.ok) throw new Error(data.error || r.statusText)
      onCreated()
    } catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <ModalOverlay onClose={onClose}>
      <div style={{ width: 580, maxHeight: '90vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>Create Skill</div>

        {err && <div style={{ color: '#e74c3c', fontSize: 13, background: '#e74c3c18', padding: '6px 10px', borderRadius: 6 }}>⚠ {err}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <FormField label="Name *">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="My Skill" className="modal-input" />
          </FormField>
          <FormField label="Icon">
            <input value={icon} onChange={e => setIcon(e.target.value)} placeholder="⚡" className="modal-input" style={{ width: 60 }} />
          </FormField>
        </div>

        <FormField label="Description">
          <input value={desc} onChange={e => setDesc(e.target.value)} placeholder="What does this skill do?" className="modal-input" />
        </FormField>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <FormField label="Category">
            <select value={category} onChange={e => setCategory(e.target.value)} className="modal-input">
              {['Custom', 'Development', 'Research', 'Documents', 'Communication', 'Data'].map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </FormField>
          <FormField label="Tags (comma-separated)">
            <input value={tags} onChange={e => setTags(e.target.value)} placeholder="search, data, api" className="modal-input" />
          </FormField>
        </div>

        {/* Type selector */}
        <FormField label="Skill Type">
          <div style={{ display: 'flex', gap: 8 }}>
            {[['python', '🐍 Python Function'], ['prompt', '💬 Prompt Template']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => setType(val)}
                style={{
                  flex: 1, padding: '8px 12px', borderRadius: 8, cursor: 'pointer',
                  border: `1px solid ${type === val ? 'var(--accent)' : 'var(--border)'}`,
                  background: type === val ? 'var(--accent)18' : 'var(--bg)',
                  color: 'var(--text)', fontWeight: type === val ? 600 : 400, fontSize: 13,
                }}
              >{label}</button>
            ))}
          </div>
        </FormField>

        {/* Code / Prompt editor */}
        <FormField label={type === 'python' ? 'Python Code' : 'Prompt Template'}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
            {type === 'python'
              ? 'Set "output" variable to the result. Access inputs via inputs["key"].'
              : 'Use {variable} placeholders for inputs. Sent to the LLM.'}
          </div>
          <textarea
            value={code}
            onChange={e => setCode(e.target.value)}
            rows={12}
            className="modal-input"
            style={{ fontFamily: 'monospace', fontSize: 12, resize: 'vertical', minHeight: 200 }}
          />
        </FormField>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
          <button className="pp-btn pp-btn--ghost" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            onClick={submit}
            disabled={busy}
            style={{ padding: '7px 18px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 6, cursor: busy ? 'not-allowed' : 'pointer', fontWeight: 600 }}
          >
            {busy ? 'Creating…' : 'Create Skill'}
          </button>
        </div>
      </div>
    </ModalOverlay>
  )
}

// ─── test skill modal ────────────────────────────────────────────────────────

function TestSkillModal({ base, skill, onClose }) {
  const skillId = skill.skill_id || skill.id
  const isDesktopAutomationSkill = String(skill?.catalog_id || skill?.slug || '').trim() === 'desktop-automation'
  const approvalSessionIdRef = useRef(`skill-test-${String(skillId || 'skill').replace(/[^a-z0-9_-]+/ig, '-')}-${Date.now().toString(36)}`)
  const approvalSessionId = approvalSessionIdRef.current
  const [inputJson, setInputJson] = useState(() => {
    try {
      const schema = skill.input_schema || {}
      const ex = skill.example_input || {}
      if (Object.keys(ex).length > 0) return JSON.stringify(ex, null, 2)
      const props = schema.properties || {}
      const demo = {}
      for (const [k, v] of Object.entries(props)) {
        demo[k] = v.default ?? (v.type === 'string' ? '' : v.type === 'integer' ? 0 : null)
      }
      return JSON.stringify(demo, null, 2)
    } catch { return '{}' }
  })
  const [result, setResult] = useState(null)
  const [busy, setBusy]     = useState(false)
  const [err, setErr]       = useState(null)
  const [approvalRequest, setApprovalRequest] = useState(null)
  const [approvalNote, setApprovalNote] = useState('')
  const [approvalBusy, setApprovalBusy] = useState('')
  const [approvalErr, setApprovalErr] = useState(null)
  const [grants, setGrants] = useState([])
  const [revokeBusy, setRevokeBusy] = useState('')
  const [desktopForm, setDesktopForm] = useState(() => {
    const parsed = _safeJsonParse(inputJson)
    return _desktopFormFromInputs(parsed || {})
  })

  const loadApprovals = useCallback(async () => {
    try {
      const r = await fetch(`${base}/api/marketplace/skills/${skillId}/approvals?status=active`)
      const data = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(data.error || r.statusText)
      setGrants(Array.isArray(data.items) ? data.items : [])
    } catch (_) {}
  }, [base, skillId])

  useEffect(() => {
    loadApprovals()
  }, [loadApprovals])

  useEffect(() => {
    if (!isDesktopAutomationSkill) return
    const parsed = _safeJsonParse(inputJson)
    if (!parsed || typeof parsed !== 'object') return
    setDesktopForm(_desktopFormFromInputs(parsed))
  }, [inputJson, isDesktopAutomationSkill])

  const setDesktopField = useCallback((field, value) => {
    setDesktopForm((prev) => {
      const next = { ...prev, [field]: value }
      setInputJson(JSON.stringify(_desktopInputsFromForm(next), null, 2))
      return next
    })
  }, [])

  const run = useCallback(async () => {
    setBusy(true)
    setErr(null)
    setApprovalErr(null)
    setResult(null)
    try {
      let inputs
      try { inputs = JSON.parse(inputJson) }
      catch { throw new Error('Invalid JSON in inputs') }

      const r = await fetch(`${base}/api/marketplace/skills/${skillId}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inputs, session_id: approvalSessionId }),
      })
      const data = await r.json().catch(() => ({}))
      if (r.status === 409 || data?.error_type === 'approval_required') {
        setApprovalRequest(data)
        setResult(data)
        await loadApprovals()
        return
      }
      if (!r.ok) throw new Error(data.error || data.detail || r.statusText)
      setApprovalRequest(null)
      setResult(data)
    } catch (e) { setErr(e.message) }
    finally {
      setBusy(false)
      loadApprovals()
    }
  }, [approvalSessionId, base, inputJson, loadApprovals, skillId])

  const approve = useCallback(async (scope) => {
    setApprovalBusy(scope)
    setApprovalErr(null)
    try {
      const r = await fetch(`${base}/api/marketplace/skills/${skillId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scope,
          note: approvalNote.trim() || `Approved ${skill.name || skill.slug || skillId} from the desktop skills panel (${scope}).`,
          session_id: approvalSessionId,
        }),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok || !data.ok) throw new Error(data.error || data.detail || r.statusText)
      setApprovalRequest(null)
      await loadApprovals()
      await run()
    } catch (e) {
      setApprovalErr(e.message)
    } finally {
      setApprovalBusy('')
    }
  }, [approvalNote, approvalSessionId, base, loadApprovals, run, skill.name, skill.slug, skillId])

  const revokeGrant = useCallback(async (grantId) => {
    setRevokeBusy(grantId)
    setApprovalErr(null)
    try {
      const r = await fetch(`${base}/api/marketplace/skills/${skillId}/revoke-approval`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ grant_id: grantId }),
      })
      const data = await r.json().catch(() => ({}))
      if (!r.ok || !data.ok) throw new Error(data.error || data.detail || r.statusText)
      await loadApprovals()
    } catch (e) {
      setApprovalErr(e.message)
    } finally {
      setRevokeBusy('')
    }
  }, [base, loadApprovals, skillId])

  const approvalSections = Array.isArray(approvalRequest?.approval_request?.sections)
    ? approvalRequest.approval_request.sections
    : []
  const suggestedScopes = Array.isArray(approvalRequest?.approval_request?.metadata?.suggested_scopes)
    ? approvalRequest.approval_request.metadata.suggested_scopes
    : ['once', 'session', 'always']
  const isApprovalPending = approvalRequest?.error_type === 'approval_required'
  const activeGrants = grants.filter((grant) => String(grant.status || '').toLowerCase() === 'active')
  const effectiveSandbox = result?.sandbox || skill?.sandbox || null
  const desktopAutomation = skill?.desktop_automation || null
  const desktopApps = Array.isArray(desktopAutomation?.supported_apps) ? desktopAutomation.supported_apps : []

  return (
    <ModalOverlay onClose={onClose}>
      <div style={{ width: 560, maxHeight: '85vh', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ fontWeight: 700, fontSize: 16 }}>
          {skill.icon || '⚡'} Test: {skill.name}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{skill.description}</div>

        {err && <div style={{ color: '#e74c3c', fontSize: 13 }}>⚠ {err}</div>}
        {approvalErr && <div style={{ color: '#e74c3c', fontSize: 13 }}>⚠ {approvalErr}</div>}

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="pp-badge pp-badge--muted">Session {approvalSessionId.slice(-10)}</span>
          {activeGrants.length > 0 && (
            <span className="pp-badge pp-badge--warn">{activeGrants.length} active grant{activeGrants.length === 1 ? '' : 's'}</span>
          )}
        </div>

        {desktopAutomation && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: 'rgba(52,152,219,.08)', border: '1px solid rgba(52,152,219,.22)', borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Desktop automation modes</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
              {desktopAutomation.sandbox_notice}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
              {desktopAutomation.full_access_warning}
            </div>
            {Array.isArray(desktopAutomation.supported_apps) && desktopAutomation.supported_apps.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {desktopAutomation.supported_apps.map((app) => (
                  <span key={app.id} className="pp-badge pp-badge--info">{app.name}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {effectiveSandbox && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 10, padding: 12 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Execution boundary</div>
            <SandboxDetail sandbox={effectiveSandbox} />
          </div>
        )}

        <FormField label="Inputs (JSON)">
          <textarea
            value={inputJson}
            onChange={e => {
              const next = e.target.value
              setInputJson(next)
              if (isDesktopAutomationSkill) {
                const parsed = _safeJsonParse(next)
                if (parsed && typeof parsed === 'object') setDesktopForm(_desktopFormFromInputs(parsed))
              }
            }}
            rows={6}
            className="modal-input"
            style={{ fontFamily: 'monospace', fontSize: 12, resize: 'vertical' }}
          />
        </FormField>

        {isDesktopAutomationSkill && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <FormField label="Access mode">
              <select className="modal-input" value={desktopForm.access_mode} onChange={e => setDesktopField('access_mode', e.target.value)}>
                <option value="sandbox">sandbox (preview only)</option>
                <option value="full_access">full_access (native dispatch)</option>
              </select>
            </FormField>
            <FormField label="Action">
              <select className="modal-input" value={desktopForm.action} onChange={e => setDesktopField('action', e.target.value)}>
                <option value="list_apps">list_apps</option>
                <option value="open_app">open_app</option>
                <option value="open_chat">open_chat</option>
                <option value="open_document">open_document</option>
                <option value="open_url">open_url</option>
              </select>
            </FormField>
            <FormField label="App">
              <select className="modal-input" value={desktopForm.app} onChange={e => setDesktopField('app', e.target.value)}>
                {(desktopApps.length ? desktopApps : [
                  { id: 'generic', name: 'Generic Native App' },
                  { id: 'whatsapp', name: 'WhatsApp' },
                  { id: 'telegram', name: 'Telegram' },
                  { id: 'microsoft_365', name: 'Microsoft 365' },
                ]).map((app) => (
                  <option key={app.id} value={app.id}>{app.id}</option>
                ))}
              </select>
            </FormField>
            <FormField label="Timeout (s)">
              <input
                className="modal-input"
                type="number"
                min={1}
                value={desktopForm.timeout}
                onChange={e => setDesktopField('timeout', Number(e.target.value || 10))}
              />
            </FormField>
            {desktopForm.action === 'open_app' && desktopForm.app === 'generic' && (
              <FormField label="App name">
                <input className="modal-input" value={desktopForm.app_name} onChange={e => setDesktopField('app_name', e.target.value)} placeholder="Telegram Desktop" />
              </FormField>
            )}
            {desktopForm.action === 'open_app' && desktopForm.app === 'microsoft_365' && (
              <FormField label="Office app">
                <select className="modal-input" value={desktopForm.office_app} onChange={e => setDesktopField('office_app', e.target.value)}>
                  <option value="outlook">outlook</option>
                  <option value="word">word</option>
                  <option value="excel">excel</option>
                  <option value="powerpoint">powerpoint</option>
                  <option value="teams">teams</option>
                </select>
              </FormField>
            )}
            {desktopForm.action === 'open_chat' && desktopForm.app === 'whatsapp' && (
              <FormField label="Phone number">
                <input className="modal-input" value={desktopForm.phone_number} onChange={e => setDesktopField('phone_number', e.target.value)} placeholder="+14155550123" />
              </FormField>
            )}
            {desktopForm.action === 'open_chat' && desktopForm.app === 'telegram' && (
              <FormField label="Telegram handle">
                <input className="modal-input" value={desktopForm.handle} onChange={e => setDesktopField('handle', e.target.value)} placeholder="OpenAI" />
              </FormField>
            )}
            {desktopForm.action === 'open_chat' && (
              <FormField label="Message">
                <input className="modal-input" value={desktopForm.message} onChange={e => setDesktopField('message', e.target.value)} placeholder="Optional message draft" />
              </FormField>
            )}
            {desktopForm.action === 'open_document' && (
              <FormField label="Document path">
                <input className="modal-input" value={desktopForm.document_path} onChange={e => setDesktopField('document_path', e.target.value)} placeholder="/path/to/file.docx" />
              </FormField>
            )}
            {desktopForm.action === 'open_url' && (
              <FormField label="URL">
                <input className="modal-input" value={desktopForm.url} onChange={e => setDesktopField('url', e.target.value)} placeholder="https://example.com" />
              </FormField>
            )}
          </div>
        )}

        <button
          onClick={run}
          disabled={busy}
          style={{ alignSelf: 'flex-end', padding: '7px 18px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 6, cursor: busy ? 'not-allowed' : 'pointer', fontWeight: 600 }}
        >
          {busy ? '⏳ Running…' : '▶ Run Test'}
        </button>

        {isApprovalPending && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, background: 'rgba(255,179,71,.08)', border: '1px solid rgba(255,179,71,.3)', borderRadius: 10, padding: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 13 }}>Permission required</span>
              <span className="pp-badge pp-badge--warn">approval required</span>
            </div>
            {approvalRequest?.approval_request?.summary && (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.55 }}>
                {approvalRequest.approval_request.summary}
              </div>
            )}
            {approvalSections.map((section, index) => (
              <div key={`${section.title || 'section'}-${index}`} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {section.title && <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.08em' }}>{section.title}</div>}
                <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4, color: 'var(--text)' }}>
                  {(section.items || []).map((item, itemIndex) => (
                    <li key={`${index}-${itemIndex}`} style={{ fontSize: 12, lineHeight: 1.5 }}>{item}</li>
                  ))}
                </ul>
              </div>
            ))}
            {approvalRequest?.approval_request?.help_text && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                {approvalRequest.approval_request.help_text}
              </div>
            )}
            <FormField label="Approval note">
              <textarea
                value={approvalNote}
                onChange={e => setApprovalNote(e.target.value)}
                rows={2}
                className="modal-input"
                placeholder="Optional note for the audit log"
              />
            </FormField>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {suggestedScopes.map((scope) => (
                <button
                  key={scope}
                  onClick={() => approve(scope)}
                  disabled={!!approvalBusy}
                  className="pp-btn pp-btn--primary"
                >
                  {approvalBusy === scope
                    ? 'Approving…'
                    : scope === 'session'
                      ? 'Allow this session'
                      : scope === 'always'
                        ? 'Always allow'
                        : 'Allow once'}
                </button>
              ))}
            </div>
          </div>
        )}

        {activeGrants.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontWeight: 600, fontSize: 13 }}>Active grants</div>
            {activeGrants.map((grant) => {
              const isCurrentSession = grant.session_id && grant.session_id === approvalSessionId
              return (
                <div
                  key={grant.grant_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 12,
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    padding: '10px 12px',
                    background: 'var(--bg)',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span className="pp-badge pp-badge--ok">{grant.scope}</span>
                      {isCurrentSession && <span className="pp-badge pp-badge--info">current session</span>}
                      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{grant.actor || 'user'}</span>
                    </div>
                    {grant.note && <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.45 }}>{grant.note}</div>}
                  </div>
                  <button
                    onClick={() => revokeGrant(grant.grant_id)}
                    disabled={revokeBusy === grant.grant_id}
                    className="pp-btn pp-btn--ghost"
                  >
                    {revokeBusy === grant.grant_id ? 'Revoking…' : 'Revoke'}
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {result && !isApprovalPending && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>Result</span>
              <span style={{
                fontSize: 11, padding: '1px 7px', borderRadius: 4,
                background: result.success ? '#27ae6018' : '#e74c3c18',
                color: result.success ? '#27ae60' : '#e74c3c',
                border: `1px solid ${result.success ? '#27ae6044' : '#e74c3c44'}`,
              }}>
                {result.success ? '✓ success' : '✕ failed'}
              </span>
              {typeof result.output?.preview_only === 'boolean' && (
                <span className={`pp-badge ${result.output.preview_only ? 'pp-badge--warn' : 'pp-badge--ok'}`}>
                  {result.output.preview_only ? 'preview only' : 'dispatched'}
                </span>
              )}
            </div>
            {result.stdout && (
              <pre style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: 10, fontSize: 12, overflowX: 'auto', maxHeight: 200, margin: 0 }}>
                {result.stdout}
              </pre>
            )}
            {result.error && (
              <pre style={{ background: '#e74c3c0a', border: '1px solid #e74c3c44', borderRadius: 6, padding: 10, fontSize: 12, color: '#e74c3c', overflowX: 'auto', maxHeight: 150, margin: 0 }}>
                {result.error}
              </pre>
            )}
            {result.output && typeof result.output === 'object' && (
              <pre style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6, padding: 10, fontSize: 12, overflowX: 'auto', maxHeight: 220, margin: 0 }}>
                {JSON.stringify(result.output, null, 2)}
              </pre>
            )}
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="pp-btn pp-btn--ghost" onClick={onClose}>Close</button>
        </div>
      </div>
    </ModalOverlay>
  )
}

// ─── shared components ───────────────────────────────────────────────────────

function ModalOverlay({ onClose, children }) {
  const overlayRef = useRef(null)
  return (
    <div
      ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div style={{
        background: 'var(--bg-secondary, #1e1e2e)',
        border: '1px solid var(--border)',
        borderRadius: 12, padding: 24, boxShadow: '0 24px 48px #0008',
      }}>
        {children}
      </div>
    </div>
  )
}

function FormField({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)' }}>{label}</label>
      {children}
    </div>
  )
}
