import React, { useEffect } from 'react'
import { useApp } from './contexts/AppContext'
import StatusBar from './components/StatusBar'
import CommandPalette from './components/CommandPalette'
import ProjectWorkspace from './panels/ProjectWorkspace'
import MCPPanel from './panels/MCPPanel'
import AgentsPanel from './panels/AgentsPanel'
import SkillsPanel from './panels/SkillsPanel'
import ModelManager from './panels/ModelManager'
import Settings from './panels/Settings'
import AgentOrchestration from './panels/AgentOrchestration'
import MenuBar from './components/MenuBar'
import StudioLayout from './panels/StudioLayout'
import ModelDocs from './panels/ModelDocs'

// Config views that can overlay the IDE
const CONFIG_VIEWS = ['agents', 'mcp', 'skills', 'models', 'settings', 'runs', 'docs']
const CONFIG_TITLES = {
  agents:   'Agents & Capabilities',
  mcp:      'MCP Servers',
  skills:   'Skills',
  models:   'Model Manager',
  settings: 'Settings',
  runs:     'Runs & Orchestration',
  docs:     'Model Docs',
}

export default function App() {
  const { state, dispatch } = useApp()
  const v = state.activeView
  const isStudio = state.appMode === 'studio'
  const isConfigView = CONFIG_VIEWS.includes(v)

  // Close config overlay with Escape
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape' && isConfigView && !isStudio) {
        dispatch({ type: 'SET_VIEW', view: 'files' })
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isConfigView, isStudio, dispatch])

  const closeOverlay = () => dispatch({ type: 'SET_VIEW', view: 'files' })

  return (
    <div className="app-root">
      {/* ── Titlebar ── */}
      <div className="titlebar" style={{ WebkitAppRegion: 'drag' }}>
        <div className="titlebar-icon" style={{ WebkitAppRegion: 'no-drag' }}>K</div>
        <MenuBar />
        <ModeSwitch />
        <div className="titlebar-center" style={{ WebkitAppRegion: 'drag' }}>
          {!isStudio && state.projectRoot && (
            <span className="titlebar-project">{state.projectRoot.split(/[\\/]/).pop()}</span>
          )}
        </div>
        <div className="titlebar-spacer" />
      </div>

      <div className="app-body">
        {/* ── Studio mode ── */}
        {isStudio && !isConfigView && <StudioLayout />}

        {/* ── Studio mode: config views with back button ── */}
        {isStudio && isConfigView && (
          <div className="full-view">
            <div className="sl-back-bar">
              <button className="sl-back-btn" onClick={() => dispatch({ type: 'SET_VIEW', view: 'chat' })}>
                ← Back to Studio
              </button>
              <span className="sl-back-title">{CONFIG_TITLES[v]}</span>
            </div>
            <ConfigPanelContent v={v} />
          </div>
        )}

        {/* ── Developer mode: always the IDE ── */}
        {!isStudio && (
          <div className="dv-root">
            <ProjectWorkspace />

            {/* Config overlay — slides in from right over the IDE */}
            {isConfigView && (
              <div className="dv-overlay" onClick={(e) => { if (e.target === e.currentTarget) closeOverlay() }}>
                <div className="dv-panel">
                  <div className="dv-panel-hdr">
                    <span className="dv-panel-title">{CONFIG_TITLES[v]}</span>
                    <button className="dv-panel-close" onClick={closeOverlay} title="Close (Esc)">✕</button>
                  </div>
                  <div className="dv-panel-body">
                    <ConfigPanelContent v={v} />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <StatusBar />
      {state.commandPaletteOpen && <CommandPalette />}
    </div>
  )
}

function ConfigPanelContent({ v }) {
  return (
    <>
      {v === 'agents'   && <AgentsPanel />}
      {v === 'mcp'      && <MCPPanel />}
      {v === 'skills'   && <SkillsPanel />}
      {v === 'runs'     && <AgentOrchestration />}
      {v === 'models'   && <FullPageWrap title="Model Manager"><ModelManager /></FullPageWrap>}
      {v === 'settings' && <FullPageWrap title="Settings"><Settings /></FullPageWrap>}
      {v === 'docs'     && <FullPageWrap title="Model Docs"><ModelDocs /></FullPageWrap>}
    </>
  )
}

// ── Mode Switch ───────────────────────────────────────────────────────────────
function ModeSwitch() {
  const { state, dispatch } = useApp()
  const setMode = (mode) => dispatch({ type: 'SET_APP_MODE', mode })

  return (
    <div className="ms-switch" style={{ WebkitAppRegion: 'no-drag' }}>
      <button
        className={`ms-btn ${state.appMode === 'developer' ? 'active' : ''}`}
        onClick={() => setMode('developer')}
        title="Developer — VS Code-style IDE with AI agent"
      >
        <DevIcon /> Developer
      </button>
      <button
        className={`ms-btn ${state.appMode === 'studio' ? 'active' : ''}`}
        onClick={() => setMode('studio')}
        title="Studio — Clean AI assistant interface"
      >
        <StudioIcon /> Studio
      </button>
    </div>
  )
}

function DevIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>
    </svg>
  )
}
function StudioIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>
  )
}

function FullPageWrap({ title, children }) {
  return (
    <div className="fp-wrap">
      <div className="fp-header">{title}</div>
      <div className="fp-body">{children}</div>
    </div>
  )
}
