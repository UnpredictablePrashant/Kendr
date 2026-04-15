import React, { useState, useEffect, useCallback, useMemo } from 'react'
import GitDiffPreview from '../components/GitDiffPreview'
import { useApp } from '../contexts/AppContext'
import { isPlanApprovalScope, isSkillApproval, summarizeRunArtifacts } from '../lib/runPresentation'

const STATUS_COLOR = {
  completed: '#89d185',
  running: '#3794ff',
  error: '#f47067',
  failed: '#f47067',
  cancelled: '#858585',
  pending: '#cca700',
  awaiting_user_input: '#e3b341',
}

function formatDuration(totalSeconds) {
  const s = Math.max(0, Number(totalSeconds) || 0)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m ${sec}s`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}

function normalizeRunStatus(status) {
  const raw = String(status || '').trim().toLowerCase()
  if (raw === 'streaming') return 'running'
  if (raw === 'awaiting') return 'awaiting'
  if (raw === 'done') return 'completed'
  if (raw === 'error') return 'failed'
  return raw || 'running'
}

function isShellProgressItem(item) {
  if (!item || typeof item !== 'object') return false
  const kind = String(item.kind || '').toLowerCase()
  const title = String(item.title || '').toLowerCase()
  const detail = String(item.detail || '').toLowerCase()
  const command = String(item.command || '').trim()
  if (command) return true
  if (kind.includes('command') || kind.includes('shell')) return true
  return /\bshell command\b|\brunning command\b|\bos[_\s-]?agent\b/.test(`${title} ${detail}`)
}

export default function AgentOrchestration() {
  const { state, dispatch, openFile } = useApp()
  const [tab, setTab] = useState('activity')
  const [runs, setRuns] = useState([])
  const [selected, setSelected] = useState(null)
  const [runDetail, setRunDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [diffPreviewPath, setDiffPreviewPath] = useState('')
  const backendUrl = state.backendUrl || 'http://127.0.0.1:2151'
  const activityFeed = Array.isArray(state.activityFeed) ? state.activityFeed : []

  const fetchRuns = useCallback(async () => {
    try {
      const response = await fetch(`${backendUrl}/api/runs`)
      if (!response.ok) return
      const data = await response.json()
      const list = Array.isArray(data) ? data : (data.runs || [])
      setRuns(list)
      dispatch({ type: 'SET_RUNS', runs: list })
    } catch (_) {}
  }, [backendUrl, dispatch])

  const fetchDetail = useCallback(async (runId) => {
    if (!runId) return
    setLoading(true)
    try {
      const [runRes, artifactsRes, messagesRes] = await Promise.all([
        fetch(`${backendUrl}/api/runs/${runId}`).then((response) => response.json()).catch(() => null),
        fetch(`${backendUrl}/api/runs/${runId}/artifacts`).then((response) => response.json()).catch(() => []),
        fetch(`${backendUrl}/api/runs/${runId}/messages`).then((response) => response.json()).catch(() => []),
      ])
      setRunDetail({
        run: runRes,
        artifacts: Array.isArray(artifactsRes) ? artifactsRes : [],
        messages: Array.isArray(messagesRes) ? messagesRes : [],
      })
    } catch (_) {
      setRunDetail(null)
    }
    setLoading(false)
  }, [backendUrl])

  useEffect(() => {
    if (tab !== 'debug') return
    fetchRuns()
    const id = setInterval(fetchRuns, 5000)
    return () => clearInterval(id)
  }, [fetchRuns, tab])

  useEffect(() => {
    if (tab === 'debug' && selected) fetchDetail(selected)
  }, [selected, fetchDetail, tab])

  const stopRun = async (runId) => {
    await fetch(`${backendUrl}/api/runs/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId }),
    }).catch(() => {})
    fetchRuns()
  }

  const deleteRun = async (runId) => {
    await fetch(`${backendUrl}/api/runs/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId }),
    }).catch(() => {})
    fetchRuns()
    if (selected === runId) {
      setSelected(null)
      setRunDetail(null)
    }
  }

  const inspectRun = useCallback((runId) => {
    if (!runId) return
    setTab('debug')
    setSelected(runId)
  }, [])

  const openActivityItem = useCallback(async (item) => {
    const filePath = String(item?.path || '').trim()
    if (!filePath) return
    dispatch({ type: 'SET_VIEW', view: 'developer' })
    await openFile(filePath)
  }, [dispatch, openFile])
  const reviewActivityItem = useCallback((item) => {
    const filePath = String(item?.path || '').trim()
    if (!filePath) return
    setDiffPreviewPath(filePath)
  }, [])

  const recentActivity = useMemo(() => activityFeed.slice(0, 16), [activityFeed])

  return (
    <div className="orchestration-view">
      <GitDiffPreview
        cwd={state.projectRoot}
        filePath={diffPreviewPath}
        onClose={() => setDiffPreviewPath('')}
        onOpenFile={(filePath) => openActivityItem({ path: filePath })}
      />
      <div className="orch-header">
        <h2 className="orch-title">Agent Orchestration</h2>
        <div className="orch-header-actions">
          <div className="orch-tabs">
            <button className={`orch-tab ${tab === 'activity' ? 'active' : ''}`} onClick={() => setTab('activity')}>Activity</button>
            <button className={`orch-tab ${tab === 'debug' ? 'active' : ''}`} onClick={() => setTab('debug')}>Debug</button>
          </div>
          {tab === 'activity' && recentActivity.length > 0 && (
            <button className="rp-btn-sm" onClick={() => dispatch({ type: 'CLEAR_ACTIVITY_FEED' })}>
              Clear
            </button>
          )}
          {tab === 'debug' && <button className="icon-btn" onClick={fetchRuns} title="Refresh">⟳</button>}
        </div>
      </div>

      {state.backendStatus !== 'running' && (
        <div className="orch-banner">
          <span>Backend is {state.backendStatus}</span>
          <button className="btn-accent" onClick={() => window.kendrAPI?.backend.start()}>
            Start Backend
          </button>
        </div>
      )}

      {tab === 'activity' ? (
        <div className="orch-activity">
          {recentActivity.length === 0 ? (
            <div className="orch-empty">
              <p>No recent activity yet.</p>
              <p>Start a run in Studio or Project mode.</p>
            </div>
          ) : (
            <div className="orch-activity-feed">
              {recentActivity.map((entry) => {
                const progress = Array.isArray(entry.progress) ? entry.progress.filter((item) => !isShellProgressItem(item)) : []
                const cards = summarizeRunArtifacts(progress, entry.artifacts)
                const checklist = Array.isArray(entry.checklist) ? entry.checklist : []
                const planLike = checklist.length > 0 && (
                  entry.mode === 'plan'
                  || isPlanApprovalScope(entry.approvalScope, entry.approvalKind, entry.approvalRequest)
                )
                const latestPath = cards
                  .flatMap((card) => Array.isArray(card.items) ? card.items : [])
                  .find((item) => item?.path)
                const elapsedSeconds = entry.runStartedAt
                  ? Math.max(0, Math.floor((Date.now() - new Date(entry.runStartedAt).getTime()) / 1000))
                  : 0
                return (
                  <div key={entry.id} className="rp-activity-card">
                    <div className="rp-activity-head">
                      <div className="rp-activity-meta">
                        <span className="rp-activity-source">{entry.source}</span>
                        {entry.modeLabel && <span className="rp-activity-chip">{entry.modeLabel}</span>}
                        {entry.runId && <span className="rp-activity-chip">{entry.runId.slice(-8)}</span>}
                      </div>
                      <div className="rp-activity-meta">
                        <span className={`rp-activity-status rp-activity-status--${normalizeRunStatus(entry.status)}`}>
                          {normalizeRunStatus(entry.status)}
                        </span>
                        {entry.runId && (
                          <button className="rp-btn-sm" onClick={() => inspectRun(entry.runId)}>Inspect</button>
                        )}
                      </div>
                    </div>

                    {!!cards.length && (
                      <div className="kc-activity-grid">
                        {cards.map((card) => (
                          <div key={`${entry.id}-${card.kind}-${card.title}`} className={`kc-activity-card kc-activity-card--${card.kind}`}>
                            <div className="kc-activity-card-head">
                              <div>
                                <div className="kc-activity-card-kind">{card.kind}</div>
                                <div className="kc-activity-card-title">{card.title}</div>
                              </div>
                              {card.kind === 'edit' && Array.isArray(card.items) && card.items.some((item) => item?.path) && (
                                <button className="kc-activity-card-action" onClick={() => reviewActivityItem(card.items.find((item) => item?.path))}>
                                  Review
                                </button>
                              )}
                            </div>
                            {Array.isArray(card.items) && card.items.length > 0 && (
                              <div className="kc-activity-card-items">
                                {card.items.slice(0, 3).map((item) => (
                                  item?.path ? (
                                    <button key={`${entry.id}-${item.path}-${item.label}`} className="kc-activity-card-item kc-activity-card-item--action" onClick={() => openActivityItem(item)}>
                                      {item.label}
                                    </button>
                                  ) : (
                                    <span key={`${entry.id}-${item.label}`} className="kc-activity-card-item">{item.label}</span>
                                  )
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {planLike && (
                      <div className="rp-plan-preview">
                        <div className="rp-plan-title">Plan</div>
                        <div className="kc-checklist-list">
                          {checklist.slice(0, 4).map((item) => (
                            <div key={`${entry.id}-${item.step}-${item.title}`} className="kc-checklist-item">
                              <div className="kc-checklist-mark">{item.done ? '✓' : item.status === 'running' ? '…' : '·'}</div>
                              <div className="kc-checklist-body">
                                <div className="kc-checklist-row">
                                  <span className="kc-checklist-step">{item.step}.</span>
                                  <span className="kc-checklist-text">{item.title}</span>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {entry.content && !planLike && !isSkillApproval(entry.approvalKind, entry.approvalRequest) && (
                      <div className="rp-activity-content">{entry.content.slice(0, 320)}{entry.content.length > 320 ? '…' : ''}</div>
                    )}

                    <div className="rp-activity-footer">
                      {entry.runId && <span>{formatDuration(elapsedSeconds)}</span>}
                      {latestPath?.path && <button className="rp-btn-sm" onClick={() => openActivityItem(latestPath)}>Open file</button>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="orch-layout">
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
            {runs.map((run) => (
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
      )}
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
      <div className="run-item-actions" onClick={(event) => event.stopPropagation()}>
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
        {['output', 'artifacts', 'messages'].map((name) => (
          <button
            key={name}
            className={`run-detail-tab ${tab === name ? 'active' : ''}`}
            onClick={() => setTab(name)}
          >
            {name.charAt(0).toUpperCase() + name.slice(1)}
            {name === 'artifacts' && artifacts.length > 0 && (
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
            {artifacts.map((artifact, index) => (
              <div key={index} className="artifact-item">
                <span className="artifact-type">{artifact.artifact_type || 'file'}</span>
                <span className="artifact-name">{artifact.name || artifact.path || 'artifact'}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'messages' && (
          <div className="run-messages">
            {messages.length === 0 && <p className="detail-empty">No messages</p>}
            {messages.map((message, index) => (
              <div key={index} className={`run-msg run-msg--${message.role || 'system'}`}>
                <span className="run-msg-role">{message.role || 'system'}</span>
                <span className="run-msg-content">
                  {typeof message.content === 'string'
                    ? message.content.slice(0, 200)
                    : JSON.stringify(message.content).slice(0, 200)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
