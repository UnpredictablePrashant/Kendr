import React from 'react'
import { useApp } from '../contexts/AppContext'

export default function HomePanel() {
  const { state, dispatch } = useApp()
  const runs = Array.isArray(state.runs) ? state.runs : []
  const recentRuns = runs.slice(0, 4)
  const connectedCloudProviders = [
    state.settings?.openaiKey,
    state.settings?.anthropicKey,
    state.settings?.googleKey,
    state.settings?.xaiKey,
  ].filter(Boolean).length
  const localModels = Array.isArray(state.ollamaModels) ? state.ollamaModels.length : 0

  const primaryAction = connectedCloudProviders || localModels
    ? { label: 'Create Assistant', target: 'studio' }
    : { label: 'Connect AI Engine', target: 'settings' }

  return (
    <div className="kendr-page kendr-home">
      <section className="hero-card">
        <div className="hero-copy">
          <span className="eyebrow">AI Operating System</span>
          <h1>Kendr unifies assistants, tools, memory, and runs in one workspace.</h1>
          <p>
            Build in chat, connect your systems, route across local and cloud models,
            and inspect every run without leaving the product shell.
          </p>
          <div className="hero-actions">
            <button className="kendr-btn kendr-btn--primary" onClick={() => dispatch({ type: 'SET_VIEW', view: primaryAction.target })}>
              {primaryAction.label}
            </button>
            <button className="kendr-btn kendr-btn--ghost" onClick={() => dispatch({ type: 'SET_VIEW', view: 'developer' })}>
              Open Developer Workspace
            </button>
          </div>
        </div>
        <div className="hero-metrics">
          <MetricCard label="Connected cloud providers" value={String(connectedCloudProviders)} detail="OpenAI, Anthropic, Google, xAI" />
          <MetricCard label="Detected local models" value={String(localModels)} detail="Ollama-ready engines" />
          <MetricCard label="Recent runs" value={String(runs.length)} detail="Durable execution history" />
        </div>
      </section>

      <section className="grid-two">
        <div className="surface-card">
          <SectionHeader title="Recommended Next Steps" subtitle="Get to a complete first run quickly." />
          <ActionRow
            title="Create your first Studio assistant"
            detail="Describe a task, let Kendr wire the basics, then test it in chat."
            actionLabel="Open Studio"
            onAction={() => dispatch({ type: 'SET_VIEW', view: 'studio' })}
          />
          <ActionRow
            title="Connect tools and tool sources"
            detail="Install connectors, import MCP servers, and make capabilities available to agents."
            actionLabel="Open Integrations"
            onAction={() => dispatch({ type: 'SET_VIEW', view: 'integrations' })}
          />
          <ActionRow
            title="Inspect execution traces"
            detail="See what tools, models, and memory were used during every run."
            actionLabel="Open Runs"
            onAction={() => dispatch({ type: 'SET_VIEW', view: 'runs' })}
          />
        </div>

        <div className="surface-card">
          <SectionHeader title="Workspace Status" subtitle="A product view of the current environment." />
          <div className="status-grid">
            <StatusPill label="Backend" value={state.backendStatus} tone={state.backendStatus === 'running' ? 'ok' : 'warn'} />
            <StatusPill label="Project" value={state.projectRoot ? state.projectRoot.split(/[\\/]/).pop() : 'Not connected'} tone={state.projectRoot ? 'neutral' : 'warn'} />
            <StatusPill label="Mode" value={state.appMode === 'studio' ? 'Studio' : 'Developer'} tone="neutral" />
            <StatusPill label="Selected model" value={state.selectedModel || 'Auto routing'} tone="neutral" />
          </div>
        </div>
      </section>

      <section className="surface-card">
        <SectionHeader title="Recent Activity" subtitle="The most recent assistant and workflow runs." />
        {recentRuns.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__title">No runs yet</div>
            <div className="empty-state__body">Start in Studio to create an assistant or open Runs after your first task completes.</div>
          </div>
        ) : (
          <div className="run-table">
            {recentRuns.map((run) => (
              <button key={run.run_id} className="run-table__row" onClick={() => dispatch({ type: 'SET_VIEW', view: 'runs' })}>
                <span className={`run-dot run-dot--${run.status || 'pending'}`} />
                <span className="run-table__title">{(run.text || run.workflow_id || run.run_id || 'Untitled run').slice(0, 64)}</span>
                <span className="run-table__status">{run.status || 'pending'}</span>
                <span className="run-table__date">{run.created_at ? new Date(run.created_at).toLocaleString() : 'recent'}</span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SectionHeader({ title, subtitle }) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </div>
  )
}

function MetricCard({ label, value, detail }) {
  return (
    <div className="metric-card">
      <span className="metric-card__label">{label}</span>
      <span className="metric-card__value">{value}</span>
      <span className="metric-card__detail">{detail}</span>
    </div>
  )
}

function ActionRow({ title, detail, actionLabel, onAction }) {
  return (
    <div className="action-row">
      <div>
        <div className="action-row__title">{title}</div>
        <div className="action-row__detail">{detail}</div>
      </div>
      <button className="kendr-btn kendr-btn--ghost" onClick={onAction}>{actionLabel}</button>
    </div>
  )
}

function StatusPill({ label, value, tone }) {
  return (
    <div className={`status-pill status-pill--${tone}`}>
      <span className="status-pill__label">{label}</span>
      <span className="status-pill__value">{value}</span>
    </div>
  )
}
