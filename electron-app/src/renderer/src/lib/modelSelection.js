export function resolveSelectedModel(selectedModel) {
  const raw = String(selectedModel || '').trim()
  if (!raw) {
    return { raw: '', provider: '', model: '', isLocal: false, label: 'Auto' }
  }

  const slash = raw.indexOf('/')
  if (slash === -1) {
    return {
      raw,
      provider: '',
      model: raw,
      isLocal: false,
      label: raw,
    }
  }

  const provider = raw.slice(0, slash).trim().toLowerCase()
  const model = raw.slice(slash + 1).trim()
  const providerLabel = provider === 'ollama'
    ? 'Local'
    : provider
      ? provider.charAt(0).toUpperCase() + provider.slice(1)
      : 'Model'

  return {
    raw,
    provider,
    model,
    isLocal: provider === 'ollama',
    label: `${providerLabel} · ${model || 'default'}`,
  }
}

export function basename(path) {
  return String(path || '').split(/[\\/]/).pop() || ''
}
