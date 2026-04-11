import React from 'react'
import { useApp } from '../contexts/AppContext'

export default function MemoryHub() {
  const { state, dispatch } = useApp()
  const localModels = Array.isArray(state.ollamaModels) ? state.ollamaModels.length : 0

  return (
    <div className="kendr-page">
      <section className="surface-card">
        <div className="section-header">
          <div>
            <h2>Memory</h2>
            <p>Turn documents, local files, and saved workspace context into reusable knowledge for assistants and workflows.</p>
          </div>
        </div>
        <div className="memory-grid">
          <MemoryCard
            title="Knowledge Bases"
            body="Build reusable retrieval layers from folders, URLs, databases, and cloud drives."
            badge="RAG-ready"
          />
          <MemoryCard
            title="Session Memory"
            body="Keep short-term context across a conversation or run without overloading the prompt."
            badge="Ephemeral"
          />
          <MemoryCard
            title="Long-Term Memory"
            body="Store durable notes, run outcomes, and workspace knowledge across tasks."
            badge="Persistent"
          />
        </div>
      </section>

      <section className="grid-two">
        <div className="surface-card">
          <div className="section-header">
            <div>
              <h2>Recommended Next Step</h2>
              <p>The memory console is not fully surfaced in the desktop app yet, but the platform primitives already exist.</p>
            </div>
          </div>
          <div className="action-row">
            <div>
              <div className="action-row__title">Use Studio for memory-backed assistants</div>
              <div className="action-row__detail">Start in Studio, then attach knowledge and tools as your workflows mature.</div>
            </div>
            <button className="kendr-btn kendr-btn--ghost" onClick={() => dispatch({ type: 'SET_VIEW', view: 'studio' })}>
              Open Studio
            </button>
          </div>
          <div className="action-row">
            <div>
              <div className="action-row__title">Inspect retrieval activity through runs</div>
              <div className="action-row__detail">Use the run inspector to validate what the assistant used and what it missed.</div>
            </div>
            <button className="kendr-btn kendr-btn--ghost" onClick={() => dispatch({ type: 'SET_VIEW', view: 'runs' })}>
              Open Runs
            </button>
          </div>
        </div>

        <div className="surface-card">
          <div className="section-header">
            <div>
              <h2>Environment Snapshot</h2>
              <p>Key setup signals that influence memory and retrieval behavior.</p>
            </div>
          </div>
          <div className="status-grid">
            <div className="status-pill status-pill--neutral">
              <span className="status-pill__label">Backend status</span>
              <span className="status-pill__value">{state.backendStatus}</span>
            </div>
            <div className="status-pill status-pill--neutral">
              <span className="status-pill__label">Project root</span>
              <span className="status-pill__value">{state.projectRoot ? state.projectRoot.split(/[\\/]/).pop() : 'Not connected'}</span>
            </div>
            <div className="status-pill status-pill--neutral">
              <span className="status-pill__label">Selected model</span>
              <span className="status-pill__value">{state.selectedModel || 'Auto'}</span>
            </div>
            <div className="status-pill status-pill--neutral">
              <span className="status-pill__label">Local models</span>
              <span className="status-pill__value">{localModels}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

function MemoryCard({ title, body, badge }) {
  return (
    <div className="memory-card">
      <span className="memory-card__badge">{badge}</span>
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  )
}
