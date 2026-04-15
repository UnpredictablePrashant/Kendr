import React, { useEffect, useMemo, useState } from 'react'

function basename(filePath) {
  return String(filePath || '').split(/[\\/]/).pop() || filePath || 'file'
}

function parentDir(filePath) {
  const raw = String(filePath || '').trim()
  if (!raw) return ''
  const idx = Math.max(raw.lastIndexOf('/'), raw.lastIndexOf('\\'))
  if (idx <= 0) return raw
  return raw.slice(0, idx)
}

function classifyDiffLine(line) {
  if (line.startsWith('@@')) return 'hunk'
  if (line.startsWith('diff --git') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++')) return 'meta'
  if (line.startsWith('+')) return 'add'
  if (line.startsWith('-')) return 'remove'
  return 'context'
}

function countDiffLines(diffText) {
  let adds = 0
  let removes = 0
  for (const line of String(diffText || '').split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---')) continue
    if (line.startsWith('+')) adds += 1
    if (line.startsWith('-')) removes += 1
  }
  return { adds, removes }
}

export default function GitDiffPreview({ cwd, filePath, onClose, onOpenFile }) {
  const [loading, setLoading] = useState(false)
  const [diff, setDiff] = useState('')
  const [error, setError] = useState('')
  const targetCwd = useMemo(() => String(cwd || '').trim() || parentDir(filePath), [cwd, filePath])
  const stats = useMemo(() => countDiffLines(diff), [diff])

  useEffect(() => {
    if (!filePath) return undefined
    let cancelled = false
    async function loadDiff() {
      if (!targetCwd || !window.kendrAPI?.git?.diff) {
        setDiff('')
        setError('No git workspace available for diff preview.')
        setLoading(false)
        return
      }
      setLoading(true)
      setDiff('')
      setError('')
      try {
        const result = await window.kendrAPI.git.diff(targetCwd, filePath)
        if (cancelled) return
        if (result?.error) {
          setError(String(result.error))
          setDiff('')
        } else {
          setDiff(String(result?.diff || ''))
        }
      } catch (err) {
        if (cancelled) return
        setError(String(err?.message || err || 'Failed to load diff preview.'))
        setDiff('')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    loadDiff()
    return () => { cancelled = true }
  }, [filePath, targetCwd])

  if (!filePath) return null

  return (
    <div className="gdp-overlay" onClick={(event) => { if (event.target === event.currentTarget) onClose?.() }}>
      <div className="gdp-sheet">
        <div className="gdp-header">
          <div className="gdp-header-main">
            <div className="gdp-eyebrow">Diff Preview</div>
            <div className="gdp-title">{basename(filePath)}</div>
            <div className="gdp-path">{filePath}</div>
          </div>
          <div className="gdp-actions">
            <button className="gdp-btn" onClick={() => onOpenFile?.(filePath)}>Open file</button>
            <button className="gdp-btn gdp-btn--close" onClick={() => onClose?.()}>Close</button>
          </div>
        </div>

        {!!diff && (
          <div className="gdp-stats">
            <span className="gdp-stat gdp-stat--add">+{stats.adds}</span>
            <span className="gdp-stat gdp-stat--remove">-{stats.removes}</span>
          </div>
        )}

        <div className="gdp-body">
          {loading ? (
            <div className="gdp-empty">Loading diff…</div>
          ) : error ? (
            <div className="gdp-empty gdp-empty--error">{error}</div>
          ) : !diff ? (
            <div className="gdp-empty">No git diff for this file.</div>
          ) : (
            <div className="gdp-code">
              {diff.split('\n').map((line, index) => (
                <div key={`${index}-${line}`} className={`gdp-line gdp-line--${classifyDiffLine(line)}`}>
                  <span className="gdp-line-no">{index + 1}</span>
                  <code className="gdp-line-text">{line || ' '}</code>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
