import React, { useState, useEffect, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'

const STATUS_COLOR = {
  completed:  '#89d185',
  running:    '#3794ff',
  error:      '#f47067',
  failed:     '#f47067',
  cancelled:  '#858585',
  pending:    '#cca700',
  awaiting_user_input: '#e3b341',
}

export default function AgentOrchestration() {
  const { state, dispatch } = useApp()
  const [runs, setRuns] = useState([])
  const [selected, setSelected] = useState(null)
  const [runDetail, setRunDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const backendUrl = state.backendUrl || 'http://127.0.0.1:2151'

  const fetchRuns = useCallback(async () => {
    try {
      const r = await fetch(`${backendUrl}/api/runs`)
      if (r.ok) {
        const data = await r.json()
        const list = Array.isArray(data) ? data : (data.runs || [])
        setRuns(list)
        dispatch({ type: 'SET_RUNS', runs: list })
      }
    } catch (_) {}
  }, [backendUrl])

  const fetchDetail = useCallback(async (runId) => {
    setLoading(true)
    try {
      const [runRes, artifactsRes, messagesRes] = await Promise.all([
        fetch(`${backendUrl}/api/runs/${runId}`).then(r => r.json()).catch(() => null),
        fetch(`${backendUrl}/api/runs/${runId}/artifacts`).then(r => r.json()).catch(() => []),
        fetch(`${backendUrl}/api/runs/${runId}/messages`).then(r => r.json()).catch(() => []),
      ])
      setRunDetail({ run: runRes, artifacts: Array.isArray(artifactsRes) ? artifactsRes : [], messages: Array.isArray(messagesRes) ? messagesRes : [] })
    } catch (_) { setRunDetail(null) }
    setLoading(false)
  }, [backendUrl])

  useEffect(() => {
    fetchRuns()
    const id = setInterval(fetchRuns, 5000)
    return () => clearInterval(id)
  }, [fetchRuns])

  useEffect(() => {
    if (selected) fetchDetail(selected)
  }, [selected])

  const stopRun = async (runId) => {
    await fetch(`${backendUrl}/api/runs/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId })
    }).catch(() => {})
    fetchRuns()
  }

  const deleteRun = async (runId) => {
    await fetch(`${backendUrl}/api/runs/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId })
    }).catch(() => {})
    fetchRuns()
    if (selected === runId) { setSelected(null); setRunDetail(null) }
  }

  return (
    <div className="orchestration-view">
      <div className="orch-header">
        <h2 className="orch-title">Agent Orchestration</h2>
        <button className="icon-btn" onClick={fetchRuns} title="Refresh">⟳</button>
      </div>

      {state.backendStatus !== 'running' && (
        <div className="orch-banner">
          <span>Backend is {state.backendStatus}</span>
          <button className="btn-accent" onClick={() => window.kendrAPI?.backend.start()}>
            Start Backend
          </button>
        </div>
      )}

      <div className="orch-layout">
        {/* Run list */}
        <div className="orch-list">
          <div className="orch-list-header">
            <span>RUNS ({runs.length})</span>
          </div>
          {runs.length === 0 && (
            <div className="orch-empty">
              <p>No runs yet.</p>
              <p>Start a conversation in the chat panel.</p>
            </div>
          )}
          {runs.map(run => (
            <RunItem
              key={run.run_id}
              run={run}
              selected={selected === run.run_id}
              onClick={() => setSelected(run.run_id)}
              onStop={() => stopRun(run.run_id)}
              onDelete={() => deleteRun(run.run_id)}
            />
          ))}
        </div>

        {/* Run detail */}
        <div className="orch-detail">
          {!selected && (
            <div className="orch-detail-empty">
              <p>Select a run to view details</p>
            </div>
          )}
          {selected && loading && <div className="orch-loading">Loading…</div>}
          {selected && !loading && runDetail && (
            <RunDetail detail={runDetail} />
          )}
        </div>
      </div>
    </div>
  )
}

function RunItem({ run, selected, onClick, onStop, onDelete }) {
  const status = run.status || 'pending'
  const color = STATUS_COLOR[status] || '#cccccc'
  const isActive = status === 'running'
  const text = (run.text || run.workflow_id || run.run_id || '').slice(0, 60)

  return (
    <div className={`run-list-item ${selected ? 'run-list-item--selected' : ''}`} onClick={onClick}>
      <div className="run-item-top">
        <span className="run-status-dot" style={{ background: color, boxShadow: isActive ? `0 0 6px ${color}` : 'none' }} />
        <span className="run-item-id">{run.run_id?.slice(0, 12) || '?'}</span>
        <span className={`run-item-status run-status--${status}`}>{status}</span>
      </div>
      <div className="run-item-text">{text || '(no description)'}</div>
      {run.created_at && (
        <div className="run-item-date">{new Date(run.created_at).toLocaleString()}</div>
      )}
      <div className="run-item-actions" onClick={e => e.stopPropagation()}>
        {isActive && (
          <button className="run-btn run-btn--stop" onClick={onStop} title="Stop">■ Stop</button>
        )}
        <button className="run-btn run-btn--delete" onClick={onDelete} title="Delete">✕</button>
      </div>
    </div>
  )
}

function RunDetail({ detail }) {
  const { run, artifacts, messages } = detail
  const [tab, setTab] = useState('output')

  return (
    <div className="run-detail">
      <div className="run-detail-header">
        <span className="run-detail-id">{run?.run_id}</span>
        <span className="run-detail-status" style={{ color: STATUS_COLOR[run?.status] || '#cccccc' }}>
          {run?.status}
        </span>
      </div>

      <div className="run-detail-tabs">
        {['output', 'artifacts', 'messages'].map(t => (
          <button
            key={t}
            className={`run-detail-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === 'artifacts' && artifacts.length > 0 && (
              <span className="tab-badge">{artifacts.length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="run-detail-body">
        {tab === 'output' && (
          <pre className="run-output">
            {JSON.stringify(run, null, 2)}
          </pre>
        )}
        {tab === 'artifacts' && (
          <div className="run-artifacts">
            {artifacts.length === 0 && <p className="detail-empty">No artifacts</p>}
            {artifacts.map((a, i) => (
              <div key={i} className="artifact-item">
                <span className="artifact-type">{a.artifact_type || 'file'}</span>
                <span className="artifact-name">{a.name || a.path || 'artifact'}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'messages' && (
          <div className="run-messages">
            {messages.length === 0 && <p className="detail-empty">No messages</p>}
            {messages.map((m, i) => (
              <div key={i} className={`run-msg run-msg--${m.role || 'system'}`}>
                <span className="run-msg-role">{m.role || 'system'}</span>
                <span className="run-msg-content">
                  {typeof m.content === 'string' ? m.content.slice(0, 200) : JSON.stringify(m.content).slice(0, 200)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
