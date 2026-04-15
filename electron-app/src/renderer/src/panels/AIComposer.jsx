import React, { useState, useRef, useCallback, useEffect } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import GitDiffPreview from '../components/GitDiffPreview'
import { useApp } from '../contexts/AppContext'
import { basename, resolveSelectedModel } from '../lib/modelSelection'
import { buildActivityEntry, extractChecklist, isPlanApprovalScope, isSkillApproval, shouldMirrorActivityMessage, summarizeRunArtifacts } from '../lib/runPresentation'

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
  const { state: app, dispatch: appDispatch, openFile, refreshModelInventory } = useApp()
  const [mode, setMode]             = useState('agent')  // agent | plan | chat | edit
  const [messages, setMessages]     = useState([])
  const [diffPreviewPath, setDiffPreviewPath] = useState('')
  const [input, setInput]           = useState('')
  const [streaming, setStreaming]   = useState(false)
  const [awaitingContext, setAwaitingContext] = useState(null)
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
  const mirroredActivityIdsRef = useRef([])

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

  useEffect(() => {
    const entries = messages
      .filter(shouldMirrorActivityMessage)
      .map((msg) => buildActivityEntry(msg, { id: `project:${msg.id}`, source: 'project' }))
      .filter(Boolean)
    const nextIds = new Set(entries.map((entry) => entry.id))
    for (const entry of entries) {
      appDispatch({ type: 'UPSERT_ACTIVITY_ENTRY', entry })
    }
    const removedIds = mirroredActivityIdsRef.current.filter((id) => !nextIds.has(id))
    if (removedIds.length) {
      appDispatch({ type: 'REMOVE_ACTIVITY_ENTRIES', ids: removedIds })
    }
    mirroredActivityIdsRef.current = Array.from(nextIds)
  }, [messages, appDispatch])

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
  const runSSE = useCallback(async ({ text, chatIdOverride, requestMode = 'agent', resumeContext = null, onStep, onActivity, onResult, onAwaiting, onDone, onError }) => {
    const runId = `comp-${Date.now().toString(36)}`
    const isProjectAgent = !!app.projectRoot
    const selected = resolveSelectedModel(app.selectedModel)
    const endpoint = resumeContext ? `${apiBase}/api/chat/resume` : `${apiBase}/api/chat`
    const payload = resumeContext
      ? {
          run_id: resumeContext.runId,
          workflow_id: resumeContext.workflowId,
          text,
          channel: isProjectAgent ? 'project_ui' : 'webchat',
        }
      : {
          text,
          channel: isProjectAgent ? 'project_ui' : 'webchat',
          sender_id: isProjectAgent ? 'project_ui_user' : 'composer',
          chat_id: chatIdOverride || chatId,
          run_id: runId,
          working_directory: app.projectRoot || undefined,
          project_root: app.projectRoot || undefined,
          provider: selected.provider || undefined,
          model: selected.model || undefined,
          execution_mode: requestMode === 'plan' ? 'plan' : undefined,
          planner_mode: requestMode === 'plan' ? 'always' : undefined,
          auto_approve_plan: requestMode === 'plan' ? false : undefined,
        }
    let resp
    try {
      resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
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
    let awaiting = false
    let failed = false

    es.addEventListener('activity', e => {
      try {
        const data = JSON.parse(e.data)
        onActivity?.({
          id: data.id || `activity-${Date.now()}`,
          title: data.title || data.kind || 'Activity',
          detail: data.detail || data.command || '',
          kind: data.kind || 'activity',
          status: data.status || 'running',
          command: data.command || '',
          cwd: data.cwd || '',
          actor: data.actor || '',
          durationLabel: data.duration_label || '',
          exitCode: data.exit_code,
        })
      } catch {}
    })

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
        awaiting = !!(
          d.awaiting_user_input
          || d.plan_waiting_for_approval
          || d.plan_needs_clarification
          || d.pending_user_input_kind
          || d.approval_pending_scope
          || d.pending_user_question
          || (d.approval_request && Object.keys(d.approval_request).length > 0)
        )
        if (awaiting) {
          onAwaiting?.({
            output: lastResult,
            checklist: extractChecklist(d),
            runId: d.run_id || effectiveId,
            workflowId: d.workflow_id || effectiveId,
            prompt: d.pending_user_question || lastResult || 'Waiting for your input.',
            kind: d.pending_user_input_kind || '',
            scope: d.approval_pending_scope || '',
            approvalRequest: d.approval_request || null,
          })
        } else {
          onResult?.(lastResult)
        }
      } catch {}
    })
    es.addEventListener('done', () => {
      if (failed) return
      es.close()
      onDone?.({ output: lastResult, awaiting })
    })
    es.addEventListener('error', e => {
      if (failed) return
      failed = true
      refreshModelInventory(true)
      try { const d = JSON.parse(e.data); onError?.(d.message || 'Run failed') } catch {}
      es.close()
    })
    es.onerror = () => {
      if (failed) return
      failed = true
      refreshModelInventory(true)
      onError?.('Run failed')
      es.close()
    }
  }, [apiBase, chatId, app.projectRoot, app.selectedModel, refreshModelInventory])

  const stopStream = () => esRef.current?.close()
  const openArtifact = useCallback(async (item) => {
    const filePath = String(item?.path || '').trim()
    if (!filePath) return
    await openFile(filePath)
  }, [openFile])
  const reviewArtifact = useCallback((item) => {
    const filePath = String(item?.path || '').trim()
    if (!filePath) return
    setDiffPreviewPath(filePath)
  }, [])

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
    } else if (mode === 'plan') {
      ctx =
        '[IDE plan mode]\n' +
        '- Inspect project context before acting.\n' +
        '- Produce a concise implementation plan first.\n' +
        '- Wait for approval before writing code.\n' +
        '- Keep the plan actionable and sequenced.\n\n' +
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
  const send = useCallback(async (textOverride = '', isResume = false) => {
    const text = String(textOverride || input).trim()
    if (!text || streaming) return
    setInput('')
    setMentionAnchor(null)
    const resumeMessageId = String(awaitingContext?.messageId || '').trim()
    const preserveInlineBubble = isResume && resumeMessageId && !isSkillApproval(awaitingContext?.kind, awaitingContext?.approvalRequest)
    const msgId = isResume && resumeMessageId && !preserveInlineBubble ? resumeMessageId : `a-${Date.now()}`
    setMessages((messages) => {
      let next = [...messages, { id: `u-${Date.now()}`, role: 'user', content: text }]
      if (preserveInlineBubble && resumeMessageId) {
        const normalizedReply = text.toLowerCase()
        const approvalState = normalizedReply === 'approve'
          ? 'approved'
          : normalizedReply === 'cancel'
            ? 'rejected'
            : 'suggested'
        next = next.map((message) => (
          message.id === resumeMessageId
            ? { ...message, status: 'done', approvalState }
            : message
        ))
      }
      if (isResume && resumeMessageId && !preserveInlineBubble) {
        next = next.map((message) => (
          message.id === msgId
            ? { ...message, content: '', steps: [], progress: [], checklist: [], status: 'thinking', approvalRequest: null, approvalScope: '', approvalKind: '' }
            : message
        ))
      } else {
        next.push({ id: msgId, role: 'assistant', content: '', steps: [], progress: [], checklist: [], status: 'thinking', mode, approvalRequest: null, approvalScope: '', approvalKind: '' })
      }
      return next
    })
    setStreaming(true)
    setAwaitingContext(null)
    try {
      await runSSE({
        text: isResume ? text : buildContextPrompt(text),
        requestMode: mode,
        resumeContext: isResume ? awaitingContext : null,
        onStep: (step) => setMessages(m => m.map(msg => {
          if (msg.id !== msgId) return msg
          const steps = [...(msg.steps || [])]
          const idx = steps.findIndex(s => s.stepId === step.stepId)
          if (idx >= 0) steps[idx] = step; else steps.push(step)
          return { ...msg, steps }
        })),
        onActivity: (item) => setMessages((messages) => messages.map((message) => {
          if (message.id !== msgId) return message
          const prev = Array.isArray(message.progress) ? message.progress : []
          return { ...message, progress: [item, ...prev].slice(0, 16) }
        })),
        onResult: (out) => setMessages(m => m.map(msg =>
          msg.id === msgId ? { ...msg, content: out, status: 'streaming' } : msg
        )),
        onAwaiting: (data) => {
          setAwaitingContext({ ...data, messageId: msgId })
          setMessages((messages) => messages.map((message) => (
            message.id === msgId
              ? {
                  ...message,
                  content: data.output,
                  checklist: data.checklist,
                  status: 'awaiting',
                  approvalRequest: data.approvalRequest || null,
                  approvalScope: data.scope || '',
                  approvalKind: data.kind || '',
                  approvalState: 'pending',
                }
              : message
          )))
        },
        onDone: ({ output, awaiting }) => {
          if (awaiting) {
            setStreaming(false)
            return
          }
          setMessages(m => m.map(msg =>
            msg.id === msgId ? { ...msg, content: output || msg.content, status: 'done' } : msg
          ))
          setStreaming(false)
        },
        onError: (err) => {
          setAwaitingContext(null)
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
  }, [input, streaming, runSSE, buildContextPrompt, mode, awaitingContext])

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
        onDone: ({ output }) => {
          setEditStreaming(false)
          setEditDiff({ original: codeToEdit, modified: extractCode(output || ''), lang })
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
      <GitDiffPreview
        cwd={app.projectRoot}
        filePath={diffPreviewPath}
        onClose={() => setDiffPreviewPath('')}
        onOpenFile={(filePath) => openArtifact({ path: filePath })}
      />

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
              {[['agent','Agent'],['plan','Plan'],['chat','Chat'],['edit','Edit']].map(([id, label]) => (
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
                onClick={() => { setMessages([]); setAttachedFiles([]); setAwaitingContext(null) }}>⊘</button>
            </div>
          </div>

          {/* ── Agent / Plan / Chat ── */}
          {(mode === 'agent' || mode === 'plan' || mode === 'chat') && (
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
                    <div className="ac-empty-icon">{mode === 'agent' ? '✨' : mode === 'plan' ? '🗺️' : '💬'}</div>
                    <div className="ac-empty-title">{mode === 'agent' ? 'Agent' : mode === 'plan' ? 'Plan' : 'Chat'}</div>
                    <div className="ac-empty-sub">
                      {mode === 'agent'
                        ? 'The agent works against the current project like an IDE coding assistant. It can inspect files, run tasks, and prepare code edits with project context.'
                        : mode === 'plan'
                          ? 'Plan mode inspects the project, proposes the work, and waits before implementation.'
                          : 'Ask questions about code, get explanations, or request suggestions.'}
                    </div>
                    {activeTab && (
                      <div className="ac-chips">
                        {((mode === 'agent'
                          ? ['Refactor this file', 'Find and fix bugs', 'Add TypeScript types', 'Write unit tests']
                          : mode === 'plan'
                            ? ['Plan a refactor for this file', 'Plan the bug fix work', 'Outline implementation steps', 'Break this task into milestones']
                            : ['Explain this code', 'What does this do?', 'How can I improve this?', 'Find potential issues'])
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
                        <ComposerActivityCards progress={msg.progress} artifacts={msg.artifacts} onOpenItem={openArtifact} onReviewItem={reviewArtifact} />
                        {msg.checklist?.length > 0 && (msg.mode === 'plan' || isPlanApprovalScope(msg.approvalScope, msg.approvalKind, msg.approvalRequest)) && (
                          <ComposerPlanCard
                            msg={msg}
                            onQuickReply={(reply) => send(reply, true)}
                            onSendSuggestion={(reply) => send(reply, true)}
                          />
                        )}
                        {msg.status === 'awaiting' && !isSkillApproval(msg.approvalKind, msg.approvalRequest) && !(msg.checklist?.length > 0 && (msg.mode === 'plan' || isPlanApprovalScope(msg.approvalScope, msg.approvalKind, msg.approvalRequest))) && (
                          <ComposerAwaitingCard
                            msg={msg}
                            onQuickReply={(reply) => send(reply, true)}
                            onSendSuggestion={(reply) => send(reply, true)}
                          />
                        )}
                        {msg.status === 'thinking' && !msg.steps?.length ? (
                          <div className="ac-thinking-row">
                            <span className="ac-thinking"><span /><span /><span /></span>
                            <span className="ac-thinking-label">Thinking…</span>
                          </div>
                        ) : msg.status === 'error' ? (
                          <div className="ac-error-msg">⚠ {msg.content}</div>
                        ) : msg.content && !(msg.status === 'awaiting' && !isSkillApproval(msg.approvalKind, msg.approvalRequest)) && !(msg.checklist?.length > 0 && (msg.mode === 'plan' || isPlanApprovalScope(msg.approvalScope, msg.approvalKind, msg.approvalRequest))) ? (
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
                    : mode === 'plan'
                      ? 'Ask for a plan first. Kendr will inspect the project and wait before changing code… (Ctrl+Enter)'
                      : 'Ask about code… (Ctrl+Enter to send)'}
                  value={input}
                  onChange={handleInputChange}
                  onKeyDown={handleKey}
                  rows={3}
                  disabled={streaming}
                />
                <div className="ac-input-footer">
                  <span className="ac-input-hint">Ctrl+Enter</span>
                  <div className="ac-flow-strip">
                    <span className={`ac-flow-chip ac-flow-chip--${mode}`}>{mode === 'plan' ? 'Plan first' : mode === 'agent' ? 'Project run' : 'Chat'}</span>
                    {activeTab && <span className="ac-flow-chip">{activeTab.name}</span>}
                  </div>
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

function ComposerActivityCards({ progress, artifacts, onOpenItem, onReviewItem }) {
  const cards = summarizeRunArtifacts(progress, artifacts)
  if (!cards.length) return null
  return (
    <div className="kc-activity-grid">
      {cards.map((card) => (
        <div key={`${card.kind}-${card.title}`} className={`kc-activity-card kc-activity-card--${card.kind}`}>
          <div className="kc-activity-card-head">
            <div>
              <div className="kc-activity-card-kind">{card.kind}</div>
              <div className="kc-activity-card-title">{card.title}</div>
            </div>
            {card.kind === 'edit' && Array.isArray(card.items) && card.items.some((item) => item?.path) && (
              <button className="kc-activity-card-action" onClick={() => onReviewItem?.(card.items.find((item) => item?.path))}>
                Review
              </button>
            )}
          </div>
          {Array.isArray(card.items) && card.items.length > 0 && (
            <div className="kc-activity-card-items">
              {card.items.slice(0, 3).map((item) => (
                item?.path ? (
                  <button key={`${item.path}-${item.label}`} className="kc-activity-card-item kc-activity-card-item--action" onClick={() => onOpenItem?.(item)}>
                    {item.label}
                  </button>
                ) : (
                  <span key={item.label} className="kc-activity-card-item">{item.label}</span>
                )
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function ComposerPlanCard({ msg, onQuickReply, onSendSuggestion }) {
  const [showSuggest, setShowSuggest] = useState(false)
  const [draft, setDraft] = useState('')
  const checklist = Array.isArray(msg.checklist) ? msg.checklist : []
  if (!checklist.length) return null
  const approvalRequest = (msg.approvalRequest && typeof msg.approvalRequest === 'object') ? msg.approvalRequest : {}
  const approvalActions = (approvalRequest.actions && typeof approvalRequest.actions === 'object') ? approvalRequest.actions : {}
  const awaiting = msg.status === 'awaiting'
  const summary = String(approvalRequest.summary || msg.content || '').trim()

  return (
    <div className="kc-plan-card">
      <div className="kc-plan-card-head">
        <div>
          <div className="kc-plan-card-label">{awaiting ? 'Plan Ready' : 'Plan'}</div>
          <div className="kc-plan-card-meta">{checklist.length} task{checklist.length === 1 ? '' : 's'}</div>
        </div>
      </div>
      {summary && <div className="kc-plan-card-summary">{summary}</div>}
      <div className="kc-plan-card-list">
        {checklist.map((item) => (
          <div key={`${item.step}-${item.title}`} className="kc-checklist-item">
            <div className="kc-checklist-mark">{item.done ? '✓' : item.status === 'running' ? '…' : '·'}</div>
            <div className="kc-checklist-body">
              <div className="kc-checklist-row">
                <span className="kc-checklist-step">{item.step}.</span>
                <span className="kc-checklist-text">{item.title}</span>
              </div>
              {item.detail && <div className="kc-checklist-detail">{item.detail}</div>}
            </div>
          </div>
        ))}
      </div>
      {awaiting && (
        <>
          <div className="kc-plan-card-actions">
            <button className="kc-plan-card-btn kc-plan-card-btn--approve" onClick={() => onQuickReply?.('approve')}>
              {approvalActions.accept_label || 'Implement'}
            </button>
            <button
              className={`kc-plan-card-btn kc-plan-card-btn--ghost${showSuggest ? ' kc-plan-card-btn--active' : ''}`}
              onClick={() => setShowSuggest((value) => !value)}
            >
              {approvalActions.suggest_label || 'Change Plan'}
            </button>
            <button className="kc-plan-card-btn kc-plan-card-btn--reject" onClick={() => onQuickReply?.('cancel')}>
              {approvalActions.reject_label || 'Reject'}
            </button>
          </div>
          {showSuggest && (
            <div className="kc-plan-card-suggest">
              <textarea
                className="kc-plan-card-input"
                rows={3}
                placeholder="Say what should change in the plan…"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
              <button
                className="kc-plan-card-btn kc-plan-card-btn--approve"
                disabled={!draft.trim()}
                onClick={() => {
                  if (!draft.trim()) return
                  onSendSuggestion?.(draft)
                  setDraft('')
                  setShowSuggest(false)
                }}
              >
                Send
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ComposerAwaitingCard({ msg, onQuickReply, onSendSuggestion }) {
  const [showSuggest, setShowSuggest] = useState(false)
  const [draft, setDraft] = useState('')
  const approvalRequest = (msg.approvalRequest && typeof msg.approvalRequest === 'object') ? msg.approvalRequest : {}
  const approvalActions = (approvalRequest.actions && typeof approvalRequest.actions === 'object') ? approvalRequest.actions : {}
  const title = approvalRequest.title || 'Waiting for input'
  const summary = String(approvalRequest.summary || msg.content || '').trim()
  const sections = Array.isArray(approvalRequest.sections) ? approvalRequest.sections : []
  const hasQuickActions = !!(approvalActions.accept_label || approvalActions.reject_label || approvalActions.suggest_label || msg.approvalScope)

  return (
    <div className="kc-inline-approval">
      <div className="kc-inline-approval-head">
        <div className="kc-inline-approval-title">{title}</div>
        <div className="kc-inline-approval-status">awaiting</div>
      </div>
      {summary && (
        <div className="kc-inline-approval-summary">
          <AcText text={summary} />
        </div>
      )}
      {sections.length > 0 && (
        <div className="kc-inline-approval-sections">
          {sections.map((section, index) => (
            <div key={`${section.title || 'section'}-${index}`} className="kc-inline-approval-section">
              {section.title && <div className="kc-inline-approval-section-title">{section.title}</div>}
              {Array.isArray(section.items) && section.items.length > 0 && (
                <ul className="kc-inline-approval-list">
                  {section.items.map((item, itemIndex) => (
                    <li key={`${index}-${itemIndex}`}>{item}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
      {approvalRequest.help_text && (
        <div className="kc-inline-approval-help">{approvalRequest.help_text}</div>
      )}
      {hasQuickActions ? (
        <>
          <div className="kc-inline-approval-actions">
            <button className="kc-plan-card-btn kc-plan-card-btn--approve" onClick={() => onQuickReply?.('approve')}>
              {approvalActions.accept_label || 'Approve'}
            </button>
            <button
              className={`kc-plan-card-btn kc-plan-card-btn--ghost${showSuggest ? ' kc-plan-card-btn--active' : ''}`}
              onClick={() => setShowSuggest((value) => !value)}
            >
              {approvalActions.suggest_label || 'Reply'}
            </button>
            <button className="kc-plan-card-btn kc-plan-card-btn--reject" onClick={() => onQuickReply?.('cancel')}>
              {approvalActions.reject_label || 'Reject'}
            </button>
          </div>
          {showSuggest && (
            <div className="kc-plan-card-suggest">
              <textarea
                className="kc-plan-card-input"
                rows={3}
                placeholder="Type your reply…"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
              <button
                className="kc-plan-card-btn kc-plan-card-btn--approve"
                disabled={!draft.trim()}
                onClick={() => {
                  if (!draft.trim()) return
                  onSendSuggestion?.(draft)
                  setDraft('')
                  setShowSuggest(false)
                }}
              >
                Send
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="kc-plan-card-suggest">
          <textarea
            className="kc-plan-card-input"
            rows={3}
            placeholder="Type your reply…"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <button
            className="kc-plan-card-btn kc-plan-card-btn--approve"
            disabled={!draft.trim()}
            onClick={() => {
              if (!draft.trim()) return
              onSendSuggestion?.(draft)
              setDraft('')
            }}
          >
            Send reply
          </button>
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
