import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useApp } from '../contexts/AppContext'

// ─── Menu definitions ─────────────────────────────────────────────────────────
function useMenuDefs() {
  const { state, dispatch, openFile } = useApp()
  const api = window.kendrAPI

  const newFile = async () => {
    const path = await api?.dialog.saveFile('')
    if (path) { await api?.fs.createFile(path); openFile(path) }
  }
  const openFolder = async () => {
    const dir = await api?.dialog.openDirectory()
    if (dir) dispatch({ type: 'SET_PROJECT_ROOT', root: dir })
  }
  const openFileDialog = async () => {
    const path = await api?.dialog.openFile()
    if (path) openFile(path)
  }
  const saveActive = () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 's', ctrlKey: true, bubbles: true }))
  const closeTab = () => {
    if (state.activeTabPath) dispatch({ type: 'CLOSE_TAB', path: state.activeTabPath })
  }

  return [
    {
      label: 'File',
      items: [
        { label: 'New File',         shortcut: 'Ctrl+N',       action: newFile },
        { label: 'Open File…',       shortcut: 'Ctrl+O',       action: openFileDialog },
        { label: 'Open Folder…',     shortcut: 'Ctrl+Shift+O', action: openFolder },
        { sep: true },
        { label: 'Save',             shortcut: 'Ctrl+S',       action: saveActive },
        { label: 'Close Tab',        shortcut: 'Ctrl+W',       action: closeTab },
        { sep: true },
        { label: 'Settings',         shortcut: 'Ctrl+,',       action: () => { dispatch({ type: 'SET_VIEW', view: 'settings' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { sep: true },
        { label: 'Quit',             shortcut: 'Alt+F4',       action: () => api?.window.close() },
      ]
    },
    {
      label: 'Edit',
      items: [
        { label: 'Undo',             shortcut: 'Ctrl+Z',       action: () => document.execCommand('undo') },
        { label: 'Redo',             shortcut: 'Ctrl+Y',       action: () => document.execCommand('redo') },
        { sep: true },
        { label: 'Cut',              shortcut: 'Ctrl+X',       action: () => document.execCommand('cut') },
        { label: 'Copy',             shortcut: 'Ctrl+C',       action: () => document.execCommand('copy') },
        { label: 'Paste',            shortcut: 'Ctrl+V',       action: () => document.execCommand('paste') },
        { sep: true },
        { label: 'Find',             shortcut: 'Ctrl+F',       action: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'f', ctrlKey: true, bubbles: true })) },
        { label: 'Replace',          shortcut: 'Ctrl+H',       action: () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'h', ctrlKey: true, bubbles: true })) },
      ]
    },
    {
      label: 'View',
      items: [
        { label: 'Build Workspace', shortcut: 'Ctrl+Shift+J', action: () => dispatch({ type: 'SET_VIEW', view: 'developer' }) },
        { sep: true },
        { label: 'Studio',                                       action: () => { dispatch({ type: 'SET_VIEW', view: 'studio' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Build Workspace',                              action: () => { dispatch({ type: 'SET_VIEW', view: 'developer' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Automation & Builders',                        action: () => { dispatch({ type: 'SET_VIEW', view: 'build' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Machine',                                      action: () => { dispatch({ type: 'SET_VIEW', view: 'machine' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Memory',                                       action: () => { dispatch({ type: 'SET_VIEW', view: 'memory' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Integrations',                                 action: () => { dispatch({ type: 'SET_VIEW', view: 'integrations' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Runs',                                         action: () => { dispatch({ type: 'SET_VIEW', view: 'runs' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Marketplace',                                  action: () => { dispatch({ type: 'SET_VIEW', view: 'marketplace' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { label: 'Settings',                                     action: () => { dispatch({ type: 'SET_VIEW', view: 'settings' }); dispatch({ type: 'SET_SIDEBAR', open: true }) } },
        { sep: true },
        { label: state.chatOpen ? 'Hide Chat' : 'Show Chat',  shortcut: 'Ctrl+Shift+C', action: () => dispatch({ type: 'TOGGLE_CHAT' }) },
        { label: 'Toggle Sidebar',   shortcut: 'Ctrl+B',       action: () => dispatch({ type: 'TOGGLE_SIDEBAR' }) },
        { sep: true },
        { label: 'Command Palette',  shortcut: 'Ctrl+Shift+P', action: () => dispatch({ type: 'TOGGLE_COMMAND_PALETTE' }) },
      ]
    },
    {
      label: 'Terminal',
      items: [
        { label: 'New Terminal',     shortcut: 'Ctrl+`',       action: () => dispatch({ type: 'SET_TERMINAL', open: true }) },
        { label: 'Toggle Terminal',  shortcut: 'Ctrl+`',       action: () => dispatch({ type: 'TOGGLE_TERMINAL' }) },
        { sep: true },
        { label: 'Run: npm dev',                               action: () => sendToTerminal('npm run dev') },
        { label: 'Run: npm test',                              action: () => sendToTerminal('npm test') },
        { label: 'Run: npm build',                             action: () => sendToTerminal('npm run build') },
        { label: 'Run: python main.py',                        action: () => sendToTerminal('python main.py') },
        { label: 'Run: pytest',                                action: () => sendToTerminal('pytest') },
      ]
    },
    {
      label: 'Run',
      items: [
        { label: 'Open Run Panel',                             action: () => window.dispatchEvent(new CustomEvent('kendr:open-run-panel')) },
        { sep: true },
        { label: 'Start Backend',                              action: () => api?.backend.start() },
        { label: 'Stop Backend',                               action: () => api?.backend.stop() },
        { label: 'Restart Backend',                            action: () => api?.backend.restart() },
        { sep: true },
        { label: 'Backend Logs',                               action: async () => {
          const logs = await api?.backend.getLogs()
          window.dispatchEvent(new CustomEvent('kendr:show-logs', { detail: logs }))
        }},
      ]
    },
    {
      label: 'Extensions',
      items: [
        { label: 'Build',                                      action: () => dispatch({ type: 'SET_VIEW', view: 'build' }) },
        { label: 'Integrations',                               action: () => dispatch({ type: 'SET_VIEW', view: 'integrations' }) },
        { label: 'Marketplace',                                action: () => dispatch({ type: 'SET_VIEW', view: 'marketplace' }) },
        { sep: true },
        { label: 'Add MCP Server',                             action: () => {
          dispatch({ type: 'SET_VIEW', view: 'integrations' })
          // small delay so the panel mounts before the event fires
          setTimeout(() => window.dispatchEvent(new CustomEvent('kendr:mcp-add')), 150)
        }},
        { label: 'Discover MCP Tools',                         action: () => {
          dispatch({ type: 'SET_VIEW', view: 'integrations' })
          setTimeout(() => window.dispatchEvent(new CustomEvent('kendr:mcp-discover-all')), 150)
        }},
        { sep: true },
        { label: 'Browse Skill Intents',                       action: () => dispatch({ type: 'SET_VIEW', view: 'marketplace' }) },
        { label: 'Reload Capabilities',                        action: async () => {
          try {
            const base = state.backendUrl || 'http://127.0.0.1:2151'
            await fetch(`${base}/api/capabilities/reload`, { method: 'POST' })
          } catch {}
        }},
      ]
    },
    {
      label: 'Help',
      items: [
        { label: 'Keyboard Shortcuts', shortcut: 'Ctrl+Shift+P', action: () => dispatch({ type: 'TOGGLE_COMMAND_PALETTE' }) },
        { label: 'Model Docs',                                  action: () => dispatch({ type: 'SET_VIEW', view: 'settings' }) },
        { sep: true },
        { label: 'About Kendr',                                action: () => dispatch({ type: 'SET_VIEW', view: 'about' }) },
      ]
    },
  ]
}

function sendToTerminal(command) {
  window.dispatchEvent(new CustomEvent('kendr:run-command', { detail: { command } }))
  window.dispatchEvent(new CustomEvent('kendr:open-terminal'))
}

// ─── MenuBar component ────────────────────────────────────────────────────────
export default function MenuBar() {
  const [open, setOpen] = useState(null)   // index of open menu, or null
  const [hovered, setHovered] = useState(null)
  const barRef = useRef(null)
  const menuDefs = useMenuDefs()

  // Close on outside click or Escape
  useEffect(() => {
    if (open === null) return
    const onKey = (e) => { if (e.key === 'Escape') setOpen(null) }
    const onMouse = (e) => {
      if (barRef.current && !barRef.current.contains(e.target)) setOpen(null)
    }
    document.addEventListener('mousedown', onMouse)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onMouse)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const toggle = (i) => setOpen(o => o === i ? null : i)
  const hoverOpen = (i) => { if (open !== null) setOpen(i) }

  const exec = (action) => {
    setOpen(null)
    setHovered(null)
    action?.()
  }

  return (
    <div className="menubar" ref={barRef} style={{ WebkitAppRegion: 'no-drag' }}>
      {menuDefs.map((menu, i) => (
        <div key={menu.label} className="menubar-item">
          <button
            className={`menubar-btn ${open === i ? 'active' : ''}`}
            onMouseDown={() => toggle(i)}
            onMouseEnter={() => hoverOpen(i)}
          >
            {menu.label}
          </button>

          {open === i && (
            <div className="menubar-dropdown">
              {menu.items.map((item, j) =>
                item.sep ? (
                  <div key={`sep-${j}`} className="menubar-sep" />
                ) : (
                  <button
                    key={item.label}
                    className={`menubar-row ${hovered === `${i}-${j}` ? 'hovered' : ''}`}
                    onMouseEnter={() => setHovered(`${i}-${j}`)}
                    onMouseLeave={() => setHovered(null)}
                    onMouseDown={() => exec(item.action)}
                    disabled={!item.action}
                  >
                    <span className="menubar-row-label">{item.label}</span>
                    {item.shortcut && <span className="menubar-row-shortcut">{item.shortcut}</span>}
                  </button>
                )
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
