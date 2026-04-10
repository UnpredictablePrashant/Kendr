import React, { useState, useRef, useCallback, useEffect } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import { useApp } from '../contexts/AppContext'
import { basename, resolveSelectedModel } from '../lib/modelSelection'

const LANG_MAP = {
  js:'javascript', jsx:'javascript', ts:'typescript', tsx:'typescript',
  py:'python', json:'json', md:'markdown', html:'html', css:'css',
  yml:'yaml', yaml:'yaml', sh:'shell', rs:'rust', go:'go', rb:'ruby',
  php:'php', java:'java', cpp:'cpp', c:'c', sql:'sql', toml:'toml',
}

function extractCode(text) {
  const m = text.match(/```(?:\w*)\n?([\s\S]*?)```/)
  return m ? m[1].trimEnd() : text.trim()
}

function stepIcon(step) {
  const msg = (step.message || step.agent || step.reason || '').toLowerCase()
  if (msg.match(/read|open|load|fetch.*file/)) return '📄'
  if (msg.match(/write|edit|creat|modif|sav/)) return '✏️'
  if (msg.match(/run|exec|command|bash|shell|terminal/)) return '⚡'
  if (msg.match(/search|grep|find|look/)) return '🔍'
  if (msg.match(/web|http|url|browse/)) return '🌐'
  if (msg.match(/test/)) return '🧪'
  if (msg.match(/git/)) return '🔀'
  return '🤖'
}

export default function AIComposer({ editorInstanceRef }) {
  const { state: app, dispatch: appDispatch, refreshModelInventory } = useApp()
  const [mode, setMode]             = useState('agent')  // agent | chat | edit
  const [messages, setMessages]     = useState([])
  const [input, setInput]           = useState('')
  const [streaming, setStreaming]   = useState(false)
  const [attachedFiles, setAttachedFiles] = useState([])
  const [mentionAnchor, setMentionAnchor] = useState(null)
  const [applyDiff, setApplyDiff]   = useState(null)
  const [editPrompt, setEditPrompt] = useState('')
  const [editStreaming, setEditStreaming] = useState(false)
  const [editDiff, setEditDiff]     = useState(null)
  const [editPhase, setEditPhase]   = useState('input')
  const esRef       = useRef(null)
  const threadEndRef = useRef(null)
  const inputRef    = useRef(null)
  const chatId      = useRef(`comp-${Date.now()}`).current

  const apiBase   = app.backendUrl || 'http://127.0.0.1:2151'
  const activeTab = app.openTabs.find(t => t.path === app.activeTabPath)
  const selection = app.editorSelection
  const selectedModelMeta = resolveSelectedModel(app.selectedModel)
  const modelInventory = app.modelInventory

  useEffect(() => {
    refreshModelInventory(false)
  }, [refreshModelInventory])

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Listen for Ctrl+K → edit mode; inline widget submit
  useEffect(() => {
    const toEdit = () => { setMode('edit'); setEditPhase('input') }
    const setModeEvt = (e) => {
      if (e.detail) { setMode(e.detail); if (e.detail === 'edit') setEditPhase('input') }
    }
    const inlineSubmit = (e) => {
      const { instruction } = e.detail || {}
      if (!instruction) return
      setMode('edit')
      setEditPhase('input')
      setEditPrompt(instruction)
      setTimeout(() => window.dispatchEvent(new CustomEvent('kendr:composer-edit-submit')), 60)
    }
    window.addEventListener('kendr:composer-edit', toEdit)
    window.addEventListener('kendr:composer-set-mode', setModeEvt)
    window.addEventListener('kendr:inline-edit-submit', inlineSubmit)
    return () => {
      window.removeEventListener('kendr:composer-edit', toEdit)
      window.removeEventListener('kendr:composer-set-mode', setModeEvt)
      window.removeEventListener('kendr:inline-edit-submit', inlineSubmit)
    }
  }, [])

  // Keep refs for use inside event handlers
  const editPromptRef  = useRef(editPrompt)
  editPromptRef.current = editPrompt
  const sendEditRef    = useRef(null)

  useEffect(() => {
    const handler = () => sendEditRef.current?.()
    window.addEventListener('kendr:composer-edit-submit', handler)
    return () => window.removeEventListener('kendr:composer-edit-submit', handler)
  }, [])

  // ── SSE helper ──────────────────────────────────────────────────────────────
  const runSSE = useCallback(async ({ text, chatIdOverride, onStep, onResult, onDone, onError }) => {
    const runId = `comp-${Date.now().toString(36)}`
    const isProjectAgent = !!app.projectRoot
    const selected = resolveSelectedModel(app.selectedModel)
    let resp
    try {
      resp = await fetch(`${apiBase}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          channel: isProjectAgent ? 'project_ui' : 'webchat',
          sender_id: isProjectAgent ? 'project_ui_user' : 'composer',
          chat_id: chatIdOverride || chatId, run_id: runId,
          working_directory: app.projectRoot || undefined,
          project_root: app.projectRoot || undefined,
          provider: selected.provider || undefined,
          model: selected.model || undefined,
        }),
      })
    } catch (e) { refreshModelInventory(true); onError?.(`Network error: ${e.message}`); return }
    if (!resp.ok) { refreshModelInventory(true); onError?.(`Backend error: ${resp.statusText}`); return }
    const { run_id: srvId } = await resp.json().catch(() => ({}))
    const effectiveId = srvId || runId

    esRef.current?.close()
    const es = new EventSource(`${apiBase}/api/stream?run_id=${encodeURIComponent(effectiveId)}`)
    esRef.current = es
    let lastResult = ''
    let stepCount = 0

    es.addEventListener('step', e => {
      try {
        const step = JSON.parse(e.data)
        onStep?.({
          stepId: step.step_id || step.id || `step-${++stepCount}`,
          agent: step.agent || step.name || 'agent',
          status: step.status || 'running',
          message: step.message || '',
          reason: step.reason || '',
          durationLabel: step.duration_label || '',
        })
      } catch {}
    })
    es.addEventListener('result', e => {
      try {
        const d = JSON.parse(e.data)
        lastResult = d.final_output || d.output || d.draft_response || d.response || ''
        onResult?.(lastResult)
      } catch {}
    })
    es.addEventListener('done', () => { es.close(); onDone?.(lastResult) })
    es.addEventListener('error', e => {
      refreshModelInventory(true)
      try { const d = JSON.parse(e.data); onError?.(d.message || 'Run failed') } catch {}
      es.close(); onDone?.(lastResult)
    })
    es.onerror = () => { refreshModelInventory(true); es.close(); onDone?.(lastResult) }
  }, [apiBase, chatId, app.projectRoot, app.selectedModel, refreshModelInventory])

  const stopStream = () => esRef.current?.close()

  const buildContextPrompt = useCallback((userText) => {
    let ctx = userText
    if (mode === 'agent') {
      ctx =
        '[IDE agent mode]\n' +
        '- Work like a coding agent inside an IDE.\n' +
        '- Inspect files and context before changing code.\n' +
        '- Keep progress updates and final answers concise, direct, and action-oriented.\n' +
        '- If you propose code changes, prefer complete code blocks with filenames when that helps apply them cleanly.\n' +
        '- Use the current project and file context instead of answering generically.\n\n' +
        userText
    }
    if (activeTab) {
      const content = window.__tabContents?.[activeTab.path] ?? activeTab.content ?? ''
      ctx += `\n\n[Active file: ${activeTab.name}]\n\`\`\`${activeTab.language || ''}\n${content.slice(0, 4000)}\n\`\`\``
    }
    if (selection?.text && selection.path === activeTab?.path) {
      ctx += `\n\n[Selected (lines ${selection.startLine}–${selection.endLine})]\n\`\`\`\n${selection.text}\n\`\`\``
    }
    for (const f of attachedFiles) {
      const c = window.__tabContents?.[f.path] ?? ''
      if (c) ctx += `\n\n[@${f.name}]\n\`\`\`\n${c.slice(0, 2000)}\n\`\`\``
    }
    return ctx
  }, [activeTab, selection, attachedFiles, mode])

  const composerModelBadge = (() => {
    if (selectedModelMeta.model) {
      return {
        primary: `Selected · ${selectedModelMeta.label}`,
        secondary: app.projectRoot ? `Project · ${basename(app.projectRoot)}` : '',
      }
    }
    const configuredProvider = String(modelInventory?.configured_provider || '').trim().toLowerCase()
    const configuredModel = String(modelInventory?.configured_model || '').trim()
    const activeProvider = String(modelInventory?.active_provider || '').trim().toLowerCase()
    const activeModel = String(modelInventory?.active_model || '').trim()
    if (configuredProvider && configuredModel) {
      const configuredLabel = resolveSelectedModel(`${configuredProvider}/${configuredModel}`).label
      const configuredReady = modelInventory?.configured_provider_ready !== false
      const activeDiffers = configuredProvider !== activeProvider || configuredModel !== activeModel
      return {
        primary: `${configuredReady ? 'Configured' : 'Configured offline'} · ${configuredLabel}`,
        secondary: activeDiffers && activeProvider && activeModel
          ? `Active · ${resolveSelectedModel(`${activeProvider}/${activeModel}`).label}`
          : (app.projectRoot ? `Project · ${basename(app.projectRoot)}` : ''),
      }
    }
    return {
      primary: 'Auto · Backend default',
      secondary: app.projectRoot ? `Project · ${basename(app.projectRoot)}` : '',
    }
  })()

  // ── SEND ────────────────────────────────────────────────────────────────────
  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming) return
    setInput('')
    setMentionAnchor(null)
    const msgId = `a-${Date.now()}`
    setMessages(m => [
      ...m,
      { id: `u-${Date.now()}`, role: 'user', content: text },
      { id: msgId, role: 'assistant', content: '', steps: [], status: 'thinking' },
    ])
    setStreaming(true)
    try {
      await runSSE({
        text: buildContextPrompt(text),
        onStep: (step) => setMessages(m => m.map(msg => {
          if (msg.id !== msgId) return msg
          const steps = [...(msg.steps || [])]
          const idx = steps.findIndex(s => s.stepId === step.stepId)
          if (idx >= 0) steps[idx] = step; else steps.push(step)
          return { ...msg, steps }
        })),
        onResult: (out) => setMessages(m => m.map(msg =>
          msg.id === msgId ? { ...msg, content: out, status: 'streaming' } : msg
        )),
        onDone: (out) => {
          setMessages(m => m.map(msg =>
            msg.id === msgId ? { ...msg, content: out || msg.content, status: 'done' } : msg
          ))
          setStreaming(false)
        },
        onError: (err) => {
          setMessages(m => m.map(msg =>
            msg.id === msgId ? { ...msg, content: err, status: 'error' } : msg
          ))
          setStreaming(false)
        },
      })
    } catch (e) {
      setMessages(m => m.map(msg =>
        msg.id === msgId ? { ...msg, content: `Error: ${e.message}`, status: 'error' } : msg
      ))
      setStreaming(false)
    }
  }, [input, streaming, runSSE, buildContextPrompt])

  // ── EDIT ────────────────────────────────────────────────────────────────────
  const sendEdit = useCallback(async () => {
    const prompt = editPromptRef.current.trim()
    if (!prompt || editStreaming || !activeTab) return

    const codeToEdit = (selection?.path === activeTab.path && selection?.text)
      ? selection.text
      : (window.__tabContents?.[activeTab.path] ?? activeTab.content ?? '')
    const lang = LANG_MAP[activeTab.name?.split('.').pop()?.toLowerCase()] || 'plaintext'

    const fullPrompt = `Edit the following code from "${activeTab.name}":

\`\`\`${lang}
${codeToEdit}
\`\`\`

Instruction: ${prompt}

Return ONLY the complete modified code in a single code block. No explanation.`

    setEditStreaming(true)
    setEditPhase('streaming')
    try {
      await runSSE({
        text: fullPrompt,
        chatIdOverride: `edit-${chatId}`,
        onDone: (result) => {
          setEditStreaming(false)
          setEditDiff({ original: codeToEdit, modified: extractCode(result), lang })
          setEditPhase('diff')
        },
        onError: () => { setEditStreaming(false); setEditPhase('input') },
      })
    } catch { setEditStreaming(false); setEditPhase('input') }
  }, [editStreaming, activeTab, selection, runSSE, chatId])

  sendEditRef.current = sendEdit

  const applyEdit = useCallback(() => {
    const editor = editorInstanceRef?.current
    if (!editor || !editDiff) return
    const sel = app.editorSelection
    if (sel?.text && sel.path === activeTab?.path) {
      editor.executeEdits('ai', [{
        range: { startLineNumber: sel.startLine, startColumn: sel.startCol, endLineNumber: sel.endLine, endColumn: sel.endCol },
        text: editDiff.modified,
      }])
    } else {
      editor.setValue(editDiff.modified)
    }
    if (activeTab) {
      window.kendrAPI?.fs.writeFile(activeTab.path, editor.getValue())
      appDispatch({ type: 'MARK_TAB_MODIFIED', path: activeTab.path, modified: false })
    }
    setEditPhase('applied')
    setEditDiff(null)
    setEditPrompt('')
    setTimeout(() => setEditPhase('input'), 1800)
  }, [editDiff, editorInstanceRef, app.editorSelection, activeTab, appDispatch])

  // ── APPLY from agent thread ──────────────────────────────────────────────────
  const handleApplyBlock = useCallback(({ code, lang, filename }) => {
    const original = activeTab ? (window.__tabContents?.[activeTab.path] ?? activeTab.content ?? '') : ''
    const targetPath = filename
      ? (app.projectRoot ? `${app.projectRoot}/${filename}` : filename)
      : activeTab?.path
    setApplyDiff({ original, modified: code, lang: lang || 'plaintext', filename, targetPath })
  }, [activeTab, app.projectRoot])

  const acceptApply = useCallback(async () => {
    if (!applyDiff) return
    const editor = editorInstanceRef?.current
    if (editor && applyDiff.targetPath === activeTab?.path) {
      editor.setValue(applyDiff.modified)
      window.kendrAPI?.fs.writeFile(applyDiff.targetPath, applyDiff.modified)
      appDispatch({ type: 'MARK_TAB_MODIFIED', path: applyDiff.targetPath, modified: false })
    } else if (applyDiff.targetPath) {
      await window.kendrAPI?.fs.writeFile(applyDiff.targetPath, applyDiff.modified)
      if (applyDiff.filename) {
        const name = applyDiff.filename.split('/').pop()
        appDispatch({ type: 'OPEN_TAB', tab: { path: applyDiff.targetPath, name, language: LANG_MAP[name.split('.').pop()?.toLowerCase()] || 'plaintext', content: applyDiff.modified, modified: false } })
      }
    }
    setApplyDiff(null)
  }, [applyDiff, editorInstanceRef, activeTab, appDispatch])

  // ── @mention ─────────────────────────────────────────────────────────────────
  const handleInputChange = (e) => {
    const val = e.target.value
    setInput(val)
    const atIdx = val.lastIndexOf('@')
    if (atIdx !== -1 && (atIdx === 0 || /\s/.test(val[atIdx - 1]))) {
      const query = val.slice(atIdx + 1)
      if (!query.includes(' ') && !query.includes('\n')) {
        setMentionAnchor({ query, idx: atIdx }); return
      }
    }
    setMentionAnchor(null)
  }

  const pickMention = (tab) => {
    if (!mentionAnchor) return
    const before = input.slice(0, mentionAnchor.idx)
    const after = input.slice(mentionAnchor.idx + 1 + mentionAnchor.query.length)
    setInput(`${before}@${tab.name} ${after}`)
    setAttachedFiles(f => [...f.filter(x => x.path !== tab.path), { path: tab.path, name: tab.name }])
    setMentionAnchor(null)
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send() }
    if (e.key === 'Escape') setMentionAnchor(null)
  }

  // ── RENDER ───────────────────────────────────────────────────────────────────
  return (
    <div className="ac-panel">

      {/* Apply diff overlay — full panel takeover */}
      {applyDiff && (
        <div className="ac-apply-overlay">
          <div className="ac-apply-bar">
            <span className="ac-apply-title">
              {applyDiff.filename ? `✨ Create ${applyDiff.filename}` : `✨ Edit ${activeTab?.name || 'file'}`}
            </span>
            <div className="ac-apply-btns">
              <button className="ac-accept-btn" onClick={acceptApply}>✓ Accept</button>
              <button className="ac-reject-btn" onClick={() => setApplyDiff(null)}>✕ Reject</button>
            </div>
          </div>
          <DiffEditor
            height="calc(100% - 44px)"
            language={applyDiff.lang}
            original={applyDiff.original}
            modified={applyDiff.modified}
            theme="vs-dark"
            options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, lineNumbers: 'off', scrollBeyondLastLine: false, renderSideBySide: false, padding: { top: 6 }, overviewRulerBorder: false }}
          />
        </div>
      )}

      {!applyDiff && (
        <>
          {/* Header */}
          <div className="ac-header">
            <div className="ac-mode-tabs">
              {[['agent','Agent'],['chat','Chat'],['edit','Edit']].map(([id, label]) => (
                <button key={id}
                  className={`ac-mode-tab ${mode === id ? 'active' : ''}`}
                  onClick={() => { setMode(id); if (id === 'edit') setEditPhase('input') }}>
                  {label}
                </button>
              ))}
            </div>
            <div className="ac-model-badge" title={composerModelBadge.primary}>
              <span className={`ac-model-dot ${selectedModelMeta.isLocal || String(modelInventory?.configured_provider || '').toLowerCase() === 'ollama' ? 'local' : ''}`} />
              <span className="ac-model-primary">{composerModelBadge.primary}</span>
              {composerModelBadge.secondary && (
                <span className="ac-model-secondary">{composerModelBadge.secondary}</span>
              )}
            </div>
            <div className="ac-header-right">
              {streaming && <span className="ac-live-dot" />}
              <button className="ac-header-btn" title="New conversation"
                onClick={() => { setMessages([]); setAttachedFiles([]) }}>⊘</button>
            </div>
          </div>

          {/* ── Agent / Chat ── */}
          {(mode === 'agent' || mode === 'chat') && (
            <>
              {(activeTab || attachedFiles.length > 0) && (
                <div className="ac-context-bar">
                  {activeTab && <span className="ac-ctx-file">📄 {activeTab.name}</span>}
                  {selection?.text && selection.path === activeTab?.path && (
                    <span className="ac-ctx-sel">{selection.text.split('\n').length}L</span>
                  )}
                  {attachedFiles.map(f => (
                    <span key={f.path} className="ac-ctx-attach">
                      @{f.name}
                      <button onClick={() => setAttachedFiles(a => a.filter(x => x.path !== f.path))}>×</button>
                    </span>
                  ))}
                </div>
              )}

              <div className="ac-thread">
                {messages.length === 0 && (
                  <div className="ac-empty">
                    <div className="ac-empty-icon">{mode === 'agent' ? '✨' : '💬'}</div>
                    <div className="ac-empty-title">{mode === 'agent' ? 'Agent' : 'Chat'}</div>
                    <div className="ac-empty-sub">
                      {mode === 'agent'
                        ? 'The agent works against the current project like an IDE coding assistant. It can inspect files, run tasks, and prepare code edits with project context.'
                        : 'Ask questions about code, get explanations, or request suggestions.'}
                    </div>
                    {activeTab && (
                      <div className="ac-chips">
                        {(mode === 'agent'
                          ? ['Refactor this file', 'Find and fix bugs', 'Add TypeScript types', 'Write unit tests']
                          : ['Explain this code', 'What does this do?', 'How can I improve this?', 'Find potential issues']
                        ).map(s => (
                          <button key={s} className="ac-chip" onClick={() => { setInput(s); inputRef.current?.focus() }}>{s}</button>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {messages.map(msg => (
                  <div key={msg.id} className={`ac-msg ac-msg--${msg.role}`}>
                    {msg.role === 'user' ? (
                      <div className="ac-user-bubble">{msg.content}</div>
                    ) : (
                      <div className="ac-asst-msg">
                        {msg.steps?.length > 0 && (
                          <AgentSteps steps={msg.steps} live={streaming && msg.status !== 'done' && msg.status !== 'error'} />
                        )}
                        {msg.status === 'thinking' && !msg.steps?.length ? (
                          <div className="ac-thinking-row">
                            <span className="ac-thinking"><span /><span /><span /></span>
                            <span className="ac-thinking-label">Thinking…</span>
                          </div>
                        ) : msg.status === 'error' ? (
                          <div className="ac-error-msg">⚠ {msg.content}</div>
                        ) : msg.content ? (
                          <AgentResponse content={msg.content} onApply={mode === 'agent' ? handleApplyBlock : null} />
                        ) : null}
                      </div>
                    )}
                  </div>
                ))}
                <div ref={threadEndRef} />
              </div>

              {mentionAnchor && (
                <div className="ac-mention-picker">
                  {app.openTabs.length === 0 ? (
                    <div className="ac-mention-empty">No open files</div>
                  ) : app.openTabs
                    .filter(t => !mentionAnchor.query || t.name.toLowerCase().includes(mentionAnchor.query.toLowerCase()))
                    .slice(0, 7)
                    .map(t => (
                      <button key={t.path} className="ac-mention-item" onMouseDown={() => pickMention(t)}>
                        <span className="ac-mention-name">{t.name}</span>
                        <span className="ac-mention-path">{t.path.replace(app.projectRoot || '', '').slice(-40)}</span>
                      </button>
                    ))}
                </div>
              )}

              <div className="ac-input-area">
                <textarea
                  ref={inputRef}
                  className="ac-input"
                  placeholder={mode === 'agent'
                    ? 'Ask the project agent to inspect, edit, debug, or explain code… (@ to mention files, Ctrl+Enter to send)'
                    : 'Ask about code… (Ctrl+Enter to send)'}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKey}
                  rows={3}
                  disabled={streaming}
                />
                <div className="ac-input-footer">
                  <span className="ac-input-hint">Ctrl+Enter</span>
                  <button
                    className={`ac-send-btn ${streaming ? 'stop' : ''}`}
                    onClick={streaming ? () => { stopStream(); setStreaming(false) } : send}
                    disabled={!streaming && !input.trim()}
                  >
                    {streaming ? <StopIcon /> : <SendIcon />}
                  </button>
                </div>
              </div>
            </>
          )}

          {/* ── Edit mode ── */}
          {mode === 'edit' && (
            <div className="ac-edit">
              {!activeTab ? (
                <div className="ac-empty">
                  <div className="ac-empty-icon">✏️</div>
                  <div className="ac-empty-sub">Open a file in the editor to use Edit mode.</div>
                </div>
              ) : editPhase === 'diff' ? (
                <div className="ac-diff-wrap">
                  <div className="ac-diff-toolbar">
                    <span className="ac-diff-label">Proposed — {activeTab.name}</span>
                    <button className="ac-accept-btn" onClick={applyEdit}>✓ Accept</button>
                    <button className="ac-reject-btn" onClick={() => { setEditPhase('input'); setEditDiff(null) }}>✕ Reject</button>
                  </div>
                  <DiffEditor
                    height="calc(100% - 44px)"
                    language={editDiff.lang}
                    original={editDiff.original}
                    modified={editDiff.modified}
                    theme="vs-dark"
                    options={{ readOnly: true, minimap: { enabled: false }, fontSize: 12, lineNumbers: 'off', scrollBeyondLastLine: false, renderSideBySide: false, padding: { top: 6 }, overviewRulerBorder: false }}
                  />
                </div>
              ) : editPhase === 'applied' ? (
                <div className="ac-empty">
                  <div className="ac-empty-icon">✓</div>
                  <div className="ac-empty-title" style={{ color: 'var(--kc-teal)' }}>Changes applied!</div>
                </div>
              ) : (
                <div className="ac-edit-form">
                  <div className="ac-edit-context">
                    {selection?.text && selection.path === activeTab.path
                      ? `✏ ${selection.text.split('\n').length} lines selected in ${activeTab.name}`
                      : `✏ Editing entire file: ${activeTab.name}`}
                  </div>
                  <textarea
                    className="ac-edit-textarea"
                    placeholder={"Describe the change…\ne.g. Add error handling, refactor to async/await, add TypeScript types"}
                    value={editPrompt}
                    onChange={e => setEditPrompt(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendEdit() } }}
                    rows={7}
                    disabled={editStreaming}
                    autoFocus
                  />
                  {editStreaming ? (
                    <div className="ac-progress">
                      <span className="ac-spinner" />
                      <span>Rewriting code…</span>
                      <button className="ac-stop-link" onClick={() => { stopStream(); setEditStreaming(false); setEditPhase('input') }}>Stop</button>
                    </div>
                  ) : (
                    <button className="ac-run-btn" onClick={sendEdit} disabled={!editPrompt.trim()}>
                      ✨ Apply Edit <span className="ac-hint-key">Ctrl+Enter</span>
                    </button>
                  )}
                  <div className="ac-edit-hints">
                    <span>Ctrl+Enter to run</span>
                    <span>Select lines in editor to target a range</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Agent step cards ──────────────────────────────────────────────────────────
function AgentSteps({ steps, live }) {
  const [open, setOpen] = useState(false)
  const running = steps.filter(s => s.status === 'running')

  return (
    <div className="as-root">
      <button className="as-toggle" onClick={() => setOpen(o => !o)}>
        <span className="as-toggle-left">
          {live && running.length > 0 ? (
            <><span className="as-spinner" /><span className="as-toggle-txt">{running[0].message || 'Working…'}</span></>
          ) : (
            <><span className="as-check">✓</span><span className="as-toggle-txt">{steps.length} action{steps.length !== 1 ? 's' : ''}</span></>
          )}
        </span>
        <span className="as-chevron">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="as-list">
          {steps.map((s, i) => (
            <div key={s.stepId || i} className={`as-step as-step--${s.status}`}>
              <span className="as-step-icon">{stepIcon(s)}</span>
              <div className="as-step-body">
                <span className="as-step-msg">{s.message || s.agent}</span>
                {s.reason && <span className="as-step-reason">{s.reason}</span>}
              </div>
              <span className="as-step-meta">
                {s.status === 'running'
                  ? <span className="as-spinner as-spinner--sm" />
                  : <span className="as-step-dur">{s.durationLabel}</span>}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Agent response with Apply buttons per code block ──────────────────────────
function AgentResponse({ content, onApply }) {
  const parts = []
  const re = /```(\w*)\n?([\s\S]*?)```/g
  let last = 0, m
  while ((m = re.exec(content)) !== null) {
    if (m.index > last) parts.push({ t: 'text', v: content.slice(last, m.index) })
    parts.push({ t: 'code', lang: m[1], v: m[2].trimEnd() })
    last = m.index + m[0].length
  }
  if (last < content.length) parts.push({ t: 'text', v: content.slice(last) })

  return (
    <div className="ac-md">
      {parts.map((p, i) =>
        p.t === 'code'
          ? <AgentCodeBlock key={i} lang={p.lang} code={p.v} onApply={onApply} />
          : <AcText key={i} text={p.v} />
      )}
    </div>
  )
}

function AgentCodeBlock({ lang, code, onApply }) {
  const [copied, setCopied]   = useState(false)
  const [applied, setApplied] = useState(false)
  const firstLine = code.split('\n')[0]
  const filename  = firstLine.match(/^[#/*\s]*(?:filename|file):\s*(.+)/i)?.[1]?.trim()

  const copy = () => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500) }
  const apply = () => {
    onApply?.({ code, lang: lang || 'plaintext', filename })
    setApplied(true); setTimeout(() => setApplied(false), 2000)
  }

  return (
    <div className="ac-code-block">
      <div className="ac-code-header">
        <span className="ac-code-lang">{filename || lang || 'code'}</span>
        <div className="ac-code-actions">
          {onApply && (
            <button className={`ac-apply-chip ${applied ? 'applied' : ''}`} onClick={apply}>
              {applied ? '✓ Applied' : '⊕ Apply'}
            </button>
          )}
          <button className="ac-code-copy" onClick={copy}>{copied ? '✓' : '⧉'}</button>
        </div>
      </div>
      <pre className="ac-code-body"><code>{code}</code></pre>
    </div>
  )
}

function AcText({ text }) {
  const html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="ac-inline-code">$1</code>')
    .replace(/\n/g, '<br/>')
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}

function SendIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
}
function StopIcon() {
  return <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2.5"/></svg>
}
