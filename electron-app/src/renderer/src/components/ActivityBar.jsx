import React from 'react'
import { useApp } from '../contexts/AppContext'

// Top views (primary navigation)
const TOP_VIEWS = [
  { id: 'chat',         icon: ChatIcon,      title: 'Chat  (home)' },
  { id: 'runs',         icon: RunsIcon,      title: 'Runs & Orchestration' },
  { id: 'files',        icon: FilesIcon,     title: 'Explorer  (Ctrl+Shift+E)' },
  { id: 'git',          icon: GitIcon,       title: 'Source Control  (Ctrl+Shift+G)' },
  { id: 'project',      icon: ProjectIcon,   title: 'Project Mode  (Ctrl+Shift+J)' },
]

// Bottom views (config / extensions)
const BOTTOM_VIEWS = [
  { id: 'agents',       icon: AgentsIcon,    title: 'Agents & Capabilities' },
  { id: 'mcp',          icon: MCPIcon,       title: 'MCP Servers' },
  { id: 'skills',       icon: SkillsIcon,    title: 'Skills' },
  { id: 'models',       icon: ModelsIcon,    title: 'Model Manager' },
  { id: 'settings',     icon: SettingsIcon,  title: 'Settings' },
]

export default function ActivityBar() {
  const { state, dispatch } = useApp()

  const toggle = (id) => {
    // project and full-view panels just set the view directly
    const isSplit = ['files', 'git', 'orchestration'].includes(id)
    if (isSplit) {
      if (state.activeView === id && state.sidebarOpen) {
        dispatch({ type: 'TOGGLE_SIDEBAR' })
      } else {
        dispatch({ type: 'SET_VIEW', view: id })
        dispatch({ type: 'SET_SIDEBAR', open: true })
      }
    } else {
      dispatch({ type: 'SET_VIEW', view: id })
    }
  }

  const isActive = (id) => state.activeView === id

  return (
    <div className="activity-bar">
      <div className="activity-bar-top">
        {TOP_VIEWS.map(v => (
          <button
            key={v.id}
            className={`activity-btn ${isActive(v.id) ? 'active' : ''}`}
            title={v.title}
            onClick={() => toggle(v.id)}
          >
            <v.icon size={22} />
          </button>
        ))}
      </div>

      <div className="activity-bar-sep" />

      <div className="activity-bar-bottom">
        {BOTTOM_VIEWS.map(v => (
          <button
            key={v.id}
            className={`activity-btn ${isActive(v.id) ? 'active' : ''}`}
            title={v.title}
            onClick={() => toggle(v.id)}
          >
            <v.icon size={20} />
          </button>
        ))}
      </div>
    </div>
  )
}

// ── SVG icons ─────────────────────────────────────────────────────────────────
function ChatIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  )
}
function RunsIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  )
}
function FilesIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
      <polyline points="13 2 13 9 20 9"/>
    </svg>
  )
}
function GitIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>
      <path d="M18 9V7a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v8m12 0v2"/>
    </svg>
  )
}
function ProjectIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
      <rect x="3" y="14" width="7" height="7" rx="1"/>
      <path d="M14 17.5h7M17.5 14v7"/>
    </svg>
  )
}
function AgentsIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2"/>
      <path d="M8 21h8m-4-4v4"/>
      <circle cx="8" cy="10" r="1.5" fill="currentColor"/>
      <circle cx="12" cy="10" r="1.5" fill="currentColor"/>
      <circle cx="16" cy="10" r="1.5" fill="currentColor"/>
    </svg>
  )
}
function MCPIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
    </svg>
  )
}
function SkillsIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
    </svg>
  )
}
function ModelsIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3"/>
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
    </svg>
  )
}
function SettingsIcon({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  )
}
