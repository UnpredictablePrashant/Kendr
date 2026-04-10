import React from 'react'
import { useApp } from '../contexts/AppContext'
import FileExplorer from '../panels/FileExplorer'
import GitPanel from '../panels/GitPanel'
import Settings from '../panels/Settings'
import ModelManager from '../panels/ModelManager'

export default function Sidebar() {
  const { state } = useApp()

  const panels = {
    files:        { title: 'EXPLORER',         component: <FileExplorer /> },
    git:          { title: 'SOURCE CONTROL',   component: <GitPanel /> },
    orchestration:{ title: 'ORCHESTRATION',    component: <AgentList /> },
    models:       { title: 'MODEL MANAGER',    component: <ModelManager /> },
    settings:     { title: 'SETTINGS',         component: <Settings /> },
  }

  const panel = panels[state.activeView]
  if (!panel) return null

  return (
    <div className="sidebar">
      <div className="sidebar-header">{panel.title}</div>
      <div className="sidebar-content">
        {panel.component}
      </div>
    </div>
  )
}

// Minimal agent list in sidebar (full view is in main area)
function AgentList() {
  const { state } = useApp()
  const runs = state.runs.slice(0, 20)

  return (
    <div className="sidebar-section">
      <div className="sidebar-label">RECENT RUNS</div>
      {runs.length === 0 && (
        <div className="sidebar-empty">No runs yet. Start a conversation in the chat panel.</div>
      )}
      {runs.map(run => (
        <div key={run.run_id} className="run-item">
          <span className={`run-dot run-dot--${run.status || 'pending'}`} />
          <span className="run-label">{(run.text || run.run_id || '').slice(0, 40)}</span>
        </div>
      ))}
    </div>
  )
}
