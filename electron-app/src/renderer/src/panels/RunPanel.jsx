import React, { useMemo, useState, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'
import { isPlanApprovalScope, isSkillApproval, summarizeRunArtifacts } from '../lib/runPresentation'

const STORAGE_KEY = 'kendr_run_configs_v2'

function loadConfigs() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}

const PRESETS = [
  { name: 'npm dev', command: 'npm run dev', icon: '🟢' },
  { name: 'npm start', command: 'npm start', icon: '🟢' },
  { name: 'npm test', command: 'npm test', icon: '🧪' },
  { name: 'npm build', command: 'npm run build', icon: '📦' },
  { name: 'Python app', command: 'python app.py', icon: '🐍' },
  { name: 'Python main', command: 'python main.py', icon: '🐍' },
  { name: 'pytest', command: 'pytest', icon: '🧪' },
  { name: 'pip install', command: 'pip install -r requirements.txt', icon: '📦' },
  { name: 'go run', command: 'go run .', icon: '🔵' },
  { name: 'cargo run', command: 'cargo run', icon: '🦀' },
]

function formatDuration(totalSeconds) {
  const s = Math.max(0, Number(totalSeconds) || 0)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m ${sec}s`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
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

function normalizeRunStatus(status) {
  const raw = String(status || '').trim().toLowerCase()
  if (raw === 'streaming') return 'running'
  if (raw === 'awaiting') return 'awaiting'
  if (raw === 'done') return 'completed'
  if (raw === 'error') return 'failed'
  return raw || 'running'
}

export default function RunPanel() {
  const { state, dispatch, openFile } = useApp()
  const [configs, setConfigs] = useState(loadConfigs)
  const [showAdd, setShowAdd] = useState(false)
  const [showPresets, setShowPresets] = useState(false)
  const [newName, setNewName] = useState('')
  const [newCmd, setNewCmd] = useState('')
  const [newCwd, setNewCwd] = useState('')
  const [running, setRunning] = useState(null)

  const activityFeed = Array.isArray(state.activityFeed) ? state.activityFeed : []

  const persist = (next) => {
    setConfigs(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  const addConfig = () => {
    if (!newCmd.trim()) return
    const cfg = {
      id: Date.now().toString(36),
      name: newName.trim() || newCmd.trim(),
      command: newCmd.trim(),
      cwd: newCwd.trim() || state.projectRoot || '',
      icon: '▶',
    }
    persist([...configs, cfg])
    setNewName('')
    setNewCmd('')
    setNewCwd('')
    setShowAdd(false)
  }

  const addPreset = (preset) => {
    const cfg = {
      id: Date.now().toString(36),
      name: preset.name,
      command: preset.command,
      cwd: state.projectRoot || '',
      icon: preset.icon,
    }
    persist([...configs, cfg])
    setShowPresets(false)
  }

  const deleteConfig = (id) => persist(configs.filter((cfg) => cfg.id !== id))

  const runConfig = useCallback(async (cfg) => {
    setRunning(cfg.id)
    dispatch({ type: 'SET_TERMINAL', open: true })
    await new Promise((resolve) => setTimeout(resolve, 150))
    window.dispatchEvent(new CustomEvent('kendr:run-command', {
      detail: { command: cfg.cwd ? `cd "${cfg.cwd}" && ${cfg.command}` : cfg.command },
    }))
    setTimeout(() => setRunning(null), 1500)
  }, [dispatch])

  const openFolder = async (setter) => {
    const dir = await window.kendrAPI?.dialog.openDirectory()
    if (dir) setter(dir)
  }

  const openActivityItem = useCallback(async (item) => {
    const filePath = String(item?.path || '').trim()
    if (!filePath) return
    await openFile(filePath)
  }, [openFile])

  const activityItems = useMemo(() => activityFeed.slice(0, 10), [activityFeed])

  return (
    <div className="rp-root">
      <div className="rp-header">
        <span className="rp-title">Activity</span>
        <div className="rp-header-actions">
          {!!activityItems.length && (
            <button className="rp-btn-sm" onClick={() => dispatch({ type: 'CLEAR_ACTIVITY_FEED' })}>Clear</button>
          )}
          <button className="rp-btn-sm" onClick={() => setShowPresets((value) => !value)}>Templates</button>
          <button className="rp-btn-sm rp-btn-sm--primary" onClick={() => setShowAdd((value) => !value)}>+ Add</button>
        </div>
      </div>

      <div className="rp-list">
        {activityItems.length === 0 ? (
          <div className="rp-empty rp-empty--activity">
            <p>No recent agent activity yet.</p>
            <p>Start a run in Studio or Project mode and it will appear here.</p>
          </div>
        ) : (
          <div className="rp-activity-feed">
            {activityItems.map((entry) => {
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
                    <span className={`rp-activity-status rp-activity-status--${normalizeRunStatus(entry.status)}`}>
                      {normalizeRunStatus(entry.status)}
                    </span>
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
                              <button className="kc-activity-card-action" onClick={() => openActivityItem(card.items.find((item) => item?.path))}>
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
                    <div className="rp-activity-content">{entry.content.slice(0, 240)}{entry.content.length > 240 ? '…' : ''}</div>
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

        {(showPresets || showAdd || configs.length > 0) && (
          <div className="rp-command-block">
            <div className="rp-section-title">Commands</div>

            {showPresets && (
              <div className="rp-presets">
                <div className="rp-presets-label">Click to add preset</div>
                {PRESETS.map((preset) => (
                  <button key={preset.name} className="rp-preset-item" onClick={() => addPreset(preset)}>
                    <span>{preset.icon}</span>
                    <span className="rp-preset-name">{preset.name}</span>
                    <span className="rp-preset-cmd">{preset.command}</span>
                  </button>
                ))}
              </div>
            )}

            {showAdd && (
              <div className="rp-add-form">
                <input className="rp-input" placeholder="Name (optional)" value={newName} onChange={(event) => setNewName(event.target.value)} />
                <input
                  className="rp-input"
                  placeholder="Command  e.g. npm run dev"
                  value={newCmd}
                  onChange={(event) => setNewCmd(event.target.value)}
                  onKeyDown={(event) => event.key === 'Enter' && addConfig()}
                />
                <div className="rp-dir-row">
                  <input
                    className="rp-input rp-input--flex"
                    placeholder="Working dir (optional, default: project root)"
                    value={newCwd}
                    onChange={(event) => setNewCwd(event.target.value)}
                  />
                  <button className="rp-icon-btn" onClick={() => openFolder(setNewCwd)}>…</button>
                </div>
                <div className="rp-form-actions">
                  <button className="rp-add-confirm" onClick={addConfig} disabled={!newCmd.trim()}>Add</button>
                  <button className="rp-cancel" onClick={() => setShowAdd(false)}>Cancel</button>
                </div>
              </div>
            )}

            {!configs.length && !showAdd && !showPresets ? (
              <div className="rp-empty rp-empty--commands">
                <p>No run configurations yet.</p>
                <p>Click <strong>Templates</strong> or <strong>+ Add</strong>.</p>
              </div>
            ) : (
              <div className="rp-config-list">
                {configs.map((cfg) => (
                  <div key={cfg.id} className={`rp-config ${running === cfg.id ? 'running' : ''}`}>
                    <button
                      className="rp-run-btn"
                      onClick={() => runConfig(cfg)}
                      title={`Run: ${cfg.command}`}
                      disabled={running === cfg.id}
                    >
                      {running === cfg.id ? <span className="rp-running-dot" /> : (cfg.icon || '▶')}
                    </button>
                    <div className="rp-config-info">
                      <span className="rp-config-name">{cfg.name}</span>
                      <span className="rp-config-cmd">{cfg.command}</span>
                      {cfg.cwd && <span className="rp-config-cwd">📁 {cfg.cwd.split(/[\\/]/).slice(-2).join('/')}</span>}
                    </div>
                    <button className="rp-del-btn" onClick={() => deleteConfig(cfg.id)} title="Remove">✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
