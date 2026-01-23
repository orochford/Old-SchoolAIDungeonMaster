import { useState, useEffect } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import { Sword, Users, Map, BookOpen, Home, ScrollText, Settings, Eye, EyeOff } from 'lucide-react'

const navItems = [
  { path: '/', label: 'Home', icon: Home },
  { path: '/characters', label: 'Characters', icon: Users },
  { path: '/campaigns', label: 'Campaigns', icon: Map },
  { path: '/journal', label: 'Journal', icon: ScrollText },
  { path: '/sourcebooks', label: 'Sourcebooks', icon: BookOpen },
]

export function Layout() {
  const location = useLocation()
  const [showSettings, setShowSettings] = useState(false)

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-dungeon-800 border-b border-dungeon-600">
        <div className="container mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <Link to="/" className="flex items-center space-x-2">
              <Sword className="w-8 h-8 text-parchment-500" />
              <span className="font-display text-2xl text-parchment-100">
                Old-School Dungeon Master
              </span>
            </Link>

            <div className="flex items-center space-x-2">
              <nav className="flex space-x-1">
                {navItems.map((item) => {
                  const Icon = item.icon
                  const isActive = location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`flex items-center space-x-2 px-4 py-2 rounded transition-colors ${
                        isActive
                          ? 'bg-parchment-600 text-dungeon-900'
                          : 'text-parchment-300 hover:bg-dungeon-700 hover:text-parchment-100'
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                      <span>{item.label}</span>
                    </Link>
                  )
                })}
              </nav>
              <button
                onClick={() => setShowSettings(true)}
                className="p-2 text-parchment-400 hover:text-parchment-100 hover:bg-dungeon-700 rounded transition-colors"
                title="Settings"
              >
                <Settings className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 container mx-auto px-4 py-6">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-dungeon-800 border-t border-dungeon-600 py-4">
        <div className="container mx-auto px-4 text-center text-parchment-400 text-sm">
          OSR Classic Solo Adventures Platform
        </div>
      </footer>

      {/* Settings Modal */}
      {showSettings && (
        <SettingsModal onClose={() => setShowSettings(false)} />
      )}
    </div>
  )
}

const CLAUDE_MODELS = [
  { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4' },
  { id: 'claude-sonnet-4-5-20250514', name: 'Claude Sonnet 4.5' },
  { id: 'claude-opus-4-5-20251101', name: 'Claude Opus 4.5' },
  { id: 'claude-haiku-4-5-20250101', name: 'Claude Haiku 4.5 (Fast)' },
]

const OPENAI_MODELS = [
  { id: 'gpt-5.2', name: 'GPT-5.2 (Flagship)' },
  { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
  { id: 'gpt-5-nano', name: 'GPT-5 Nano (Fast)' },
  { id: 'gpt-4.1', name: 'GPT-4.1' },
  { id: 'gpt-4.1-mini', name: 'GPT-4.1 Mini' },
  { id: 'gpt-4o-mini', name: 'GPT-4o Mini (Legacy)' },
]

function SettingsModal({ onClose }: { onClose: () => void }) {
  const [openaiKey, setOpenaiKey] = useState('')
  const [claudeKey, setClaudeKey] = useState('')
  const [showOpenai, setShowOpenai] = useState(false)
  const [showClaude, setShowClaude] = useState(false)
  const [saved, setSaved] = useState(false)
  const [openaiTest, setOpenaiTest] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')
  const [claudeTest, setClaudeTest] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')
  const [testError, setTestError] = useState('')

  // GM AI settings
  const [gmProvider, setGmProvider] = useState<'claude' | 'openai'>('claude')
  const [gmClaudeModel, setGmClaudeModel] = useState('claude-sonnet-4-20250514')
  const [gmOpenaiModel, setGmOpenaiModel] = useState('gpt-4o-mini')

  // Processing AI settings
  const [processingProvider, setProcessingProvider] = useState<'openai' | 'claude'>('openai')
  const [processingClaudeModel, setProcessingClaudeModel] = useState('claude-haiku-4-5-20250101')
  const [processingOpenaiModel, setProcessingOpenaiModel] = useState('gpt-4o-mini')

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  useEffect(() => {
    // Load existing settings from localStorage
    setOpenaiKey(localStorage.getItem('openai_api_key') || '')
    setClaudeKey(localStorage.getItem('claude_api_key') || '')

    // GM settings
    setGmProvider((localStorage.getItem('gm_provider') as 'claude' | 'openai') || 'claude')
    setGmClaudeModel(localStorage.getItem('gm_claude_model') || 'claude-sonnet-4-20250514')
    setGmOpenaiModel(localStorage.getItem('gm_openai_model') || 'gpt-4o-mini')

    // Processing settings
    setProcessingProvider((localStorage.getItem('processing_provider') as 'openai' | 'claude') || 'openai')
    setProcessingClaudeModel(localStorage.getItem('processing_claude_model') || 'claude-haiku-4-5-20250101')
    setProcessingOpenaiModel(localStorage.getItem('processing_openai_model') || 'gpt-4o-mini')
  }, [])

  // Save settings to localStorage and backend (used by test functions)
  const saveSettings = async () => {
    // Save to localStorage
    if (openaiKey) {
      localStorage.setItem('openai_api_key', openaiKey)
    } else {
      localStorage.removeItem('openai_api_key')
    }
    if (claudeKey) {
      localStorage.setItem('claude_api_key', claudeKey)
    } else {
      localStorage.removeItem('claude_api_key')
    }

    // GM settings
    localStorage.setItem('gm_provider', gmProvider)
    localStorage.setItem('gm_claude_model', gmClaudeModel)
    localStorage.setItem('gm_openai_model', gmOpenaiModel)

    // Processing settings
    localStorage.setItem('processing_provider', processingProvider)
    localStorage.setItem('processing_claude_model', processingClaudeModel)
    localStorage.setItem('processing_openai_model', processingOpenaiModel)

    // Send to backend and wait for response
    try {
      await fetch(`${apiUrl}/api/v1/settings/keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          openai_api_key: openaiKey || null,
          claude_api_key: claudeKey || null,
          gm_provider: gmProvider,
          gm_claude_model: gmClaudeModel,
          gm_openai_model: gmOpenaiModel,
          processing_provider: processingProvider,
          processing_claude_model: processingClaudeModel,
          processing_openai_model: processingOpenaiModel,
        }),
      })
    } catch (e) {
      console.error('Failed to save settings to backend:', e)
    }
  }

  // Save and close modal
  const handleSave = () => {
    saveSettings() // Fire and forget
    onClose()
  }

  const testOpenai = async () => {
    setOpenaiTest('testing')
    setTestError('')
    // Save first so backend has the key
    await saveSettings()
    try {
      const res = await fetch(`${apiUrl}/api/v1/settings/test-openai`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setOpenaiTest('success')
      } else {
        setOpenaiTest('error')
        setTestError(data.error || 'Test failed')
      }
    } catch (e) {
      setOpenaiTest('error')
      setTestError('Connection failed')
    }
    setTimeout(() => setOpenaiTest('idle'), 3000)
  }

  const testClaude = async () => {
    setClaudeTest('testing')
    setTestError('')
    // Save first so backend has the key
    await saveSettings()
    try {
      const res = await fetch(`${apiUrl}/api/v1/settings/test-claude`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setClaudeTest('success')
      } else {
        setClaudeTest('error')
        setTestError(data.error || 'Test failed')
      }
    } catch (e) {
      setClaudeTest('error')
      setTestError('Connection failed')
    }
    setTimeout(() => setClaudeTest('idle'), 3000)
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-dungeon-800 border border-dungeon-600 rounded-lg p-6 w-full max-w-md shadow-xl">
        <h2 className="font-display text-2xl text-parchment-100 mb-4">Settings</h2>

        <div className="space-y-4">
          {/* OpenAI Key */}
          <div>
            <label className="block text-parchment-300 text-sm mb-1">OpenAI API Key</label>
            <p className="text-parchment-500 text-xs mb-2">Used for embeddings and PDF processing</p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showOpenai ? 'text' : 'password'}
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full bg-dungeon-900 border border-dungeon-600 text-parchment-200 rounded px-3 py-2 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowOpenai(!showOpenai)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-parchment-500 hover:text-parchment-300"
                >
                  {showOpenai ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                onClick={testOpenai}
                disabled={!openaiKey || openaiTest === 'testing'}
                className={`px-3 py-2 rounded text-sm transition-colors ${
                  openaiTest === 'success' ? 'bg-green-700 text-white' :
                  openaiTest === 'error' ? 'bg-red-700 text-white' :
                  'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                } disabled:opacity-50`}
              >
                {openaiTest === 'testing' ? '...' : openaiTest === 'success' ? 'OK' : openaiTest === 'error' ? 'Fail' : 'Test'}
              </button>
            </div>
          </div>

          {/* Claude Key */}
          <div>
            <label className="block text-parchment-300 text-sm mb-1">Anthropic API Key</label>
            <p className="text-parchment-500 text-xs mb-2">Used for AI Dungeon Master and adventure parsing</p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={showClaude ? 'text' : 'password'}
                  value={claudeKey}
                  onChange={(e) => setClaudeKey(e.target.value)}
                  placeholder="sk-ant-..."
                  className="w-full bg-dungeon-900 border border-dungeon-600 text-parchment-200 rounded px-3 py-2 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowClaude(!showClaude)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-parchment-500 hover:text-parchment-300"
                >
                  {showClaude ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <button
                onClick={testClaude}
                disabled={!claudeKey || claudeTest === 'testing'}
                className={`px-3 py-2 rounded text-sm transition-colors ${
                  claudeTest === 'success' ? 'bg-green-700 text-white' :
                  claudeTest === 'error' ? 'bg-red-700 text-white' :
                  'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                } disabled:opacity-50`}
              >
                {claudeTest === 'testing' ? '...' : claudeTest === 'success' ? 'OK' : claudeTest === 'error' ? 'Fail' : 'Test'}
              </button>
            </div>
          </div>

          {testError && (
            <p className="text-red-400 text-xs">{testError}</p>
          )}

          {/* Divider */}
          <div className="border-t border-dungeon-600 my-4" />

          {/* Game Master AI Section */}
          <div className="space-y-3">
            <h3 className="text-parchment-200 font-medium">Game Master AI</h3>
            <p className="text-parchment-500 text-xs">Used during gameplay sessions</p>

            {/* GM Provider Selection */}
            <div className="flex gap-2">
              <button
                onClick={() => setGmProvider('claude')}
                className={`flex-1 px-3 py-2 rounded text-sm transition-colors ${
                  gmProvider === 'claude'
                    ? 'bg-purple-700 text-white'
                    : 'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                }`}
              >
                Claude
              </button>
              <button
                onClick={() => setGmProvider('openai')}
                className={`flex-1 px-3 py-2 rounded text-sm transition-colors ${
                  gmProvider === 'openai'
                    ? 'bg-green-700 text-white'
                    : 'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                }`}
              >
                OpenAI
              </button>
            </div>

            {/* GM Model Selection */}
            <select
              value={gmProvider === 'claude' ? gmClaudeModel : gmOpenaiModel}
              onChange={(e) => gmProvider === 'claude' ? setGmClaudeModel(e.target.value) : setGmOpenaiModel(e.target.value)}
              className="w-full bg-dungeon-900 border border-dungeon-600 text-parchment-200 rounded px-3 py-2"
            >
              {(gmProvider === 'claude' ? CLAUDE_MODELS : OPENAI_MODELS).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>

          {/* Divider */}
          <div className="border-t border-dungeon-600 my-4" />

          {/* Sourcebook Processing AI Section */}
          <div className="space-y-3">
            <h3 className="text-parchment-200 font-medium">Sourcebook Processing AI</h3>
            <p className="text-parchment-500 text-xs">Used for parsing adventures and generating descriptions</p>

            {/* Processing Provider Selection */}
            <div className="flex gap-2">
              <button
                onClick={() => setProcessingProvider('claude')}
                className={`flex-1 px-3 py-2 rounded text-sm transition-colors ${
                  processingProvider === 'claude'
                    ? 'bg-purple-700 text-white'
                    : 'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                }`}
              >
                Claude
              </button>
              <button
                onClick={() => setProcessingProvider('openai')}
                className={`flex-1 px-3 py-2 rounded text-sm transition-colors ${
                  processingProvider === 'openai'
                    ? 'bg-green-700 text-white'
                    : 'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                }`}
              >
                OpenAI
              </button>
            </div>

            {/* Processing Model Selection */}
            <select
              value={processingProvider === 'claude' ? processingClaudeModel : processingOpenaiModel}
              onChange={(e) => processingProvider === 'claude' ? setProcessingClaudeModel(e.target.value) : setProcessingOpenaiModel(e.target.value)}
              className="w-full bg-dungeon-900 border border-dungeon-600 text-parchment-200 rounded px-3 py-2"
            >
              {(processingProvider === 'claude' ? CLAUDE_MODELS : OPENAI_MODELS).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          {saved && <span className="text-green-400 text-sm self-center mr-2">Saved!</span>}
          <button
            onClick={onClose}
            className="px-4 py-2 text-parchment-300 hover:text-parchment-100 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-purple-700 hover:bg-purple-600 text-white rounded transition-colors"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
