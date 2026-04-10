import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useApp } from '../contexts/AppContext'

const FILE_ICONS = {
  js: '⚡', jsx: '⚛', ts: '🔷', tsx: '⚛', py: '🐍', json: '{}',
  md: '📝', html: '🌐', css: '🎨', yml: '⚙', yaml: '⚙', sh: '💻',
  rs: '⚙', go: '🐹', java: '☕', sql: '🗄', txt: '📄', env: '🔐',
  toml: '⚙', xml: '📋', png: '🖼', jpg: '🖼', svg: '🖼', pdf: '📑',
  zip: '📦', lock: '🔒', gitignore: '⊘'
}

function TreeNode({ node, depth = 0, onContextMenu }) {
  const [open, setOpen] = useState(depth < 2)
  const [children, setChildren] = useState(null)
  const { openFile } = useApp()
  const api = window.kendrAPI

  const loadChildren = useCallback(async () => {
    if (!node.isDirectory) return
    const entries = await api?.fs.readDir(node.path)
    if (Array.isArray(entries)) setChildren(entries)
  }, [node])

  useEffect(() => {
    if (open && node.isDirectory && children === null) loadChildren()
  }, [open, node.isDirectory])

  const toggle = () => {
    if (node.isDirectory) setOpen(o => !o)
    else openFile(node.path)
  }

  const ext = node.name.split('.').pop()?.toLowerCase() || ''
  const icon = node.isDirectory ? (open ? '📂' : '📁') : (FILE_ICONS[ext] || '📄')

  return (
    <div>
      <div
        className="tree-node"
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={toggle}
        onContextMenu={e => onContextMenu(e, node)}
        title={node.path}
      >
        <span className="tree-icon">{icon}</span>
        <span className="tree-name">{node.name}</span>
      </div>
      {node.isDirectory && open && children && (
        <div>
          {children.map(child => (
            <TreeNode key={child.path} node={child} depth={depth + 1} onContextMenu={onContextMenu} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function FileExplorer() {
  const { state, dispatch } = useApp()
  const [rootEntries, setRootEntries] = useState([])
  const [contextMenu, setContextMenu] = useState(null)
  const [renaming, setRenaming] = useState(null)
  const [newFileName, setNewFileName] = useState('')
  const api = window.kendrAPI

  const loadRoot = useCallback(async () => {
    if (!state.projectRoot) return
    const entries = await api?.fs.readDir(state.projectRoot)
    if (Array.isArray(entries)) setRootEntries(entries)
  }, [state.projectRoot])

  useEffect(() => { loadRoot() }, [state.projectRoot])

  const openFolder = async () => {
    const dir = await api?.dialog.openDirectory()
    if (dir) {
      dispatch({ type: 'SET_PROJECT_ROOT', root: dir })
      await api?.settings.set('projectRoot', dir)
    }
  }

  const handleContextMenu = (e, node) => {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, node })
  }

  const closeCtx = () => setContextMenu(null)

  const ctxAction = async (action) => {
    const node = contextMenu?.node
    closeCtx()
    if (!node) return

    if (action === 'open' && !node.isDirectory) {
      const { openFile } = useApp()
    }
    if (action === 'rename') {
      setRenaming(node)
      setNewFileName(node.name)
    }
    if (action === 'delete') {
      if (confirm(`Delete "${node.name}"?`)) {
        await api?.fs.delete(node.path)
        loadRoot()
      }
    }
    if (action === 'new-file') {
      const name = prompt('File name:')
      if (name) {
        const newPath = `${node.isDirectory ? node.path : node.path.split(/[\\/]/).slice(0, -1).join('/')}/${name}`
        await api?.fs.createFile(newPath.replace(/\//g, require ? '\\' : '/'))
        loadRoot()
      }
    }
    if (action === 'new-folder') {
      const name = prompt('Folder name:')
      if (name) {
        const base = node.isDirectory ? node.path : node.path.split(/[\\/]/).slice(0, -1).join('\\')
        await api?.fs.createDir(`${base}\\${name}`)
        loadRoot()
      }
    }
  }

  const confirmRename = async () => {
    if (!renaming || !newFileName.trim()) { setRenaming(null); return }
    const dir = renaming.path.split(/[\\/]/).slice(0, -1).join('\\')
    const newPath = `${dir}\\${newFileName.trim()}`
    await api?.fs.rename(renaming.path, newPath)
    setRenaming(null)
    loadRoot()
  }

  return (
    <div className="file-explorer" onClick={() => contextMenu && closeCtx()}>
      {/* Toolbar */}
      <div className="explorer-toolbar">
        <button className="icon-btn" title="Open folder" onClick={openFolder}>
          <FolderOpenIcon />
        </button>
        <button className="icon-btn" title="Refresh" onClick={loadRoot}>
          <RefreshIcon />
        </button>
        {state.projectRoot && (
          <span className="explorer-root-name" title={state.projectRoot}>
            {state.projectRoot.split(/[\\/]/).pop()}
          </span>
        )}
      </div>

      {!state.projectRoot ? (
        <div className="explorer-empty">
          <button className="btn-primary" onClick={openFolder}>Open Folder</button>
          <p>Select a folder to start exploring</p>
        </div>
      ) : (
        <div className="tree-root">
          {rootEntries.map(entry => (
            <TreeNode key={entry.path} node={entry} depth={0} onContextMenu={handleContextMenu} />
          ))}
        </div>
      )}

      {/* Rename input */}
      {renaming && (
        <div className="rename-overlay">
          <input
            autoFocus
            className="rename-input"
            value={newFileName}
            onChange={e => setNewFileName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') confirmRename(); if (e.key === 'Escape') setRenaming(null) }}
            onBlur={confirmRename}
          />
        </div>
      )}

      {/* Context menu */}
      {contextMenu && (
        <div
          className="context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={e => e.stopPropagation()}
        >
          {!contextMenu.node.isDirectory && <div className="ctx-item" onClick={() => ctxAction('open')}>Open</div>}
          <div className="ctx-item" onClick={() => ctxAction('new-file')}>New File</div>
          <div className="ctx-item" onClick={() => ctxAction('new-folder')}>New Folder</div>
          <div className="ctx-divider" />
          <div className="ctx-item" onClick={() => ctxAction('rename')}>Rename</div>
          <div className="ctx-item ctx-item--danger" onClick={() => ctxAction('delete')}>Delete</div>
        </div>
      )}
    </div>
  )
}

function FolderOpenIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
}
function RefreshIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
}
