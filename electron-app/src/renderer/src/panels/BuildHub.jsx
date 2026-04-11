import React, { useState } from 'react'
import AgentsPanel from './AgentsPanel'
import ProjectWorkspace from './ProjectWorkspace'
import SkillsPanel from './SkillsPanel'
import AssistantBuilder from './AssistantBuilder'

const TABS = [
  { id: 'assistants', label: 'Assistants' },
  { id: 'capabilities', label: 'Capabilities' },
  { id: 'skills', label: 'Skills' },
  { id: 'developer', label: 'Developer Workspace' },
]

export default function BuildHub() {
  const [tab, setTab] = useState('assistants')

  return (
    <div className="kendr-page">
      <div className="surface-card surface-card--tight">
        <div className="section-header">
          <div>
            <h2>Build</h2>
            <p>Create assistants, refine skills, and drop into the developer workspace when you need full control.</p>
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

      <div className="build-content">
        {tab === 'assistants' && <AssistantBuilder />}
        {tab === 'capabilities' && <AgentsPanel />}
        {tab === 'skills' && <SkillsPanel />}
        {tab === 'developer' && (
          <div className="developer-frame">
            <ProjectWorkspace />
          </div>
        )}
      </div>
    </div>
  )
}
