/**
 * Minimal persistent settings store.
 * Writes a JSON file to Electron's userData directory.
 * Drop-in replacement for electron-store with no external dependencies.
 */
import { app } from 'electron'
import { join } from 'path'
import { readFileSync, writeFileSync, mkdirSync } from 'fs'

export class Store {
  constructor(opts = {}) {
    // userData is e.g. C:\Users\<user>\AppData\Roaming\kendr-desktop
    const dir = app.getPath('userData')
    this._path = join(dir, 'settings.json')
    this._defaults = opts.defaults || {}
    this._data = this._load()
  }

  _load() {
    try {
      const raw = readFileSync(this._path, 'utf-8')
      return { ...this._defaults, ...JSON.parse(raw) }
    } catch (_) {
      return { ...this._defaults }
    }
  }

  _save() {
    try {
      mkdirSync(app.getPath('userData'), { recursive: true })
      writeFileSync(this._path, JSON.stringify(this._data, null, 2), 'utf-8')
    } catch (_) {}
  }

  /** Get a value by dot-separated key, or the full store object if no key given. */
  get(key) {
    if (!key) return { ...this._data }
    return key.split('.').reduce((obj, k) => (obj != null ? obj[k] : undefined), this._data)
  }

  /** Set a value. Accepts either (key, value) or a plain object to merge. */
  set(key, value) {
    if (typeof key === 'object' && key !== null) {
      Object.assign(this._data, key)
    } else {
      const parts = String(key).split('.')
      let node = this._data
      for (let i = 0; i < parts.length - 1; i++) {
        if (node[parts[i]] === undefined || typeof node[parts[i]] !== 'object') {
          node[parts[i]] = {}
        }
        node = node[parts[i]]
      }
      node[parts[parts.length - 1]] = value
    }
    this._save()
  }

  /** Returns a shallow copy of all stored data. */
  get store() {
    return { ...this._data }
  }
}
