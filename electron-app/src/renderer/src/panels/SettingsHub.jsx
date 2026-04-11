import React, { useState } from 'react'
import Settings from './Settings'
import ModelManager from './ModelManager'
import ModelDocs from './ModelDocs'

const TABS = [
  { id: 'engines', label: 'AI Engines' },
  { id: 'workspace', label: 'Workspace' },
  { id: 'docs', label: 'Model Docs' },
]

export default function SettingsHub() {
  const [tab, setTab] = useState('engines')

  return (
    <div className="kendr-page">
      <div className="surface-card surface-card--tight">
        <div className="section-header">
          <div>
            <h2>Settings</h2>
            <p>Configure AI engines, workspace preferences, and provider guidance in one place.</p>
          </div>
        </div>
        <div className="kendr-tabs">
          {TABS.map((item) => (
            <button key={item.id} className={`kendr-tab ${tab === item.id ? 'active' : ''}`} onClick={() => setTab(item.id)}>
              {item.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'engines' && <ModelManager />}
      {tab === 'workspace' && <Settings />}
      {tab === 'docs' && <ModelDocs />}
    </div>
  )
}
