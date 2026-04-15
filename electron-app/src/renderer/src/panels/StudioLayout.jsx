import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useApp } from '../contexts/AppContext'
import ChatPanel from './ChatPanel'

const SESSIONS_KEY = 'kendr_sessions_v1'
const CURRENT_HIST_KEY = 'kendr_chat_history_v1'
const PROVIDERS = [
  { id: 'openai', label: 'OpenAI', settingsKey: 'openaiKey', defaultModel: 'openai/gpt-4o-mini' },
  { id: 'anthropic', label: 'Anthropic', settingsKey: 'anthropicKey', defaultModel: 'anthropic/claude-sonnet-4-6' },
  { id: 'google', label: 'Google AI', settingsKey: 'googleKey', defaultModel: 'google/gemini-2.0-flash' },
  { id: 'xai', label: 'xAI / Grok', settingsKey: 'xaiKey', defaultModel: 'xai/grok-4' },
]
const CLOUD_MODEL_CATALOG = {
  openai: [
    { name: 'gpt-5.4', badge: 'latest' },
    { name: 'gpt-5.2', badge: 'agent' },
    { name: 'gpt-4o', badge: 'best' },
    { name: 'gpt-4o-mini', badge: 'cheapest' },
    { name: 'gpt-4-turbo' },
  ],
  anthropic: [
    { name: 'claude-opus-4-6', badge: 'best' },
    { name: 'claude-sonnet-4-6', badge: 'latest' },
    { name: 'claude-haiku-4-5', badge: 'cheapest' },
  ],
  google: [
    { name: 'gemini-2.5-pro', badge: 'best' },
    { name: 'gemini-2.5-flash', badge: 'agent' },
    { name: 'gemini-2.0-flash', badge: 'latest' },
    { name: 'gemini-1.5-pro' },
  ],
  xai: [
    { name: 'grok-4', badge: 'best' },
    { name: 'grok-4-1-fast-reasoning', badge: 'agent' },
    { name: 'grok-4.20-beta-latest-non-reasoning', badge: 'latest' },
  ],
}
const STUDIO_NAV_ITEMS = [
  { id: 'build', label: 'Build' },
  { id: 'memory', label: 'Memory' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'runs', label: 'Runs' },
  { id: 'settings', label: 'Settings' },
  { id: 'about', label: 'About Kendr' },
]

function lsGet(key) {
  try { return JSON.parse(localStorage.getItem(key)) } catch { return null }
}

function lsSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch {}
}

function readSessions(settings) {
  const all = lsGet(SESSIONS_KEY) || []
  const days = settings?.chatHistoryRetentionDays ?? 14
  if (!days || days <= 0) return all.slice().reverse()
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000
  return all.filter((session) => new Date(session.updatedAt || session.createdAt).getTime() >= cutoff).reverse()
}

function saveCurrentAsSession(chatId) {
  const messages = lsGet(CURRENT_HIST_KEY) || []
  if (!messages.length) return
  const first = messages.find((item) => item.role === 'user')
  const title = String(first?.content || '').slice(0, 60) || 'New conversation'
  const all = lsGet(SESSIONS_KEY) || []
  const session = {
    id: chatId,
    title,
    createdAt: String(messages[0]?.ts || new Date().toISOString()),
    updatedAt: new Date().toISOString(),
    messages,
  }
  lsSet(SESSIONS_KEY, [...all.filter((item) => item.id !== chatId), session].slice(-100))
}

function sessionRelTime(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime()
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  const d = new Date(dateStr)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function buildProviderModels(providerId, status) {
  const selectable = Array.isArray(status?.selectable_models) ? status.selectable_models : []
  const details = Array.isArray(status?.selectable_model_details) ? status.selectable_model_details : []
  const detailMap = new Map(details.map((item) => [String(item?.name || '').trim(), item]))
  const catalog = Array.isArray(CLOUD_MODEL_CATALOG[providerId]) ? CLOUD_MODEL_CATALOG[providerId] : []
  const seen = new Set()
  const merged = []

  for (const entry of catalog) {
    const name = String(entry?.name || '').trim()
    if (!name) continue
    seen.add(name)
    merged.push({
      name,
      badge: String(entry?.badge || '').trim(),
      available: selectable.includes(name),
      agentCapable: detailMap.get(name)?.agent_capable,
    })
  }

  for (const name of selectable) {
    const clean = String(name || '').trim()
    if (!clean || seen.has(clean)) continue
    const detail = detailMap.get(clean)
    merged.push({
      name: clean,
      badge: '',
      available: true,
      agentCapable: detail?.agent_capable,
    })
  }

  return merged
}

function modelLabel(modelId) {
  const raw = String(modelId || '').trim()
  if (!raw) return 'Auto model'
  if (raw.startsWith('ollama/')) return raw.replace(/^ollama\//, '')
  const provider = raw.split('/')[0]
  const name = raw.replace(`${provider}/`, '')
  const label = PROVIDERS.find((item) => item.id === provider)?.label || provider
  return `${label} · ${name}`
}

function StudioNavIcon({ name }) {
  const common = {
    width: 15,
    height: 15,
    viewBox: '0 0 16 16',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  }

  switch (name) {
    case 'build':
      return (
        <svg {...common}>
          <path d="M3 4.5h10" />
          <path d="M5.5 2.5v4" />
          <path d="M10.5 2.5v4" />
          <path d="M3 7.5h10v5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z" />
        </svg>
      )
    case 'memory':
      return (
        <svg {...common}>
          <path d="M5 3.5h6a1 1 0 0 1 1 1v7H4v-7a1 1 0 0 1 1-1z" />
          <path d="M6 2.5v2" />
          <path d="M10 2.5v2" />
          <path d="M6 8h4" />
        </svg>
      )
    case 'integrations':
      return (
        <svg {...common}>
          <circle cx="5" cy="5" r="1.5" />
          <circle cx="11" cy="5" r="1.5" />
          <circle cx="8" cy="11" r="1.5" />
          <path d="M6.5 5h3" />
          <path d="M5.9 6.2 7.3 9.6" />
          <path d="M10.1 6.2 8.7 9.6" />
        </svg>
      )
    case 'runs':
      return (
        <svg {...common}>
          <path d="M8 3.25a4.75 4.75 0 1 0 4.58 6" />
          <path d="M9.75 2.75H13v3.25" />
          <path d="M8 5.5v2.75l1.75 1.25" />
        </svg>
      )
    case 'settings':
      return (
        <svg {...common}>
          <circle cx="8" cy="8" r="2.25" />
          <path d="M8 2.5v1.25" />
          <path d="M8 12.25v1.25" />
          <path d="M12.25 8h1.25" />
          <path d="M2.5 8h1.25" />
          <path d="m11.89 4.11.88-.88" />
          <path d="m3.23 12.77.88-.88" />
          <path d="m11.89 11.89.88.88" />
          <path d="m3.23 3.23.88.88" />
        </svg>
      )
    default:
      return null
  }
}

export default function StudioLayout() {
  const { state, dispatch, refreshModelInventory, refreshOllamaModels } = useApp()
  const [chatKey, setChatKey] = useState(0)
  const [chatId, setChatId] = useState(() => `chat-${Date.now()}`)
  const [activeSession, setActiveSession] = useState(null)
  const [sessions, setSessions] = useState(() => readSessions(state.settings))
  const [historyFlyoutOpen, setHistoryFlyoutOpen] = useState(false)
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)
  const historyFlyoutRef = useRef(null)
  const profileMenuRef = useRef(null)
  const providerStatuses = useMemo(() => Object.fromEntries(
    ((state.modelInventory && Array.isArray(state.modelInventory.providers)) ? state.modelInventory.providers : [])
      .map((item) => [item.provider, item])
  ), [state.modelInventory])
  const localModels = Array.isArray(state.ollamaModels) ? state.ollamaModels : []

  const cloudReady = PROVIDERS.some((provider) => {
    const hasSavedKey = !!String(state.settings?.[provider.settingsKey] || '').trim()
    const status = providerStatuses[provider.id] || {}
    const selectable = Array.isArray(status.selectable_models) ? status.selectable_models : []
    return hasSavedKey && selectable.length > 0
  })
  const selectedModelReady = (() => {
    const selected = String(state.selectedModel || '').trim()
    if (!selected) return false
    if (selected.startsWith('ollama/')) {
      const name = selected.replace(/^ollama\//, '')
      return localModels.some((model) => String(model?.name || model || '').trim() === name)
    }
    const provider = selected.split('/')[0]
    const status = providerStatuses[provider] || {}
    const selectable = Array.isArray(status.selectable_models) ? status.selectable_models : []
    const modelName = selected.replace(`${provider}/`, '')
    return selectable.includes(modelName)
  })()
  const hasAnyModel = selectedModelReady || cloudReady || localModels.length > 0

  useEffect(() => {
    if (state.selectedModel || cloudReady || localModels.length === 0) return
    const firstLocal = String(localModels[0]?.name || localModels[0] || '').trim()
    if (!firstLocal) return
    dispatch({ type: 'SET_MODEL', model: `ollama/${firstLocal}` })
  }, [cloudReady, dispatch, localModels, state.selectedModel])

  useEffect(() => {
    setSessions(readSessions(state.settings))
  }, [chatKey, state.settings])

  useEffect(() => {
    if (!historyFlyoutOpen) return undefined
    const onMouseDown = (event) => {
      if (historyFlyoutRef.current && !historyFlyoutRef.current.contains(event.target)) setHistoryFlyoutOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [historyFlyoutOpen])

  useEffect(() => {
    if (!profileMenuOpen) return undefined
    const onMouseDown = (event) => {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) setProfileMenuOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [profileMenuOpen])

  useEffect(() => {
    setHistoryFlyoutOpen(false)
    setProfileMenuOpen(false)
  }, [state.sidebarOpen])

  const handleNewChat = () => {
    saveCurrentAsSession(chatId)
    lsSet(CURRENT_HIST_KEY, [])
    const newId = `chat-${Date.now()}`
    setChatId(newId)
    setActiveSession(null)
    setChatKey((value) => value + 1)
    setHistoryFlyoutOpen(false)
  }

  const handleLoadSession = (session) => {
    saveCurrentAsSession(chatId)
    const all = lsGet(SESSIONS_KEY) || []
    lsSet(SESSIONS_KEY, all.filter((item) => item.id !== session.id))
    lsSet(CURRENT_HIST_KEY, session.messages)
    setChatId(session.id)
    setActiveSession(session)
    setChatKey((value) => value + 1)
    setHistoryFlyoutOpen(false)
  }

  const handleDeleteSession = (id) => {
    const all = lsGet(SESSIONS_KEY) || []
    lsSet(SESSIONS_KEY, all.filter((item) => item.id !== id))
    setSessions((current) => current.filter((item) => item.id !== id))
    if (activeSession?.id === id) setActiveSession(null)
  }

  return (
    <div className="sl-minimal-root">
      {hasAnyModel ? (
        <div className="sl-minimal-shell">
          <div className={`sl-studio-shell ${state.sidebarOpen ? '' : 'sl-studio-shell--collapsed'}`}>
            <aside className={`sl-studio-sidebar ${state.sidebarOpen ? '' : 'sl-studio-sidebar--collapsed'}`}>
              <div className="sl-studio-side-top">
                <button
                  className="sl-studio-collapse"
                  onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
                  title={state.sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
                >
                  {state.sidebarOpen ? '‹' : '›'}
                </button>
                <button className={`sl-studio-new ${state.sidebarOpen ? '' : 'sl-studio-new--icon'}`} onClick={handleNewChat} title="New chat">
                  <span className="sl-studio-new-mark">+</span>
                  {state.sidebarOpen && <span>New chat</span>}
                </button>
              </div>

              {state.sidebarOpen ? (
                <div className="sl-studio-session-list">
                  {sessions.length === 0 ? (
                    <div className="sl-studio-empty">No saved chats yet</div>
                  ) : (
                    sessions.map((session) => (
                      <div key={session.id} className="sl-studio-session-row">
                        <button className={`sl-studio-session ${activeSession?.id === session.id ? 'active' : ''}`} onClick={() => handleLoadSession(session)}>
                          <span className="sl-studio-session-title">{session.title}</span>
                          <span className="sl-studio-session-time">{sessionRelTime(session.updatedAt || session.createdAt)}</span>
                        </button>
                        <button className="sl-studio-session-del" onClick={() => handleDeleteSession(session.id)}>×</button>
                      </div>
                    ))
                  )}
                </div>
              ) : (
                <div className="sl-studio-mini-list">
                  <div className="sl-history-flyout-root" ref={historyFlyoutRef}>
                    <button
                      className={`sl-studio-mini-session ${historyFlyoutOpen ? 'active' : ''}`}
                      onClick={() => setHistoryFlyoutOpen((value) => !value)}
                      title="Chat history"
                    >
                      <ChatThreadsIcon />
                    </button>
                    {historyFlyoutOpen && (
                      <div className="sl-history-flyout">
                        <div className="sl-history-flyout-title">Chats</div>
                        {sessions.length === 0 ? (
                          <div className="sl-history-flyout-empty">No saved chats yet</div>
                        ) : (
                          <div className="sl-history-flyout-list">
                            {sessions.map((session) => (
                              <div key={session.id} className="sl-history-flyout-row">
                                <button className="sl-history-flyout-item" onClick={() => handleLoadSession(session)}>
                                  <span className="sl-history-flyout-item-title">{session.title}</span>
                                  <span className="sl-history-flyout-item-time">{sessionRelTime(session.updatedAt || session.createdAt)}</span>
                                </button>
                                <button className="sl-history-flyout-del" onClick={() => handleDeleteSession(session.id)}>×</button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="sl-studio-side-bottom">
                <div className="sl-profile-menu-root" ref={profileMenuRef}>
                  <button
                    className={`sl-profile-trigger ${profileMenuOpen ? 'active' : ''}`}
                    onClick={() => setProfileMenuOpen((value) => !value)}
                    title="Workspace menu"
                  >
                    <span className="sl-profile-avatar">K</span>
                    {state.sidebarOpen && (
                      <span className="sl-profile-copy">
                        <span className="sl-profile-name">Workspace menu</span>
                        <span className="sl-profile-sub">Build, runs, memory, settings</span>
                      </span>
                    )}
                    <span className="sl-profile-caret">⌄</span>
                  </button>
                  {profileMenuOpen && (
                    <div className={`sl-profile-menu ${state.sidebarOpen ? '' : 'sl-profile-menu--collapsed'}`}>
                      <div className="sl-profile-menu-header">
                        <span className="sl-profile-avatar sl-profile-avatar--lg">K</span>
                        <div className="sl-profile-menu-copy">
                          <div className="sl-profile-menu-title">Kendr workspace</div>
                          <div className="sl-profile-menu-sub">Open a focused surface, then jump back to search in one click.</div>
                        </div>
                      </div>
                      <div className="sl-profile-menu-list">
                        {STUDIO_NAV_ITEMS.map((item) => (
                          <button
                            key={item.id}
                            className="sl-profile-menu-item"
                            onClick={() => {
                              dispatch({ type: 'SET_VIEW', view: item.id })
                              setProfileMenuOpen(false)
                            }}
                          >
                            <span className="sl-studio-nav-icon"><StudioNavIcon name={item.id} /></span>
                            <span className="sl-profile-menu-item-label">{item.label}</span>
                            <span className="sl-profile-menu-item-arrow">›</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </aside>
            <div className="sl-studio-main">
              <div className="sl-studio-stage">
                <ChatPanel
                  key={chatKey}
                  fullWidth
                  hideHeader
                  studioMode
                  minimalStudio
                  studioAccessory={(
                    <StudioModelPicker
                      state={state}
                      dispatch={dispatch}
                      providerStatuses={providerStatuses}
                      localModels={localModels}
                      refreshOllamaModels={refreshOllamaModels}
                    />
                  )}
                />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <StudioModelGate
          state={state}
          dispatch={dispatch}
          localModels={localModels}
          refreshModelInventory={refreshModelInventory}
          refreshOllamaModels={refreshOllamaModels}
        />
      )}
    </div>
  )
}

function ChatThreadsIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 4.5h10a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H8.5l-2.5 2v-2H3a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1z" />
      <path d="M5 7h6" />
    </svg>
  )
}

function StudioModelPicker({ state, dispatch, providerStatuses, localModels, refreshOllamaModels }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const triggerRef = useRef(null)
  const [dropdownStyle, setDropdownStyle] = useState(null)
  const selected = String(state.selectedModel || '').trim()
  const selectedProvider = selected.startsWith('ollama/')
    ? 'ollama'
    : String(selected.split('/')[0] || '').trim().toLowerCase()
  const selectedAvailable = (() => {
    if (!selected) return true
    if (selected.startsWith('ollama/')) {
      const localName = selected.replace(/^ollama\//, '')
      return localModels.some((model) => String(model?.name || model || '').trim() === localName)
    }
    const provider = selected.split('/')[0]
    const model = selected.replace(`${provider}/`, '')
    const status = providerStatuses[provider] || {}
    const selectable = Array.isArray(status.selectable_models) ? status.selectable_models : []
    return selectable.includes(model)
  })()

  useEffect(() => {
    if (!open) return undefined
    const onMouseDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [open])

  useLayoutEffect(() => {
    if (!open) return undefined

    const updateDropdownPosition = () => {
      const trigger = triggerRef.current
      if (!trigger) return
      const rect = trigger.getBoundingClientRect()
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight
      const margin = 16
      const gap = 8
      const width = Math.min(420, Math.max(280, viewportWidth - margin * 2))
      const left = Math.max(margin, Math.min(rect.left, viewportWidth - width - margin))
      const spaceBelow = viewportHeight - rect.bottom - gap - margin
      const spaceAbove = rect.top - gap - margin
      const openUpward = spaceBelow < 260 && spaceAbove > spaceBelow
      const maxHeight = Math.max(180, (openUpward ? spaceAbove : spaceBelow))

      setDropdownStyle({
        position: 'fixed',
        left: `${left}px`,
        width: `${width}px`,
        maxHeight: `${maxHeight}px`,
        [openUpward ? 'bottom' : 'top']: `${Math.round(openUpward ? viewportHeight - rect.top + gap : rect.bottom + gap)}px`,
        [openUpward ? 'top' : 'bottom']: 'auto',
      })
    }

    updateDropdownPosition()
    window.addEventListener('resize', updateDropdownPosition)
    window.addEventListener('scroll', updateDropdownPosition, true)
    return () => {
      window.removeEventListener('resize', updateDropdownPosition)
      window.removeEventListener('scroll', updateDropdownPosition, true)
    }
  }, [open])

  return (
    <div className="mp-root sl-model-picker" ref={rootRef}>
      <button
        ref={triggerRef}
        className={`mp-trigger${selected && !selectedAvailable ? ' mp-trigger--warn' : ''}`}
        onClick={() => setOpen((value) => !value)}
      >
        <span className={`mp-provider-dot ${selectedProvider || 'auto'}`} />
        <span className="mp-trigger-label">{modelLabel(selected)}</span>
        {selected && !selectedAvailable && <span className="mp-trigger-warn">Locked</span>}
        <span className="sl-model-trigger-caret">⌄</span>
      </button>
      {open && (
        <div className="mp-dropdown" style={dropdownStyle || undefined}>
          {PROVIDERS.map((provider) => {
            const status = providerStatuses[provider.id] || {}
            const hasKey = !!String(state.settings?.[provider.settingsKey] || '').trim()
            const tone = status?.checking ? 'checking' : status?.error ? 'error' : hasKey ? 'ok' : 'missing'
            const toneLabel = status?.checking ? 'Checking' : status?.error ? 'Error' : hasKey ? 'Ready' : 'Locked'
            const models = buildProviderModels(provider.id, status)
            return (
              <div key={provider.id} className="mp-group">
                <div className="mp-group-label mp-group-label--row">
                  <span className={`mp-provider-dot ${provider.id}`} />
                  <span>{provider.label}</span>
                  <span className={`mp-key-badge ${tone}`}>{toneLabel}</span>
                </div>
                {models.map((entry) => {
                  const name = String(entry.name || '').trim()
                  const id = `${provider.id}/${name}`
                  const disabled = !entry.available
                  return (
                    <button
                      key={id}
                      className={`mp-option ${selected === id ? 'active' : ''}${disabled ? ' mp-option--dim' : ''}`}
                      disabled={disabled}
                      onClick={() => {
                        if (disabled) return
                        dispatch({ type: 'SET_MODEL', model: id })
                        setOpen(false)
                      }}
                    >
                      <span className="mp-option-name">{name}</span>
                      {entry.badge && <span className={`mp-model-badge ${entry.badge}`}>{entry.badge}</span>}
                      {typeof entry.agentCapable === 'boolean' && (
                        <span className={`mp-model-badge ${entry.agentCapable ? 'agent' : 'noagent'}`}>
                          {entry.agentCapable ? 'agent' : 'text'}
                        </span>
                      )}
                      {disabled ? <span className="mp-lock">🔒</span> : selected === id ? <span className="mp-option-check">✓</span> : null}
                    </button>
                  )
                })}
              </div>
            )
          })}

          <div className="mp-group">
            <div className="mp-group-label mp-group-label--row">
              <span className="mp-provider-dot ollama" />
              <span>Local models</span>
              <button className="mp-refresh-btn" onClick={() => refreshOllamaModels(true)}>↻</button>
            </div>
            {localModels.length === 0 ? (
              <div className="mp-empty">No local models found.</div>
            ) : (
              localModels.map((model) => {
                const name = String(model?.name || model || '').trim()
                const id = `ollama/${name}`
                return (
                  <button
                    key={id}
                    className={`mp-option ${selected === id ? 'active' : ''}`}
                    onClick={() => {
                      dispatch({ type: 'SET_MODEL', model: id })
                      setOpen(false)
                    }}
                  >
                    <span className="mp-option-name">{name}</span>
                    <span className="mp-model-badge agent">local</span>
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

function StudioModelGate({ state, dispatch, localModels, refreshModelInventory, refreshOllamaModels }) {
  const api = window.kendrAPI
  const [setupMode, setSetupMode] = useState('api')
  const [providerId, setProviderId] = useState('openai')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const selectedProvider = PROVIDERS.find((item) => item.id === providerId) || PROVIDERS[0]

  const saveProvider = async () => {
    const value = String(apiKey || '').trim()
    if (!value) {
      setError('Enter an API key first.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api?.settings.set(selectedProvider.settingsKey, value)
      dispatch({ type: 'SET_SETTINGS', settings: { [selectedProvider.settingsKey]: value } })
      if (state.backendStatus === 'running') {
        await api?.backend.restart()
      } else {
        await api?.backend.start()
      }
      await refreshModelInventory(true)
      dispatch({ type: 'SET_MODEL', model: selectedProvider.defaultModel })
    } catch (err) {
      setError(String(err?.message || err || 'Could not save provider key.'))
    } finally {
      setSaving(false)
    }
  }

  const selectLocalModel = async (model) => {
    const name = String(model?.name || model || '').trim()
    if (!name) return
    dispatch({ type: 'SET_MODEL', model: `ollama/${name}` })
    if (state.backendStatus !== 'running') {
      await api?.backend.start().catch(() => {})
    }
  }

  return (
    <div className="sl-gate">
      <div className="sl-gate-card">
        <div className="sl-gate-badge">First step</div>
        <h1 className="sl-gate-title">Connect one model to start</h1>
        <p className="sl-gate-copy">
          Start with one cloud API key or one local model. Everything else stays tucked into the menu until you need it.
        </p>

        <div className="sl-gate-tabs">
          <button className={`sl-gate-tab ${setupMode === 'api' ? 'active' : ''}`} onClick={() => setSetupMode('api')}>Use API key</button>
          <button className={`sl-gate-tab ${setupMode === 'local' ? 'active' : ''}`} onClick={() => { setSetupMode('local'); refreshOllamaModels(true) }}>Use local model</button>
        </div>

        {setupMode === 'api' ? (
          <div className="sl-gate-form">
            <div className="sl-gate-provider-row">
              {PROVIDERS.map((provider) => (
                <button
                  key={provider.id}
                  className={`sl-gate-provider ${provider.id === providerId ? 'active' : ''}`}
                  onClick={() => setProviderId(provider.id)}
                >
                  {provider.label}
                </button>
              ))}
            </div>
            <input
              className="sl-gate-input"
              type="password"
              placeholder={`Paste ${selectedProvider.label} API key`}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && !saving && saveProvider()}
            />
            <div className="sl-gate-actions">
              <button className="sl-gate-cta" disabled={saving || !apiKey.trim()} onClick={saveProvider}>
                {saving ? 'Connecting…' : 'Save and continue'}
              </button>
              <button className="sl-gate-link" onClick={() => dispatch({ type: 'SET_VIEW', view: 'settings' })}>
                Open full settings
              </button>
            </div>
          </div>
        ) : (
          <div className="sl-gate-form">
            <div className="sl-gate-inline-actions">
              <button className="sl-gate-link" onClick={() => refreshOllamaModels(true)}>Refresh local models</button>
              <button className="sl-gate-link" onClick={() => dispatch({ type: 'SET_VIEW', view: 'settings' })}>Open model manager</button>
            </div>
            {localModels.length === 0 ? (
              <div className="sl-gate-empty">
                No local models found yet. Pull one from the model manager, then come back here.
              </div>
            ) : (
              <div className="sl-gate-local-list">
                {localModels.map((model) => {
                  const name = String(model?.name || model || '').trim()
                  const size = model?.size ? `${(Number(model.size) / 1e9).toFixed(1)} GB` : ''
                  return (
                    <button key={name} className="sl-gate-local-item" onClick={() => selectLocalModel(model)}>
                      <span className="sl-gate-local-name">{name}</span>
                      {size && <span className="sl-gate-local-size">{size}</span>}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {!!error && <div className="sl-gate-error">{error}</div>}
      </div>
    </div>
  )
}
