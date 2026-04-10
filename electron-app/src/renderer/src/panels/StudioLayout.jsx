import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'
import ChatPanel from './ChatPanel'

// ─── Cloud model catalogue ────────────────────────────────────────────────────
const PROVIDER_ORDER = ['anthropic', 'openai', 'google', 'xai']

const CLOUD_MODELS = [
  { id: 'anthropic/claude-opus-4-6',    label: 'Claude Opus 4.6',    provider: 'anthropic' },
  { id: 'anthropic/claude-sonnet-4-6',  label: 'Claude Sonnet 4.6',  provider: 'anthropic' },
  { id: 'anthropic/claude-haiku-4-5',   label: 'Claude Haiku 4.5',   provider: 'anthropic' },
  { id: 'openai/gpt-4o',               label: 'GPT-4o',             provider: 'openai' },
  { id: 'openai/gpt-4o-mini',          label: 'GPT-4o mini',        provider: 'openai' },
  { id: 'openai/gpt-4-turbo',          label: 'GPT-4 Turbo',        provider: 'openai' },
  { id: 'google/gemini-2.0-flash',      label: 'Gemini 2.0 Flash',   provider: 'google' },
  { id: 'google/gemini-2.5-pro',        label: 'Gemini 2.5 Pro',     provider: 'google' },
  { id: 'google/gemini-1.5-pro',        label: 'Gemini 1.5 Pro',     provider: 'google' },
  { id: 'xai/grok-4',                               label: 'Grok 4',                     provider: 'xai' },
  { id: 'xai/grok-4.20-beta-latest-non-reasoning', label: 'Grok 4.20',                  provider: 'xai' },
  { id: 'xai/grok-4-1-fast-reasoning',              label: 'Grok 4.1 Fast Reasoning',   provider: 'xai' },
]

const PROVIDER_META = {
  anthropic: { label: 'Anthropic', settingsKey: 'anthropicKey' },
  openai:    { label: 'OpenAI', settingsKey: 'openaiKey' },
  google:    { label: 'Google AI', settingsKey: 'googleKey' },
  xai:       { label: 'xAI / Grok', settingsKey: 'xaiKey' },
}

// ─── StudioLayout ─────────────────────────────────────────────────────────────
export default function StudioLayout() {
  const { state, dispatch, refreshOllamaModels } = useApp()
  const [chatKey, setChatKey]       = useState(0)
  const isOnline = state.backendStatus === 'running'
  const ollamaModels = Array.isArray(state.ollamaModels) ? state.ollamaModels : []
  const ollamaLoading = !!state.ollamaLoading
  const ollamaError = !!state.ollamaError
  const modelInventory = state.modelInventory
  const modelInventoryLoading = !!state.modelInventoryLoading
  const modelInventoryError = !!state.modelInventoryError

  const providerStatuses = Object.fromEntries(
    ((modelInventory && Array.isArray(modelInventory.providers)) ? modelInventory.providers : [])
      .map(provider => [provider.provider, provider])
  )

  const getProviderUiState = useCallback((provider) => {
    const meta = PROVIDER_META[provider]
    const status = providerStatuses[provider] || {}
    const hasSavedKey = !!String(state.settings?.[meta.settingsKey] || '').trim()
    const hasModels = Array.isArray(status.selectable_models) && status.selectable_models.length > 0
    const hasFetchError = !!String(status.model_fetch_error || '').trim()

    if (!hasSavedKey) {
      return { kind: 'missing', label: '+ key', title: `Add ${meta.label} API key` }
    }
    if (modelInventoryLoading || state.backendStatus === 'starting' || state.backendStatus === 'connecting') {
      return { kind: 'checking', label: 'checking', title: `Checking ${meta.label} models…` }
    }
    if (modelInventoryError || hasFetchError || (!status.ready && !hasModels)) {
      return {
        kind: 'error',
        label: 'error',
        title: hasFetchError ? `${meta.label}: ${status.model_fetch_error}` : `${meta.label} could not be verified`,
      }
    }
    return { kind: 'ok', label: '✓', title: `${meta.label} ready` }
  }, [modelInventoryError, modelInventoryLoading, providerStatuses, state.backendStatus, state.settings])

  const selectModel = (id) => dispatch({ type: 'SET_MODEL', model: id })
  const navigate    = (view) => dispatch({ type: 'SET_VIEW', view })

  return (
    <div className="sl-root">
      {/* ── Left sidebar ── */}
      <div className="sl-sidebar">
        <div className="sl-sidebar-top">
          <button className="sl-new-chat" onClick={() => setChatKey(k => k + 1)}>
            <PlusIcon /> New chat
          </button>

          <div className="sl-conv-label">Session</div>
          <button className="sl-conv-item active">
            <ChatDotIcon /> Current chat
          </button>

          {/* ── Cloud provider status ── */}
          <div className="sl-section-divider" />
          <div className="sl-conv-label">CLOUD PROVIDERS</div>
          <div className="sl-providers">
            {PROVIDER_ORDER.map(p => {
              const ui = getProviderUiState(p)
              return (
              <button
                key={p}
                className={`sl-provider-row ${ui.kind}`}
                onClick={() => navigate('settings')}
                title={ui.title}
              >
                <span className={`mp-provider-dot ${p}`} />
                <span className="sl-provider-name">{PROVIDER_META[p].label}</span>
                {ui.kind === 'checking' && <SpinnerIcon className="sl-provider-spinner" />}
                {ui.kind === 'ok' && <span className="sl-provider-ok">✓</span>}
                {ui.kind === 'missing' && <span className="sl-provider-add">+ key</span>}
                {ui.kind === 'error' && <span className="sl-provider-error">!</span>}
              </button>
            )})}
          </div>

          {/* ── Local Ollama models ── */}
          <div className="sl-section-divider" />
          <div className="sl-ollama-header">
            <span className="sl-conv-label" style={{ margin: 0 }}>LOCAL MODELS</span>
            <button
              className="sl-refresh-btn"
              onClick={() => refreshOllamaModels(true)}
              disabled={ollamaLoading}
              title="Refresh Ollama models"
            >
              <RefreshIcon spinning={ollamaLoading} />
            </button>
          </div>

          {ollamaLoading && (
            <div className="sl-ollama-inline">
              <span className="sl-ollama-dot checking" />
              <span>Checking…</span>
            </div>
          )}
          {!ollamaLoading && ollamaError && (
            <div className="sl-ollama-inline">
              <span className="sl-ollama-dot offline" />
              <span>Ollama offline</span>
              <button className="sl-ollama-action" onClick={() => refreshOllamaModels(true)}>retry</button>
            </div>
          )}
          {!ollamaLoading && !ollamaError && ollamaModels.length === 0 && (
            <div className="sl-ollama-inline">
              <span className="sl-ollama-dot empty" />
              <span>No local models</span>
              <button className="sl-ollama-action" onClick={() => navigate('models')}>pull →</button>
            </div>
          )}
          {!ollamaLoading && ollamaModels.map(m => {
            const id       = `ollama/${m.name || m}`
            const name     = m.name || m
            const isActive = state.selectedModel === id
            const sizeGB   = m.size ? (m.size / 1e9).toFixed(1) : null
            return (
              <button
                key={id}
                className={`sl-model-btn ${isActive ? 'active' : ''}`}
                onClick={() => selectModel(isActive ? null : id)}
                title={`${name}${sizeGB ? ` — ${sizeGB} GB` : ''}`}
              >
                <span className="sl-model-dot" />
                <span className="sl-model-name">{name}</span>
                {sizeGB && <span className="sl-model-size">{sizeGB} GB</span>}
                {isActive && <span className="sl-model-check">✓</span>}
              </button>
            )
          })}
        </div>

        {/* Bottom nav */}
        <div className="sl-sidebar-bottom">
          <button className="sl-nav-btn" onClick={() => navigate('runs')} title="Runs & Orchestration">
            <RunsNavIcon /> Runs
          </button>
          <button className="sl-nav-btn" onClick={() => navigate('agents')} title="Agents & Capabilities">
            <AgentsNavIcon /> Agents
          </button>
          <button className="sl-nav-btn" onClick={() => navigate('mcp')} title="MCP Servers">
            <MCPNavIcon /> MCP
          </button>
          <button className="sl-nav-btn" onClick={() => navigate('models')} title="Model Manager">
            <ModelsNavIcon /> Models
          </button>
          <button className="sl-nav-btn" onClick={() => navigate('settings')} title="Settings">
            <SettingsNavIcon /> Settings
          </button>
        </div>
      </div>

      {/* ── Main content ── */}
      <div className="sl-main">
        <div className="sl-topbar">
          <ModelPicker
            ollamaModels={ollamaModels}
            onRefreshOllama={() => refreshOllamaModels(true)}
            providerStatuses={providerStatuses}
            getProviderUiState={getProviderUiState}
          />
          <div className="sl-topbar-spacer" />
          <div className="sl-status">
            <span className={`sl-status-dot ${isOnline ? 'on' : ''}`} />
            <span>{isOnline ? 'connected' : state.backendStatus}</span>
          </div>
        </div>

        <ChatPanel key={chatKey} fullWidth hideHeader studioMode />
      </div>
    </div>
  )
}

// ─── Model Picker (topbar dropdown) ──────────────────────────────────────────
function ModelPicker({ ollamaModels, onRefreshOllama, providerStatuses, getProviderUiState }) {
  const { state, dispatch } = useApp()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const select = (modelId, disabled) => {
    if (disabled) return
    dispatch({ type: 'SET_MODEL', model: modelId })
    setOpen(false)
  }

  const selected = state.selectedModel
  const selectedMeta = CLOUD_MODELS.find(m => m.id === selected)
  const displayName = !selected
    ? 'Auto (backend default)'
    : selectedMeta?.label ?? selected.replace(/^ollama\//, '')
  const selectedProvider = selected
    ? (selectedMeta?.provider || 'ollama')
    : null

  const isProviderConfigured = (provider) => {
    return getProviderUiState(provider).kind === 'ok'
  }
  const getModelBadges = (provider, modelId) => {
    const status = providerStatuses[provider] || {}
    const name = String(modelId || '').replace(new RegExp(`^${provider}/`), '')
    return Array.isArray(status.model_badges?.[name]) ? status.model_badges[name] : []
  }

  // If selected model's provider lost its key, show warning in trigger
  const selectedProviderLost = selected && selectedMeta && !isProviderConfigured(selectedMeta.provider)

  return (
    <div className="mp-root" ref={rootRef}>
      <button className={`mp-trigger ${selectedProviderLost ? 'mp-trigger--warn' : ''}`} onClick={() => setOpen(o => !o)}>
        {selectedProvider && <span className={`mp-provider-dot ${selectedProvider}`} />}
        <span className="mp-trigger-label">{displayName}</span>
        {selectedProviderLost && <span className="mp-trigger-warn" title="API key not configured">⚠</span>}
        <ChevronIcon />
      </button>

      {open && (
        <div className="mp-dropdown">
          {/* Auto */}
          <div className="mp-group">
            <button className={`mp-option ${!selected ? 'active' : ''}`} onClick={() => select(null, false)}>
              <span className="mp-option-name">Auto (backend default)</span>
              {!selected && <span className="mp-option-check">✓</span>}
            </button>
          </div>

          {/* Cloud — grouped per provider */}
          {PROVIDER_ORDER.map(provider => {
            const status = providerStatuses[provider] || {}
            const ui = getProviderUiState(provider)
            const isConfigured = ui.kind === 'ok'
            const knownModels = CLOUD_MODELS.filter(m => m.provider === provider)
            const selectableModels = Array.isArray(status.selectable_models) ? status.selectable_models : []
            const models = selectableModels.length
              ? selectableModels.map(model => {
                  const existing = knownModels.find(item => item.id === `${provider}/${model}`)
                  return existing || { id: `${provider}/${model}`, label: model, provider }
                })
              : knownModels
            const meta = PROVIDER_META[provider]
            return (
              <div key={provider} className="mp-group">
                <div className="mp-group-label">
                  <span className={`mp-provider-dot ${provider}`} />
                  {meta.label}
                  {ui.kind === 'ok' && <span className="mp-key-badge ok">ready</span>}
                  {ui.kind === 'missing' && <span className="mp-key-badge missing">no key</span>}
                  {ui.kind === 'checking' && (
                    <span className="mp-key-badge checking"><SpinnerIcon className="mp-inline-spinner" />checking</span>
                  )}
                  {ui.kind === 'error' && <span className="mp-key-badge error">error</span>}
                </div>
                {models.map(m => (
                  <button
                    key={m.id}
                    className={`mp-option ${selected === m.id ? 'active' : ''} ${!isConfigured ? 'mp-option--dim' : ''}`}
                    onClick={() => select(m.id, !isConfigured)}
                    title={!isConfigured ? ui.title : m.label}
                    disabled={!isConfigured}
                  >
                    <span className="mp-option-name">{m.label}</span>
                    {getModelBadges(provider, m.id).map(badge => (
                      <span key={`${m.id}:${badge}`} className={`mp-model-badge ${badge}`}>{badge}</span>
                    ))}
                    {!isConfigured && <span className="mp-lock">🔒</span>}
                    {selected === m.id && isConfigured && <span className="mp-option-check">✓</span>}
                  </button>
                ))}
                {!isConfigured && (
                  <button
                    className="mp-add-key-btn"
                    onClick={() => { dispatch({ type: 'SET_VIEW', view: 'settings' }); setOpen(false) }}
                  >
                    {ui.kind === 'missing' ? `+ Add ${meta.label} key →` : ui.kind === 'checking' ? `Checking ${meta.label}…` : `Resolve ${meta.label} error →`}
                  </button>
                )}
              </div>
            )
          })}

          {/* Local Ollama */}
          <div className="mp-group">
            <div className="mp-group-label mp-group-label--row">
              <span className="mp-provider-dot ollama" />
              Local (Ollama)
              <button className="mp-refresh-btn" onClick={onRefreshOllama} title="Refresh Ollama models">
                <RefreshIcon />
              </button>
            </div>
            {ollamaModels.length === 0 ? (
              <div className="mp-empty">
                No local models found.
                <button className="mp-add-key-btn" onClick={() => { dispatch({ type: 'SET_VIEW', view: 'models' }); setOpen(false) }}>
                  Pull a model →
                </button>
              </div>
            ) : (
              ollamaModels.map(m => {
                const id = `ollama/${m.name || m}`
                return (
                  <button
                    key={id}
                    className={`mp-option ${selected === id ? 'active' : ''}`}
                    onClick={() => select(id, false)}
                  >
                    <span className="mp-option-name">{m.name || m}</span>
                    {m.size && <span className="mp-option-size">{(m.size / 1e9).toFixed(1)} GB</span>}
                    {selected === id && <span className="mp-option-check">✓</span>}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function SpinnerIcon({ className = '' }) {
  return (
    <svg
      className={className}
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
    >
      <path d="M21 12a9 9 0 1 1-3.2-6.9" />
    </svg>
  )
}

// ─── Refresh icon (optionally animates) ───────────────────────────────────────
function RefreshIcon({ spinning = false }) {
  return (
    <svg
      width="12" height="12" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
      style={spinning ? { animation: 'sl-spin .7s linear infinite' } : {}}
    >
      <polyline points="23 4 23 10 17 10"/>
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
    </svg>
  )
}

// ─── Icons ────────────────────────────────────────────────────────────────────
function PlusIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
}
function ChatDotIcon() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
}
function RunsNavIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
}
function AgentsNavIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/><circle cx="8" cy="10" r="1.5" fill="currentColor"/><circle cx="12" cy="10" r="1.5" fill="currentColor"/><circle cx="16" cy="10" r="1.5" fill="currentColor"/></svg>
}
function MCPNavIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/></svg>
}
function ModelsNavIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
}
function SettingsNavIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
}
function ChevronIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="6 9 12 15 18 9"/></svg>
}
