import React, { useRef, useState, useCallback, useEffect } from 'react'
import { useApp } from '../contexts/AppContext'
import FileExplorer from './FileExplorer'
import EditorPanel from './EditorPanel'
import TabBar from '../components/TabBar'
import TerminalPanel from './TerminalPanel'
import AIComposer from './AIComposer'
import RunPanel from './RunPanel'
import GitPanel from './GitPanel'
import AgentOrchestration from './AgentOrchestration'

export default function ProjectWorkspace() {
  const { state, dispatch, openFile } = useApp()
  const editorInstanceRef = useRef(null)

  // Panel sizes
  const [leftW, setLeftW]     = useState(240)
  const [rightW, setRightW]   = useState(360)
  const [bottomH, setBottomH] = useState(240)
  const [showBottom, setShowBottom] = useState(false)
  const [bottomTab, setBottomTab]   = useState('terminal')
  const [leftTab, setLeftTab]       = useState('files')  // files | search | git

  // Inline Cmd+K overlay
  const [inlineEdit, setInlineEdit] = useState(null)  // {top, path, selectedText}
  const inlineInputRef = useRef(null)

  // Drag state refs
  const dragging = useRef(null)

  const onDividerMouseDown = useCallback((which, e) => {
    e.preventDefault()
    dragging.current = { which, startX: e.clientX, startY: e.clientY, startLeft: leftW, startRight: rightW, startBottom: bottomH }
    const onMove = (ev) => {
      if (!dragging.current) return
      const d = dragging.current
      if (d.which === 'left')   setLeftW(Math.max(180, Math.min(480, d.startLeft + (ev.clientX - d.startX))))
      else if (d.which === 'right') setRightW(Math.max(280, Math.min(640, d.startRight - (ev.clientX - d.startX))))
      else setBottomH(Math.max(80, Math.min(560, d.startBottom - (ev.clientY - d.startY))))
    }
    const onUp = () => {
      dragging.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [leftW, rightW, bottomH])

  // Listen for Ctrl+K from EditorPanel → show inline overlay
  useEffect(() => {
    const handler = (e) => {
      setInlineEdit({ top: e.detail?.top ?? 80, path: e.detail?.path, selectedText: e.detail?.selectedText || '' })
      setTimeout(() => inlineInputRef.current?.focus(), 60)
      // Also open composer in edit mode
      if (!state.composerOpen) dispatch({ type: 'TOGGLE_COMPOSER' })
      window.dispatchEvent(new CustomEvent('kendr:composer-set-mode', { detail: 'edit' }))
    }
    window.addEventListener('kendr:inline-edit', handler)
    return () => window.removeEventListener('kendr:inline-edit', handler)
  }, [state.composerOpen, dispatch])

  // Ctrl+K with no inline → switch composer to edit
  useEffect(() => {
    const handler = () => {
      if (!state.composerOpen) dispatch({ type: 'TOGGLE_COMPOSER' })
      window.dispatchEvent(new CustomEvent('kendr:composer-set-mode', { detail: 'edit' }))
    }
    window.addEventListener('kendr:composer-edit', handler)
    return () => window.removeEventListener('kendr:composer-edit', handler)
  }, [state.composerOpen, dispatch])

  // Menu bar events
  useEffect(() => {
    const openTerminal = () => { setBottomTab('terminal'); setShowBottom(true) }
    const openRun      = () => { setBottomTab('run');      setShowBottom(true) }
    window.addEventListener('kendr:open-terminal',  openTerminal)
    window.addEventListener('kendr:open-run-panel', openRun)
    return () => {
      window.removeEventListener('kendr:open-terminal',  openTerminal)
      window.removeEventListener('kendr:open-run-panel', openRun)
    }
  }, [])

  // Ctrl+Shift+F → open search tab
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'F') {
        e.preventDefault()
        setLeftTab('search')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const toggleBottom = (tab) => {
    if (showBottom && bottomTab === tab) setShowBottom(false)
    else { setBottomTab(tab); setShowBottom(true) }
  }

  const submitInlineEdit = () => {
    const instruction = inlineInputRef.current?.value?.trim()
    if (!instruction) { setInlineEdit(null); return }
    window.dispatchEvent(new CustomEvent('kendr:inline-edit-submit', { detail: { instruction, path: inlineEdit?.path, selectedText: inlineEdit?.selectedText } }))
    setInlineEdit(null)
  }

  return (
    <div className="pw-root">
      {/* ── Three-pane body ── */}
      <div className="pw-main" style={{ bottom: showBottom ? bottomH + 1 : 0 }}>

        {/* Left sidebar */}
        <div className="pw-left" style={{ width: leftW }}>
          <div className="pw-left-tabs">
            {/* Top: primary views */}
            <button className={`pw-left-tab ${leftTab === 'files' ? 'active' : ''}`} onClick={() => setLeftTab('files')} title="Explorer (Ctrl+Shift+E)">
              <FilesTabIcon />
            </button>
            <button className={`pw-left-tab ${leftTab === 'search' ? 'active' : ''}`} onClick={() => setLeftTab('search')} title="Search (Ctrl+Shift+F)">
              <SearchTabIcon />
            </button>
            <button className={`pw-left-tab ${leftTab === 'git' ? 'active' : ''}`} onClick={() => setLeftTab('git')} title="Source Control">
              <GitTabIcon />
            </button>
            <button className={`pw-left-tab ${leftTab === 'runs' ? 'active' : ''}`} onClick={() => setLeftTab('runs')} title="Runs & Orchestration">
              <RunsTabIcon />
            </button>

            {/* Spacer pushes bottom icons down */}
            <div className="pw-left-tab-spacer" />

            {/* Bottom: extensions & settings (like VS Code) */}
            <button
              className={`pw-left-tab pw-left-tab--bottom ${leftTab === 'extensions' ? 'active' : ''}`}
              onClick={() => setLeftTab(leftTab === 'extensions' ? 'files' : 'extensions')}
              title="Agents, MCP & Skills"
            >
              <ExtensionsTabIcon />
            </button>
            <button
              className={`pw-left-tab pw-left-tab--bottom ${leftTab === 'settings' ? 'active' : ''}`}
              onClick={() => setLeftTab(leftTab === 'settings' ? 'files' : 'settings')}
              title="Settings"
            >
              <SettingsTabIcon />
            </button>
          </div>
          <div className="pw-left-body">
            {leftTab === 'files'      && <FileExplorer />}
            {leftTab === 'search'     && <SearchPanel projectRoot={state.projectRoot} onOpenFile={openFile} />}
            {leftTab === 'git'        && <GitPanel />}
            {leftTab === 'runs'       && <AgentOrchestration />}
            {leftTab === 'extensions' && <ExtensionsPanel onNavigate={(view) => dispatch({ type: 'SET_VIEW', view })} />}
            {leftTab === 'settings'   && <SettingsSidebar onNavigate={(view) => dispatch({ type: 'SET_VIEW', view })} />}
          </div>
        </div>

        <div className="pw-divider-v" onMouseDown={(e) => onDividerMouseDown('left', e)} />

        {/* Center: editor */}
        <div className="pw-center">
          <div className="pw-center-toolbar">
            <TabBar />
            <div className="pw-toolbar-actions">
              <button className={`pw-tool-btn ${showBottom && bottomTab === 'terminal' ? 'active' : ''}`} title="Terminal (Ctrl+`)" onClick={() => toggleBottom('terminal')}>
                <TermIcon />
              </button>
              <button className={`pw-tool-btn ${showBottom && bottomTab === 'run' ? 'active' : ''}`} title="Activity Panel" onClick={() => toggleBottom('run')}>
                <RunIcon />
              </button>
              <button className={`pw-tool-btn ${state.composerOpen ? 'active' : ''}`} title="Workflow Panel (Ctrl+Shift+A)" onClick={() => dispatch({ type: 'TOGGLE_COMPOSER' })}>
                <ComposerIcon />
              </button>
            </div>
          </div>

          {/* Editor area — position:relative for inline overlay */}
          <div className="pw-editor-area" style={{ position: 'relative' }}>
            {state.openTabs.length > 0 ? (
              <EditorPanel onEditorMount={(ed) => { editorInstanceRef.current = ed }} />
            ) : (
              <ProjectWelcome onOpenTerminal={() => toggleBottom('terminal')} onOpenRun={() => toggleBottom('run')} />
            )}

            {/* Inline Cmd+K edit overlay */}
            {inlineEdit && (
              <div
                className="ile-widget"
                style={{ top: Math.min(inlineEdit.top, 400) + 'px' }}
              >
                {inlineEdit.selectedText && (
                  <div className="ile-preview">
                    {inlineEdit.selectedText.split('\n').slice(0, 3).join('\n')}
                    {inlineEdit.selectedText.split('\n').length > 3 ? '\n…' : ''}
                  </div>
                )}
                <div className="ile-row">
                  <span className="ile-icon">✨</span>
                  <input
                    ref={inlineInputRef}
                    className="ile-input"
                    placeholder="Edit with AI… (Enter to apply, Esc to cancel)"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { e.preventDefault(); submitInlineEdit() }
                      if (e.key === 'Escape') setInlineEdit(null)
                    }}
                  />
                  <button className="ile-submit" onClick={submitInlineEdit}>↩</button>
                  <button className="ile-cancel" onClick={() => setInlineEdit(null)}>✕</button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Agent panel */}
        {state.composerOpen && (
          <>
            <div className="pw-divider-v" onMouseDown={(e) => onDividerMouseDown('right', e)} />
            <div className="pw-right" style={{ width: rightW }}>
              <AIComposer editorInstanceRef={editorInstanceRef} />
            </div>
          </>
        )}
      </div>

      {/* Bottom panel */}
      {showBottom && (
        <>
          <div className="pw-divider-h" style={{ bottom: bottomH }} onMouseDown={(e) => onDividerMouseDown('bottom', e)} />
          <div className="pw-bottom" style={{ height: bottomH }}>
            <div className="pw-bottom-header">
              <button className={`pw-bottom-tab ${bottomTab === 'terminal' ? 'active' : ''}`} onClick={() => setBottomTab('terminal')}>Terminal</button>
              <button className={`pw-bottom-tab ${bottomTab === 'run' ? 'active' : ''}`} onClick={() => setBottomTab('run')}>Activity</button>
              <div className="pw-bottom-spacer" />
              <button className="pw-bottom-close" onClick={() => setShowBottom(false)}>✕</button>
            </div>
            <div className="pw-bottom-body">
              {bottomTab === 'terminal' && <TerminalPanel />}
              {bottomTab === 'run'      && <RunPanel />}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Search panel ─────────────────────────────────────────────────────────────
function SearchPanel({ projectRoot, onOpenFile }) {
  const [query, setQuery]     = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)
  const base = (window.__kendrBackendUrl) || 'http://127.0.0.1:2151'

  const search = useCallback(async (q) => {
    if (!q.trim()) { setResults([]); return }
    setSearching(true)
    try {
      // Try backend file search
      const r = await fetch(`${base}/api/files/search?q=${encodeURIComponent(q)}&root=${encodeURIComponent(projectRoot || '')}`)
      if (r.ok) {
        const data = await r.json()
        setResults(data.results || data.matches || [])
      } else {
        setResults([])
      }
    } catch {
      setResults([])
    }
    setSearching(false)
  }, [base, projectRoot])

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => { if (query) search(query) }, 350)
    return () => clearTimeout(t)
  }, [query, search])

  return (
    <div className="pw-search-panel">
      <div className="pw-search-header">
        <span className="pw-search-title">SEARCH</span>
      </div>
      <div className="pw-search-input-row">
        <input
          className="pw-search-input"
          placeholder="Search files… (Ctrl+Shift+F)"
          value={query}
          onChange={e => { setQuery(e.target.value); if (!e.target.value) setResults([]) }}
        />
        {query && <button className="pw-search-clear" onClick={() => { setQuery(''); setResults([]) }}>✕</button>}
      </div>
      {searching && <div className="pw-search-status">Searching…</div>}
      {!searching && results.length === 0 && query && (
        <div className="pw-search-status">No results for "{query}"</div>
      )}
      <div className="pw-search-results">
        {results.map((r, i) => (
          <button key={i} className="pw-search-result" onClick={() => onOpenFile(r.path || r.file)}>
            <span className="pw-search-result-file">{(r.file || r.path || '').split(/[\\/]/).pop()}</span>
            {r.line && <span className="pw-search-result-line">:{r.line}</span>}
            {r.text && <span className="pw-search-result-text">{(r.text || '').trim().slice(0, 60)}</span>}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Welcome pane ──────────────────────────────────────────────────────────────
function ProjectWelcome({ onOpenTerminal, onOpenRun }) {
  const { state, dispatch } = useApp()
  const quickActions = [
    { label: 'Open File',     icon: '📄', action: () => dispatch({ type: 'SET_VIEW', view: 'files' }) },
    { label: 'Terminal',      icon: '⌨',  action: onOpenTerminal },
    { label: 'Run Project',   icon: '▶',  action: onOpenRun },
    { label: 'Agent Panel',   icon: '✨', action: () => dispatch({ type: 'TOGGLE_COMPOSER' }) },
  ]
  return (
    <div className="pw-welcome">
      <div className="pw-welcome-logo">⚡</div>
      <h1 className="pw-welcome-name">
        {state.projectRoot ? state.projectRoot.split(/[\\/]/).pop() : 'Kendr'}
      </h1>
      <p className="pw-welcome-path">{state.projectRoot || 'No project folder open'}</p>
      <div className="pw-welcome-grid">
        {quickActions.map(a => (
          <button key={a.label} className="pw-welcome-card" onClick={a.action}>
            <span className="pw-welcome-card-icon">{a.icon}</span>
            <span className="pw-welcome-card-label">{a.label}</span>
          </button>
        ))}
      </div>
      <div className="pw-welcome-tips">
        <span className="pw-tip"><kbd>Ctrl+K</kbd> Edit with AI</span>
        <span className="pw-tip"><kbd>Ctrl+Shift+F</kbd> Search</span>
        <span className="pw-tip"><kbd>Ctrl+`</kbd> Terminal</span>
        <span className="pw-tip"><kbd>Ctrl+Shift+P</kbd> Commands</span>
      </div>
    </div>
  )
}

// ── Extensions sidebar panel ──────────────────────────────────────────────────
function ExtensionsPanel({ onNavigate }) {
  const ITEMS = [
    { id: 'agents', icon: '🤖', label: 'Agents & Capabilities', desc: 'Manage kendr agents and their tools' },
    { id: 'mcp',    icon: '🔌', label: 'MCP Servers',           desc: 'Model Context Protocol integrations' },
    { id: 'skills', icon: '⭐', label: 'Skills',                desc: 'Intent-based skill routing' },
    { id: 'models', icon: '🗄', label: 'Model Manager',         desc: 'Pull and manage Ollama models' },
    { id: 'runs',   icon: '⏱', label: 'Runs & Orchestration',  desc: 'View active and past runs' },
  ]
  return (
    <div className="pw-ext-panel">
      <div className="pw-section-label">EXTENSIONS</div>
      {ITEMS.map(item => (
        <button key={item.id} className="pw-ext-item" onClick={() => onNavigate(item.id)}>
          <span className="pw-ext-icon">{item.icon}</span>
          <div className="pw-ext-info">
            <span className="pw-ext-name">{item.label}</span>
            <span className="pw-ext-desc">{item.desc}</span>
          </div>
          <span className="pw-ext-arrow">›</span>
        </button>
      ))}
    </div>
  )
}

// ── Settings sidebar panel ────────────────────────────────────────────────────
function SettingsSidebar({ onNavigate }) {
  const { state } = useApp()
  return (
    <div className="pw-ext-panel">
      <div className="pw-section-label">SETTINGS</div>
      <button className="pw-ext-item" onClick={() => onNavigate('settings')}>
        <span className="pw-ext-icon">⚙️</span>
        <div className="pw-ext-info">
          <span className="pw-ext-name">Preferences</span>
          <span className="pw-ext-desc">API keys, backend, UI options</span>
        </div>
        <span className="pw-ext-arrow">›</span>
      </button>
      <button className="pw-ext-item" onClick={() => onNavigate('models')}>
        <span className="pw-ext-icon">🗄</span>
        <div className="pw-ext-info">
          <span className="pw-ext-name">Model Manager</span>
          <span className="pw-ext-desc">Pull and switch Ollama models</span>
        </div>
        <span className="pw-ext-arrow">›</span>
      </button>
      <div className="pw-ext-info-block">
        <div className="pw-ext-kv"><span>Backend</span><span className={`pw-ext-badge ${state.backendStatus === 'running' ? 'ok' : 'err'}`}>{state.backendStatus}</span></div>
        <div className="pw-ext-kv"><span>Project</span><span className="pw-ext-val">{state.projectRoot ? state.projectRoot.split(/[\\/]/).pop() : '—'}</span></div>
      </div>
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────
function FilesTabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
}
function SearchTabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
}
function GitTabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9V7a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v8m12 0v2"/></svg>
}
function RunsTabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
}
function ExtensionsTabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8m-4-4v4"/><circle cx="8" cy="10" r="1.5" fill="currentColor"/><circle cx="12" cy="10" r="1.5" fill="currentColor"/><circle cx="16" cy="10" r="1.5" fill="currentColor"/></svg>
}
function SettingsTabIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
}
function TermIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
}
function RunIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
}
function ComposerIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
}
