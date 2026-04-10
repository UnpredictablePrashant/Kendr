import React, { useState, useEffect, useRef } from 'react'
import { useApp } from '../contexts/AppContext'

const COMMANDS = [
  { id: 'toggle-terminal',  label: 'Toggle Terminal',          keys: 'Ctrl+`' },
  { id: 'toggle-sidebar',   label: 'Toggle Sidebar',           keys: 'Ctrl+B' },
  { id: 'toggle-chat',      label: 'Toggle Chat Panel',        keys: '' },
  { id: 'view-files',       label: 'View: Explorer',           keys: '' },
  { id: 'view-git',         label: 'View: Source Control',     keys: '' },
  { id: 'view-agents',      label: 'View: Agent Orchestration',keys: '' },
  { id: 'view-models',      label: 'View: Model Manager',      keys: '' },
  { id: 'view-settings',    label: 'View: Settings',           keys: '' },
  { id: 'open-folder',      label: 'Open Folder…',             keys: '' },
  { id: 'start-backend',    label: 'Backend: Start',           keys: '' },
  { id: 'restart-backend',  label: 'Backend: Restart',         keys: '' },
  { id: 'stop-backend',     label: 'Backend: Stop',            keys: '' },
  { id: 'new-chat',         label: 'Chat: New Conversation',   keys: '' },
  { id: 'clear-chat',       label: 'Chat: Clear Messages',     keys: '' },
]

export default function CommandPalette() {
  const { state, dispatch, openFile } = useApp()
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef(null)
  const api = window.kendrAPI

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const filtered = COMMANDS.filter(c =>
    c.label.toLowerCase().includes(query.toLowerCase())
  )

  const run = async (cmd) => {
    dispatch({ type: 'SET_COMMAND_PALETTE', open: false })
    switch (cmd.id) {
      case 'toggle-terminal':  dispatch({ type: 'TOGGLE_TERMINAL' }); break
      case 'toggle-sidebar':   dispatch({ type: 'TOGGLE_SIDEBAR' }); break
      case 'toggle-chat':      dispatch({ type: 'TOGGLE_CHAT' }); break
      case 'view-files':       dispatch({ type: 'SET_VIEW', view: 'files' }); break
      case 'view-git':         dispatch({ type: 'SET_VIEW', view: 'git' }); break
      case 'view-agents':      dispatch({ type: 'SET_VIEW', view: 'orchestration' }); break
      case 'view-models':      dispatch({ type: 'SET_VIEW', view: 'models' }); break
      case 'view-settings':    dispatch({ type: 'SET_VIEW', view: 'settings' }); break
      case 'open-folder': {
        const dir = await api?.dialog.openDirectory()
        if (dir) {
          dispatch({ type: 'SET_PROJECT_ROOT', root: dir })
          await api?.settings.set('projectRoot', dir)
          dispatch({ type: 'SET_VIEW', view: 'files' })
        }
        break
      }
      case 'start-backend':   await api?.backend.start(); break
      case 'restart-backend': await api?.backend.restart(); break
      case 'stop-backend':    await api?.backend.stop(); break
      case 'new-chat':        dispatch({ type: 'SET_MESSAGES', messages: [] }); break
      case 'clear-chat':      dispatch({ type: 'CLEAR_MESSAGES' }); break
    }
  }

  const handleKey = (e) => {
    if (e.key === 'ArrowDown') setSelected(s => Math.min(s + 1, filtered.length - 1))
    else if (e.key === 'ArrowUp') setSelected(s => Math.max(s - 1, 0))
    else if (e.key === 'Enter' && filtered[selected]) run(filtered[selected])
    else if (e.key === 'Escape') dispatch({ type: 'SET_COMMAND_PALETTE', open: false })
  }

  return (
    <div className="palette-backdrop" onClick={() => dispatch({ type: 'SET_COMMAND_PALETTE', open: false })}>
      <div className="palette" onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="Type a command…"
          value={query}
          onChange={e => { setQuery(e.target.value); setSelected(0) }}
          onKeyDown={handleKey}
        />
        <div className="palette-list">
          {filtered.length === 0 && (
            <div className="palette-empty">No commands match</div>
          )}
          {filtered.map((cmd, i) => (
            <div
              key={cmd.id}
              className={`palette-item ${i === selected ? 'palette-item--selected' : ''}`}
              onClick={() => run(cmd)}
              onMouseEnter={() => setSelected(i)}
            >
              <span className="palette-item-label">{cmd.label}</span>
              {cmd.keys && <span className="palette-item-keys">{cmd.keys}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
