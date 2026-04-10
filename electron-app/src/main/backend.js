/**
 * BackendManager – auto-discovers and manages the kendr gateway + UI servers.
 *
 * gateway_server.py starts BOTH:
 *   • Gateway  →  http://127.0.0.1:8790  (agent execution)
 *   • UI       →  http://127.0.0.1:2151  (HTTP API used by the Electron renderer)
 *
 * We spawn gateway_server.py once and health-check both ports.
 */
import { spawn } from 'child_process'
import http from 'http'
import { existsSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'

const UI_PORT      = 2151
const GATEWAY_PORT = 8790

export class BackendManager {
  constructor(store) {
    this.store = store
    this._proc   = null
    this._logs   = []            // rolling last-200 lines
    this._status = {
      gateway:  'stopped',      // stopped | starting | running | error
      ui:       'stopped',
      pid:      null,
      kendrRoot: null,
      error:    null,
    }
    this._listeners = []         // (status) => void  — push to renderer
    this._healthTimer = null
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /** Current status snapshot (safe to serialise and send over IPC). */
  status() { return { ...this._status, logs: [...this._logs] } }

  /** Register a callback that fires on every status change. */
  onChange(fn) { this._listeners.push(fn) }

  async startIfNeeded() {
    const [uiOk, gwOk] = await Promise.all([
      this._ping(UI_PORT), this._ping(GATEWAY_PORT)
    ])
    if (uiOk && gwOk) {
      this._set({ gateway: 'running', ui: 'running' })
      this._startHealthWatch()
      return { ok: true, already: true }
    }
    if (uiOk || gwOk) {
      // Partially up – adopt and monitor
      this._set({ gateway: gwOk ? 'running' : 'starting', ui: uiOk ? 'running' : 'starting' })
      this._startHealthWatch()
    }
    return this.start()
  }

  async start() {
    if (this._status.gateway === 'running' && this._status.ui === 'running') {
      return { ok: true, already: true }
    }

    const kendrRoot = this._findKendrRoot()
    if (!kendrRoot) {
      this._set({ gateway: 'error', ui: 'error', error: 'Cannot locate gateway_server.py. Set kendrRoot in settings.' })
      return { error: this._status.error }
    }

    const gatewayScript = join(kendrRoot, 'gateway_server.py')
    const python = this.store.get('pythonPath') || 'python'
    const providerEnv = this._providerEnv()

    this._log(`[backend] Starting: ${python} ${gatewayScript}`)
    this._set({ gateway: 'starting', ui: 'starting', error: null, kendrRoot })

    return new Promise((resolve) => {
      try {
        this._proc = spawn(python, [gatewayScript], {
          cwd: kendrRoot,
          env: {
            ...process.env,
            KENDR_UI_ENABLED: '1',
            GATEWAY_PORT: String(GATEWAY_PORT),
            KENDR_UI_PORT: String(UI_PORT),
            PYTHONUNBUFFERED: '1',
            ...providerEnv,
          },
          stdio: ['ignore', 'pipe', 'pipe'],
          windowsHide: true,
        })

        this._status.pid = this._proc.pid
        let resolved = false

        const tryResolve = () => {
          if (!resolved) { resolved = true; resolve({ ok: true }) }
        }

        const handleLine = (line) => {
          this._log(line)
          if (line.includes('Gateway server running')) {
            this._set({ gateway: 'running' })
            tryResolve()
          }
          if (line.includes('Kendr UI running') || line.includes('UI server') || line.includes('2151')) {
            this._set({ ui: 'running' })
            tryResolve()
          }
        }

        let stdoutBuf = '', stderrBuf = ''
        this._proc.stdout?.on('data', d => {
          stdoutBuf += d.toString()
          const lines = stdoutBuf.split('\n')
          stdoutBuf = lines.pop()
          lines.forEach(handleLine)
        })
        this._proc.stderr?.on('data', d => {
          stderrBuf += d.toString()
          const lines = stderrBuf.split('\n')
          stderrBuf = lines.pop()
          lines.forEach(l => this._log(`[stderr] ${l}`))
        })

        this._proc.on('error', err => {
          this._log(`[backend] spawn error: ${err.message}`)
          this._set({ gateway: 'error', ui: 'error', error: err.message, pid: null })
          if (!resolved) { resolved = true; resolve({ error: err.message }) }
        })

        this._proc.on('exit', (code, signal) => {
          this._log(`[backend] exited  code=${code} signal=${signal}`)
          this._proc = null
          this._status.pid = null
          if (this._status.gateway !== 'stopped') {
            this._set({ gateway: code === 0 ? 'stopped' : 'error', ui: 'stopped', error: code ? `Exited ${code}` : null })
          }
          this._stopHealthWatch()
        })

        // Fallback: health-check after 8 s regardless of stdout messages
        setTimeout(async () => {
          const [uiOk, gwOk] = await Promise.all([this._ping(UI_PORT), this._ping(GATEWAY_PORT)])
          if (uiOk)  this._set({ ui: 'running' })
          if (gwOk)  this._set({ gateway: 'running' })
          if (!resolved) {
            resolved = true
            if (uiOk || gwOk) resolve({ ok: true })
            else {
              this._set({ ui: 'error', gateway: 'error', error: 'Did not respond within 8 s' })
              resolve({ error: 'Did not respond within 8 s' })
            }
          }
        }, 8000)

        this._startHealthWatch()
      } catch (err) {
        this._set({ gateway: 'error', ui: 'error', error: err.message, pid: null })
        resolve({ error: err.message })
      }
    })
  }

  stop() {
    this._stopHealthWatch()
    if (this._proc) {
      try { this._proc.kill('SIGTERM') } catch (_) {}
      this._proc = null
    }
    this._set({ gateway: 'stopped', ui: 'stopped', pid: null })
    return { ok: true }
  }

  async restart() {
    this.stop()
    await new Promise(r => setTimeout(r, 600))
    return this.start()
  }

  getLogs() { return [...this._logs] }

  // ── Internals ──────────────────────────────────────────────────────────────

  _set(patch) {
    Object.assign(this._status, patch)
    const snapshot = this.status()
    this._listeners.forEach(fn => { try { fn(snapshot) } catch (_) {} })
  }

  _log(line) {
    if (!line.trim()) return
    this._logs.push(line)
    if (this._logs.length > 200) this._logs.shift()
  }

  _ping(port) {
    return new Promise(resolve => {
      const req = http.get({ hostname: '127.0.0.1', port, path: '/health', timeout: 1500 }, res => {
        resolve(res.statusCode < 500)
      })
      req.on('error', () => resolve(false))
      req.on('timeout', () => { req.destroy(); resolve(false) })
    })
  }

  _startHealthWatch() {
    this._stopHealthWatch()
    this._healthTimer = setInterval(async () => {
      const [uiOk, gwOk] = await Promise.all([this._ping(UI_PORT), this._ping(GATEWAY_PORT)])
      let changed = false
      if (uiOk  && this._status.ui      !== 'running') { this._status.ui      = 'running'; changed = true }
      if (!uiOk && this._status.ui      === 'running') { this._status.ui      = 'error';   changed = true }
      if (gwOk  && this._status.gateway !== 'running') { this._status.gateway = 'running'; changed = true }
      if (!gwOk && this._status.gateway === 'running') { this._status.gateway = 'error';   changed = true }
      if (changed) this._set({})
    }, 5000)
  }

  _stopHealthWatch() {
    if (this._healthTimer) { clearInterval(this._healthTimer); this._healthTimer = null }
  }

  /**
   * Walk up from various anchor points looking for gateway_server.py.
   * Tries saved setting first, then relative paths from __dirname / cwd.
   */
  _findKendrRoot() {
    const saved = this.store.get('kendrRoot')
    if (saved && existsSync(join(saved, 'gateway_server.py'))) return saved

    const anchors = [
      app.getAppPath(),
      process.cwd(),
      // In electron-vite dev, out/main/ → electron-app/ → kendr root
      join(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1'), '../../..'),
    ]

    for (const anchor of anchors) {
      for (let up = 0; up <= 4; up++) {
        let candidate = anchor
        for (let i = 0; i < up; i++) candidate = join(candidate, '..')
        if (existsSync(join(candidate, 'gateway_server.py'))) {
          this.store.set('kendrRoot', candidate)
          return candidate
        }
      }
    }
    return null
  }

  _providerEnv() {
    const mappings = [
      ['anthropicKey', 'ANTHROPIC_API_KEY'],
      ['openaiKey', 'OPENAI_API_KEY'],
      ['openaiOrgId', 'OPENAI_ORG_ID'],
      ['googleKey', 'GOOGLE_API_KEY'],
      ['xaiKey', 'XAI_API_KEY'],
      ['hfToken', 'HUGGINGFACEHUB_API_TOKEN'],
      ['tavilyKey', 'TAVILY_API_KEY'],
      ['braveKey', 'BRAVE_API_KEY'],
      ['serperKey', 'SERPER_API_KEY'],
    ]

    return Object.fromEntries(
      mappings
        .map(([storeKey, envKey]) => [envKey, String(this.store.get(storeKey) || '').trim()])
        .filter(([, value]) => value)
    )
  }
}
