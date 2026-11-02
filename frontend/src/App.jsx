/**
 * App.jsx — Root component of the React frontend.
 *
 * WHY THIS FILE EXISTS:
 *   Every React app needs a single top-level component that owns the
 *   application-level state and decides what to render. This component:
 *     1. Holds the active tab so only one panel is shown at a time.
 *     2. Holds a "refresh key" that lets the Documents panel know when a new
 *        file has been uploaded from within that same panel, triggering a
 *        re-fetch of the document list.
 *
 * UI STRUCTURE:
 *   ┌──────────────────────────────────┐
 *   │  Header (title + subtitle)       │
 *   ├──────────────────────────────────┤
 *   │  Tab bar: [Chat] [Documents]     │
 *   ├──────────────────────────────────┤
 *   │  <ChatInterface />               │
 *   │      or                          │
 *   │  <DocumentUpload />              │
 *   └──────────────────────────────────┘
 *
 * WHY A REFRESH KEY INSTEAD OF LIFTING STATE?
 *   DocumentUpload manages its own document list. When an upload succeeds,
 *   the parent (this file) increments docRefreshKey. DocumentUpload watches
 *   refreshKey via useEffect and re-fetches the list. This pattern avoids
 *   prop-drilling the full document array through App while still allowing
 *   the parent to trigger a refresh signal.
 */

import { useState } from 'react'
import ChatInterface from './components/ChatInterface'
import DocumentUpload from './components/DocumentUpload'

export default function App() {
  const [activeTab, setActiveTab] = useState('chat')

  // Incrementing this number causes DocumentUpload to re-fetch the document
  // list. We use a counter (not a boolean) so every increment is a new value
  // and triggers the useEffect regardless of how quickly uploads happen.
  const [docRefreshKey, setDocRefreshKey] = useState(0)

  return (
    <div className="app">
      <header className="header">
        <h1>AI Document Assistant</h1>
        <p>Ask questions grounded in your uploaded documents</p>
      </header>

      <nav className="tabs">
        <button
          className={activeTab === 'chat' ? 'tab active' : 'tab'}
          onClick={() => setActiveTab('chat')}
        >
          Chat
        </button>
        <button
          className={activeTab === 'docs' ? 'tab active' : 'tab'}
          onClick={() => setActiveTab('docs')}
        >
          Documents
        </button>
      </nav>

      <main className="main">
        {activeTab === 'chat' ? (
          <ChatInterface />
        ) : (
          <DocumentUpload
            onUploadSuccess={() => setDocRefreshKey((k) => k + 1)}
            refreshKey={docRefreshKey}
          />
        )}
      </main>
    </div>
  )
}
