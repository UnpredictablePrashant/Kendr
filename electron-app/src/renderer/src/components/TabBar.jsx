import React from 'react'
import { useApp } from '../contexts/AppContext'

const FILE_ICONS = {
  js: '⚡', jsx: '⚛', ts: '🔷', tsx: '⚛', py: '🐍',
  json: '{}', md: '📝', html: '🌐', css: '🎨', yml: '⚙',
  yaml: '⚙', sh: '💻', rs: '⚙', go: '🐹', java: '☕',
  sql: '🗄', txt: '📄', env: '🔐', toml: '⚙', xml: '📋'
}

export default function TabBar() {
  const { state, dispatch } = useApp()

  if (state.openTabs.length === 0) return (
    <div className="tab-bar tab-bar--empty">
      <span className="tab-bar-hint">Open a file from the explorer or let the AI create one</span>
    </div>
  )

  return (
    <div className="tab-bar">
      <div className="tabs-scroll">
        {state.openTabs.map(tab => {
          const ext = tab.name.split('.').pop()?.toLowerCase() || ''
          const icon = FILE_ICONS[ext] || '📄'
          const isActive = tab.path === state.activeTabPath

          return (
            <div
              key={tab.path}
              className={`tab ${isActive ? 'tab--active' : ''} ${tab.modified ? 'tab--modified' : ''}`}
              onClick={() => dispatch({ type: 'SET_ACTIVE_TAB', path: tab.path })}
              title={tab.path}
            >
              <span className="tab-icon">{icon}</span>
              <span className="tab-name">{tab.name}</span>
              {tab.modified && <span className="tab-dot" />}
              <button
                className="tab-close"
                onClick={e => {
                  e.stopPropagation()
                  dispatch({ type: 'CLOSE_TAB', path: tab.path })
                }}
                title="Close"
              >
                ×
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
