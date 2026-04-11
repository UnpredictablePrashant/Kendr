import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useApp } from '../contexts/AppContext'

const EMPTY_ASSISTANT = {
  assistant_id: '',
  name: '',
  description: '',
  goal: '',
  system_prompt: '',
  model_provider: '',
  model_name: '',
  routing_policy: 'balanced',
  status: 'draft',
  attached_capabilities: [],
  memory_config: { summary: '', local_paths: [] },
}

const ROUTING_OPTIONS = [
  { id: 'balanced', label: 'Balanced' },
  { id: 'quality', label: 'Highest quality' },
  { id: 'cost', label: 'Lowest cost' },
  { id: 'private', label: 'Private first' },
]

export default function AssistantBuilder() {
  const { state, dispatch } = useApp()
  const base = state.backendUrl || 'http://127.0.0.1:2151'

  const [assistants, setAssistants] = useState([])
  const [capabilities, setCapabilities] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [draft, setDraft] = useState(EMPTY_ASSISTANT)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState('')
  const [testMessage, setTestMessage] = useState('Give me a short explanation of what you can do and how you would approach a task.')
  const [testResult, setTestResult] = useState(null)

  const selectedAssistant = useMemo(
    () => assistants.find((item) => item.assistant_id === selectedId) || null,
    [assistants, selectedId]
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [assistantRes, capRes] = await Promise.all([
        fetch(`${base}/api/assistants`),
        fetch(`${base}/api/capabilities?status=active`),
      ])
      const assistantData = await assistantRes.json()
      const capData = await capRes.json()
      const nextAssistants = Array.isArray(assistantData.assistants) ? assistantData.assistants : []
      const nextCaps = Array.isArray(capData) ? capData : (capData.capabilities || capData.items || [])
      setAssistants(nextAssistants)
      setCapabilities(nextCaps.filter((item) => ['skill', 'agent', 'tool', 'api', 'mcp_server'].includes(item.type)))
      if (!selectedId && nextAssistants[0]?.assistant_id) {
        setSelectedId(nextAssistants[0].assistant_id)
      }
      if (!selectedId && !nextAssistants.length) {
        setDraft(EMPTY_ASSISTANT)
      }
    } catch (e) {
      setError(e.message || 'Failed to load assistant builder')
    } finally {
      setLoading(false)
    }
  }, [base, selectedId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (selectedAssistant) {
      setDraft({
        ...EMPTY_ASSISTANT,
        ...selectedAssistant,
        attached_capabilities: Array.isArray(selectedAssistant.attached_capabilities) ? selectedAssistant.attached_capabilities : [],
        memory_config: typeof selectedAssistant.memory_config === 'object' && selectedAssistant.memory_config ? selectedAssistant.memory_config : { summary: '', local_paths: [] },
      })
      setTestResult(null)
    } else if (!selectedId) {
      setDraft(EMPTY_ASSISTANT)
      setTestResult(null)
    }
  }, [selectedAssistant, selectedId])

  const setField = (key, value) => setDraft((prev) => ({ ...prev, [key]: value }))
  const setMemoryField = (key, value) => setDraft((prev) => ({ ...prev, memory_config: { ...(prev.memory_config || {}), [key]: value } }))

  const resetNew = () => {
    setSelectedId('')
    setDraft(EMPTY_ASSISTANT)
    setTestResult(null)
    setError('')
  }

  const toggleCapability = (cap) => {
    setDraft((prev) => {
      const current = Array.isArray(prev.attached_capabilities) ? prev.attached_capabilities : []
      const capabilityId = cap.capability_id || cap.id
      const capabilityKey = cap.capability_key || cap.key
      const exists = current.some((item) => item.capability_id === capabilityId)
      return {
        ...prev,
        attached_capabilities: exists
          ? current.filter((item) => item.capability_id !== capabilityId)
          : [
              ...current,
              {
                capability_id: capabilityId,
                capability_key: capabilityKey,
                name: cap.name,
                type: cap.type,
              },
            ],
      }
    })
  }

  const saveAssistant = async (statusOverride = null) => {
    if (!draft.name.trim()) {
      setError('Assistant name is required')
      return
    }
    setSaving(true)
    setError('')
    try {
      const payload = {
        ...draft,
        status: statusOverride || draft.status || 'draft',
      }
      const isUpdate = !!draft.assistant_id
      const url = isUpdate ? `${base}/api/assistants/${draft.assistant_id}/update` : `${base}/api/assistants`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error || res.statusText)
      await load()
      setSelectedId(data.assistant_id || data.id || payload.assistant_id || '')
      setDraft((prev) => ({ ...prev, ...data }))
    } catch (e) {
      setError(e.message || 'Failed to save assistant')
    } finally {
      setSaving(false)
    }
  }

  const deleteAssistant = async () => {
    if (!draft.assistant_id) return
    if (!window.confirm('Delete this assistant?')) return
    setSaving(true)
    setError('')
    try {
      const res = await fetch(`${base}/api/assistants/${draft.assistant_id}/delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error || res.statusText)
      resetNew()
      await load()
    } catch (e) {
      setError(e.message || 'Failed to delete assistant')
    } finally {
      setSaving(false)
    }
  }

  const runTest = async () => {
    if (!draft.assistant_id) {
      setError('Save the assistant before testing it')
      return
    }
    if (!testMessage.trim()) {
      setError('Test message is required')
      return
    }
    setTesting(true)
    setError('')
    try {
      const res = await fetch(`${base}/api/assistants/${draft.assistant_id}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: testMessage }),
      })
      const data = await res.json()
      if (!res.ok || data.error) throw new Error(data.error || res.statusText)
      setTestResult(data)
    } catch (e) {
      setError(e.message || 'Assistant test failed')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="assistant-builder">
      <div className="assistant-builder__sidebar surface-card">
        <div className="assistant-builder__sidebar-head">
          <div>
            <h3>Assistants</h3>
            <p>Draft, test, and publish reusable AI workers.</p>
          </div>
          <button className="kendr-btn kendr-btn--ghost" onClick={resetNew}>New</button>
        </div>
        {loading ? (
          <div className="pp-loading">Loading assistants…</div>
        ) : assistants.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__title">No assistants yet</div>
            <div className="empty-state__body">Create your first assistant from goal, instructions, and connected capabilities.</div>
          </div>
        ) : (
          <div className="assistant-list">
            {assistants.map((item) => (
              <button
                key={item.assistant_id}
                className={`assistant-list__item ${selectedId === item.assistant_id ? 'active' : ''}`}
                onClick={() => setSelectedId(item.assistant_id)}
              >
                <span className="assistant-list__name">{item.name}</span>
                <span className="assistant-list__meta">{item.status || 'draft'} · {item.routing_policy || 'balanced'}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="assistant-builder__main">
        <div className="surface-card">
          <div className="assistant-builder__header">
            <div>
              <h2>{draft.assistant_id ? 'Assistant Builder' : 'Create Assistant'}</h2>
              <p>Define the assistant goal, add instructions, attach capabilities, and test it before you publish.</p>
            </div>
            <div className="assistant-builder__actions">
              <button className="kendr-btn kendr-btn--ghost" onClick={() => dispatch({ type: 'SET_VIEW', view: 'studio' })}>Open Studio</button>
              <button className="kendr-btn kendr-btn--ghost" disabled={saving} onClick={() => saveAssistant('draft')}>Save Draft</button>
              <button className="kendr-btn kendr-btn--primary" disabled={saving} onClick={() => saveAssistant('active')}>Publish</button>
            </div>
          </div>
          {error && <div className="pp-error-banner">⚠ {error} <button onClick={() => setError('')}>✕</button></div>}

          <div className="assistant-form-grid">
            <label>
              <span>Name</span>
              <input className="pp-input" value={draft.name} onChange={(e) => setField('name', e.target.value)} placeholder="Customer Support Assistant" />
            </label>
            <label>
              <span>Status</span>
              <select className="pp-select" value={draft.status || 'draft'} onChange={(e) => setField('status', e.target.value)}>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
              </select>
            </label>
            <label className="assistant-form-grid__full">
              <span>Description</span>
              <input className="pp-input" value={draft.description} onChange={(e) => setField('description', e.target.value)} placeholder="One-line product description for the assistant" />
            </label>
            <label className="assistant-form-grid__full">
              <span>Goal</span>
              <textarea className="pp-input assistant-textarea" value={draft.goal} onChange={(e) => setField('goal', e.target.value)} placeholder="What should this assistant actually do?" />
            </label>
            <label className="assistant-form-grid__full">
              <span>System Instructions</span>
              <textarea className="pp-input assistant-textarea assistant-textarea--lg" value={draft.system_prompt} onChange={(e) => setField('system_prompt', e.target.value)} placeholder="Add domain rules, tone, approval guidance, and constraints." />
            </label>
            <label>
              <span>Model Provider</span>
              <input className="pp-input" value={draft.model_provider || ''} onChange={(e) => setField('model_provider', e.target.value)} placeholder="openai, anthropic, ollama…" />
            </label>
            <label>
              <span>Model Name</span>
              <input className="pp-input" value={draft.model_name || ''} onChange={(e) => setField('model_name', e.target.value)} placeholder="Leave blank for routed default" />
            </label>
            <label>
              <span>Routing Policy</span>
              <select className="pp-select" value={draft.routing_policy || 'balanced'} onChange={(e) => setField('routing_policy', e.target.value)}>
                {ROUTING_OPTIONS.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
              </select>
            </label>
            <label>
              <span>Memory Summary</span>
              <input className="pp-input" value={draft.memory_config?.summary || ''} onChange={(e) => setMemoryField('summary', e.target.value)} placeholder="What should it remember or retrieve?" />
            </label>
            <label className="assistant-form-grid__full">
              <span>Local Memory Paths</span>
              <textarea className="pp-input assistant-textarea" value={(draft.memory_config?.local_paths || []).join('\n')} onChange={(e) => setMemoryField('local_paths', e.target.value.split('\n').map((item) => item.trim()).filter(Boolean))} placeholder="/docs\n/data/help-center" />
            </label>
          </div>
        </div>

        <div className="grid-two">
          <div className="surface-card">
            <div className="section-header">
              <div>
                <h2>Attached Capabilities</h2>
                <p>Select the skills, tools, APIs, and MCP sources this assistant can use.</p>
              </div>
            </div>
            <div className="assistant-cap-grid">
              {capabilities.slice(0, 24).map((cap) => {
                const capabilityId = cap.capability_id || cap.id
                const capabilityKey = cap.capability_key || cap.key
                const checked = (draft.attached_capabilities || []).some((item) => item.capability_id === capabilityId)
                return (
                  <button key={capabilityId} className={`assistant-cap-card ${checked ? 'active' : ''}`} onClick={() => toggleCapability(cap)}>
                    <span className="assistant-cap-card__type">{cap.type}</span>
                    <span className="assistant-cap-card__name">{cap.name}</span>
                    <span className="assistant-cap-card__key">{capabilityKey}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="surface-card">
            <div className="section-header">
              <div>
                <h2>Quick Test</h2>
                <p>Run a direct test against the configured assistant before shipping it into Studio.</p>
              </div>
            </div>
            <textarea className="pp-input assistant-textarea assistant-textarea--lg" value={testMessage} onChange={(e) => setTestMessage(e.target.value)} />
            <div className="hero-actions">
              <button className="kendr-btn kendr-btn--primary" disabled={testing || !draft.assistant_id} onClick={runTest}>
                {testing ? 'Testing…' : 'Run Test'}
              </button>
              <button className="kendr-btn kendr-btn--ghost" disabled={saving || !draft.assistant_id} onClick={deleteAssistant}>
                Delete
              </button>
            </div>

            {testResult && (
              <div className="assistant-test-result">
                <div className="status-grid">
                  <div className="status-pill status-pill--neutral">
                    <span className="status-pill__label">Provider</span>
                    <span className="status-pill__value">{testResult.provider}</span>
                  </div>
                  <div className="status-pill status-pill--neutral">
                    <span className="status-pill__label">Model</span>
                    <span className="status-pill__value">{testResult.model}</span>
                  </div>
                </div>
                <div className="assistant-test-result__panel">
                  <strong>Assistant response</strong>
                  <pre>{testResult.answer}</pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
