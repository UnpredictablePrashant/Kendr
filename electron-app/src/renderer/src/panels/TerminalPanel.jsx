import React, { useEffect, useRef, useState } from 'react'
import { useApp } from '../contexts/AppContext'

export default function TerminalPanel() {
  const { state, dispatch } = useApp()
  const containerRef = useRef(null)
  const termRef = useRef(null)
  const fitRef = useRef(null)
  const ptyIdRef = useRef(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function init() {
      const api = window.kendrAPI
      if (!api) { setError('Electron API not available'); setLoading(false); return }

      try {
        const { Terminal } = await import('@xterm/xterm')
        const { FitAddon } = await import('@xterm/addon-fit')
        const { WebLinksAddon } = await import('@xterm/addon-web-links')

        if (cancelled) return

        const term = new Terminal({
          theme: {
            background: '#1e1e1e',
            foreground: '#cccccc',
            cursor: '#aeafad',
            selectionBackground: '#264f78',
            black: '#1e1e1e', brightBlack: '#808080',
            red: '#f44747', brightRed: '#f44747',
            green: '#89d185', brightGreen: '#b5cea8',
            yellow: '#dcdcaa', brightYellow: '#dcdcaa',
            blue: '#569cd6', brightBlue: '#9cdcfe',
            magenta: '#c586c0', brightMagenta: '#d7ba7d',
            cyan: '#4ec9b0', brightCyan: '#4ec9b0',
            white: '#d4d4d4', brightWhite: '#e8e8e8'
          },
          fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace",
          fontSize: 13,
          lineHeight: 1.4,
          cursorBlink: true,
          cursorStyle: 'block',
          allowTransparency: true,
          scrollback: 5000
        })

        const fit = new FitAddon()
        term.loadAddon(fit)
        term.loadAddon(new WebLinksAddon())

        term.open(containerRef.current)
        fit.fit()

        termRef.current = term
        fitRef.current = fit

        // Create PTY
        const result = await api.pty.create({
          cwd: state.projectRoot || undefined,
          cols: term.cols,
          rows: term.rows
        })

        if (result.error) {
          term.writeln(`\x1b[31mFailed to create terminal: ${result.error}\x1b[0m`)
          setLoading(false)
          return
        }

        ptyIdRef.current = result.id
        // Expose PTY ID globally so RunPanel can send commands before first render
        window.__kendrPtyId = result.id

        // Bridge: PTY output → terminal
        const unsubData = api.pty.onData(result.id, (data) => {
          term.write(data)
        })
        const unsubExit = api.pty.onExit(result.id, () => {
          term.writeln('\r\n\x1b[33m[Process exited]\x1b[0m')
        })

        // Bridge: terminal input → PTY
        term.onData(data => {
          api.pty.write(result.id, data)
        })

        // Handle resize
        const observer = new ResizeObserver(() => {
          fit.fit()
          api.pty.resize(result.id, term.cols, term.rows)
        })
        observer.observe(containerRef.current)

        setLoading(false)

        // Handle commands queued from RunPanel / AppContext
        const onRunCmd = (e) => {
          if (ptyIdRef.current) api.pty.write(ptyIdRef.current, e.detail.command + '\r')
        }
        window.addEventListener('kendr:run-command', onRunCmd)

        return () => {
          window.removeEventListener('kendr:run-command', onRunCmd)
          unsubData?.()
          unsubExit?.()
          observer.disconnect()
          api.pty.kill(result.id)
          window.__kendrPtyId = null
          term.dispose()
        }
      } catch (err) {
        if (!cancelled) { setError(err.message); setLoading(false) }
      }
    }

    const cleanup = init()
    return () => {
      cancelled = true
      cleanup?.then?.(fn => fn?.())
    }
  }, [])

  return (
    <div className="terminal-panel">
      <div className="terminal-header">
        <span className="terminal-title">Terminal</span>
        <div className="terminal-actions">
          <button className="icon-btn" title="New terminal" onClick={() => {
            // Kill and recreate
            if (ptyIdRef.current) window.kendrAPI?.pty.kill(ptyIdRef.current)
            termRef.current?.dispose()
            ptyIdRef.current = null
            termRef.current = null
          }}>+</button>
          <button
            className="icon-btn"
            title="Close terminal (Ctrl+`)"
            onClick={() => dispatch({ type: 'SET_TERMINAL', open: false })}
          >×</button>
        </div>
      </div>
      {loading && <div className="terminal-loading">Initializing terminal…</div>}
      {error && <div className="terminal-error">{error} – node-pty may not be installed</div>}
      <div ref={containerRef} className="terminal-xterm" style={{ opacity: loading ? 0 : 1 }} />
    </div>
  )
}
