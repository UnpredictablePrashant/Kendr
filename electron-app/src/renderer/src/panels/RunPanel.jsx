import React, { useState, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'

const STORAGE_KEY = 'kendr_run_configs_v2'

function loadConfigs() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}

// ─── Preset templates ─────────────────────────────────────────────────────────
const PRESETS = [
  { name: 'npm dev',        command: 'npm run dev',         icon: '🟢' },
  { name: 'npm start',      command: 'npm start',           icon: '🟢' },
  { name: 'npm test',       command: 'npm test',            icon: '🧪' },
  { name: 'npm build',      command: 'npm run build',       icon: '📦' },
  { name: 'Python app',     command: 'python app.py',       icon: '🐍' },
  { name: 'Python main',    command: 'python main.py',      icon: '🐍' },
  { name: 'pytest',         command: 'pytest',              icon: '🧪' },
  { name: 'pip install',    command: 'pip install -r requirements.txt', icon: '📦' },
  { name: 'go run',         command: 'go run .',            icon: '🔵' },
  { name: 'cargo run',      command: 'cargo run',           icon: '🦀' },
]

export default function RunPanel() {
  const { state, dispatch } = useApp()
  const [configs, setConfigs] = useState(loadConfigs)
  const [showAdd, setShowAdd]   = useState(false)
  const [showPresets, setShowPresets] = useState(false)
  const [newName, setNewName]   = useState('')
  const [newCmd, setNewCmd]     = useState('')
  const [newCwd, setNewCwd]     = useState('')
  const [running, setRunning]   = useState(null) // id of currently running config

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
    setNewName(''); setNewCmd(''); setNewCwd(''); setShowAdd(false)
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

  const deleteConfig = (id) => persist(configs.filter(c => c.id !== id))

  const runConfig = useCallback(async (cfg) => {
    setRunning(cfg.id)
    // Ensure terminal is visible
    dispatch({ type: 'SET_TERMINAL', open: true })

    // Small delay to let TerminalPanel mount if it wasn't open
    await new Promise(r => setTimeout(r, 150))

    // Dispatch via custom event (picked up by TerminalPanel)
    window.dispatchEvent(new CustomEvent('kendr:run-command', {
      detail: { command: cfg.cwd ? `cd "${cfg.cwd}" && ${cfg.command}` : cfg.command }
    }))

    // Mark as done after brief visual feedback
    setTimeout(() => setRunning(null), 1500)
  }, [dispatch])

  const openFolder = async (setter) => {
    const dir = await window.kendrAPI?.dialog.openDirectory()
    if (dir) setter(dir)
  }

  return (
    <div className="rp-root">
      {/* Header */}
      <div className="rp-header">
        <span className="rp-title">Run Configurations</span>
        <div className="rp-header-actions">
          <button className="rp-btn-sm" onClick={() => setShowPresets(s => !s)}>Templates</button>
          <button className="rp-btn-sm rp-btn-sm--primary" onClick={() => setShowAdd(s => !s)}>+ Add</button>
        </div>
      </div>

      {/* Presets dropdown */}
      {showPresets && (
        <div className="rp-presets">
          <div className="rp-presets-label">Click to add preset</div>
          {PRESETS.map(p => (
            <button key={p.name} className="rp-preset-item" onClick={() => addPreset(p)}>
              <span>{p.icon}</span>
              <span className="rp-preset-name">{p.name}</span>
              <span className="rp-preset-cmd">{p.command}</span>
            </button>
          ))}
        </div>
      )}

      {/* Add form */}
      {showAdd && (
        <div className="rp-add-form">
          <input
            className="rp-input"
            placeholder="Name (optional)"
            value={newName}
            onChange={e => setNewName(e.target.value)}
          />
          <input
            className="rp-input"
            placeholder="Command  e.g. npm run dev"
            value={newCmd}
            onChange={e => setNewCmd(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addConfig()}
          />
          <div className="rp-dir-row">
            <input
              className="rp-input rp-input--flex"
              placeholder="Working dir (optional, default: project root)"
              value={newCwd}
              onChange={e => setNewCwd(e.target.value)}
            />
            <button className="rp-icon-btn" onClick={() => openFolder(setNewCwd)}>…</button>
          </div>
          <div className="rp-form-actions">
            <button className="rp-add-confirm" onClick={addConfig} disabled={!newCmd.trim()}>Add</button>
            <button className="rp-cancel" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Config list */}
      {configs.length === 0 && !showAdd && !showPresets && (
        <div className="rp-empty">
          <p>No run configurations yet.</p>
          <p>Click <strong>Templates</strong> for quick presets or <strong>+ Add</strong> to create a custom command.</p>
        </div>
      )}

      <div className="rp-list">
        {configs.map(cfg => (
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
            <button
              className="rp-del-btn"
              onClick={() => deleteConfig(cfg.id)}
              title="Remove"
            >✕</button>
          </div>
        ))}
      </div>
    </div>
  )
}
