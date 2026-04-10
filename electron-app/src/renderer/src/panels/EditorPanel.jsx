import React, { useCallback, useRef } from 'react'
import Editor from '@monaco-editor/react'
import { useApp } from '../contexts/AppContext'

export default function EditorPanel({ onEditorMount } = {}) {
  const { state, dispatch } = useApp()
  const editorRef = useRef(null)

  const activeTab = state.openTabs.find(t => t.path === state.activeTabPath)

  const handleMount = useCallback((editor) => {
    editorRef.current = editor
    // Expose editor instance to parent (ProjectWorkspace → AIComposer)
    onEditorMount?.(editor)

    // Track selection for AI Composer context
    editor.onDidChangeCursorSelection((e) => {
      const model = editor.getModel()
      if (!model) return
      const sel = e.selection
      const text = model.getValueInRange(sel)
      dispatch({
        type: 'SET_EDITOR_SELECTION',
        selection: text.trim() ? {
          path: activeTab?.path,
          text,
          startLine: sel.startLineNumber,
          startCol:  sel.startColumn,
          endLine:   sel.endLineNumber,
          endCol:    sel.endColumn,
        } : null
      })
    })

    // Add save keybinding
    editor.addCommand(
      // Ctrl+S / Cmd+S
      2048 + 49, // monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS
      () => saveFile(editor.getValue())
    )

    // Ctrl+K → focus AI composer in edit mode (custom event)
    editor.addCommand(
      2048 + 41, // CtrlCmd + K
      () => {
        const pos = editor.getPosition()
        const sel = editor.getSelection()
        const model = editor.getModel()
        const selectedText = model ? model.getValueInRange(sel) : ''
        // Estimate screen Y offset from line number and scroll position
        const lineHeight = 22
        const scrollTop = editor.getScrollTop()
        const top = pos ? Math.max(10, (pos.lineNumber - 1) * lineHeight - scrollTop + lineHeight) : 80
        window.dispatchEvent(new CustomEvent('kendr:inline-edit', {
          detail: { top, path: activeTab?.path, selectedText: selectedText.trim() }
        }))
      }
    )
  }, [activeTab?.path, onEditorMount])

  const saveFile = useCallback(async (content) => {
    if (!activeTab) return
    const api = window.kendrAPI
    if (!api) return
    const result = await api.fs.writeFile(activeTab.path, content)
    if (result.ok) {
      dispatch({ type: 'MARK_TAB_MODIFIED', path: activeTab.path, modified: false })
    }
  }, [activeTab, dispatch])

  const handleChange = useCallback((value) => {
    if (!activeTab) return
    dispatch({ type: 'MARK_TAB_MODIFIED', path: activeTab.path, modified: true })
    // Update tab content in state so switching back restores it
    const tabs = (window.__tabContents = window.__tabContents || {})
    tabs[activeTab.path] = value
  }, [activeTab, dispatch])

  if (!activeTab) return null

  const savedContent = window.__tabContents?.[activeTab.path] ?? activeTab.content ?? ''

  return (
    <div className="editor-panel">
      <div className="editor-breadcrumb">
        {activeTab.path.split(/[\\/]/).map((part, i, arr) => (
          <React.Fragment key={i}>
            <span className={i === arr.length - 1 ? 'breadcrumb-file' : 'breadcrumb-dir'}>
              {part}
            </span>
            {i < arr.length - 1 && <span className="breadcrumb-sep">/</span>}
          </React.Fragment>
        ))}
        {activeTab.modified && <span className="breadcrumb-modified">●</span>}
      </div>

      <Editor
        height="100%"
        language={activeTab.language || 'plaintext'}
        value={savedContent}
        theme="vs-dark"
        onMount={handleMount}
        onChange={handleChange}
        options={{
          fontSize: 14,
          fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace",
          fontLigatures: true,
          lineHeight: 22,
          minimap: { enabled: true, scale: 1 },
          scrollBeyondLastLine: false,
          renderWhitespace: 'selection',
          bracketPairColorization: { enabled: true },
          smoothScrolling: true,
          cursorBlinking: 'smooth',
          cursorSmoothCaretAnimation: 'on',
          padding: { top: 10, bottom: 10 },
          wordWrap: 'off',
          tabSize: 2,
          insertSpaces: true,
          renderLineHighlight: 'all',
          scrollbar: {
            verticalScrollbarSize: 8,
            horizontalScrollbarSize: 8
          },
          overviewRulerBorder: false,
          hideCursorInOverviewRuler: true,
          glyphMargin: false,
          folding: true,
          lineNumbersMinChars: 3
        }}
      />
    </div>
  )
}
