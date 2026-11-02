/**
 * ChatInterface.jsx — The main Q&A chat panel.
 *
 * WHY THIS FILE EXISTS:
 *   This is the primary user-facing feature of the app. The user types a
 *   question, it is sent to the backend's /api/chat/ endpoint, and the AI
 *   answer is displayed in the conversation thread.
 *
 * STATE MANAGED HERE:
 *   messages    — The conversation history as an array of {role, text} objects.
 *                 Starts with a welcome message so the UI is never blank.
 *   input       — The current value of the text input box.
 *   loading     — True while waiting for the API response. Used to disable the
 *                 send button and show an animated "thinking" indicator.
 *   bottomRef   — A ref attached to an invisible div at the bottom of the
 *                 message list. We call scrollIntoView() on it whenever
 *                 messages changes so the view always scrolls to the newest
 *                 message automatically.
 *
 * WHY API_BASE FROM import.meta.env?
 *   During local development the frontend Vite dev server (port 5173) proxies
 *   /api/ calls to the Django backend (port 8000) via vite.config.js, so
 *   API_BASE can be an empty string. In production the variable can be set to
 *   the backend's public URL without any code changes.
 *
 * CHAT FLOW:
 *   1. User submits the form → handleSend() fires.
 *   2. The user's message is appended to the messages array immediately so
 *      the UI feels responsive (optimistic update).
 *   3. A POST request is sent to /api/chat/ with the question as JSON.
 *   4. On success the assistant's answer is appended to messages.
 *   5. On failure an error bubble is appended instead.
 */

import { useState, useRef, useEffect } from 'react'
import MessageBubble from './MessageBubble'

// Empty string means "same origin" — the Vite dev proxy handles /api/* routing.
// Set VITE_API_URL in .env to point at a different backend host in production.
const API_BASE = import.meta.env.VITE_API_URL || ''

export default function ChatInterface() {
  // Seed the conversation with a welcome message so the UI is never empty.
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Hello! Upload documents in the Documents tab, then ask me anything about them.',
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  // Invisible sentinel div at the bottom of the list; we scroll to it after
  // every new message so the latest message is always visible.
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(e) {
    e.preventDefault()
    const question = input.trim()
    // Guard: don't send empty questions or double-send while already loading.
    if (!question || loading) return

    // Show the user's message immediately for a responsive feel (optimistic UI).
    setMessages((prev) => [...prev, { role: 'user', text: question }])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/chat/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, use_query_transform: false }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Something went wrong')
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: data.answer,
          sources: data.sources_used,
          citations: data.citations || [],
          evaluation: data.evaluation || null,
        },
      ])
    } catch (err) {
      // Network errors or backend 500s are shown as a red error bubble.
      setMessages((prev) => [...prev, { role: 'error', text: err.message }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {loading && (
          <div className="message assistant">
            <div className="bubble loading">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSend}>
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your documents…"
          disabled={loading}
        />
        <button className="send-btn" type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>

      <style>{`
        .chat-container {
          display: flex;
          flex-direction: column;
          height: calc(100vh - 220px);
          background: white;
          border-radius: 12px;
          border: 1px solid #e5e7eb;
          overflow: hidden;
        }
        .messages {
          flex: 1;
          overflow-y: auto;
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .chat-input-form {
          display: flex;
          gap: 0.5rem;
          padding: 1rem;
          border-top: 1px solid #e5e7eb;
          background: #fafafa;
        }
        .chat-input {
          flex: 1;
          padding: 0.75rem 1rem;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          font-size: 0.95rem;
          outline: none;
          transition: border-color 0.2s;
        }
        .chat-input:focus { border-color: #3b82f6; }
        .send-btn {
          padding: 0.75rem 1.5rem;
          background: #3b82f6;
          color: white;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          font-size: 0.95rem;
          font-weight: 600;
          transition: background 0.2s;
        }
        .send-btn:hover:not(:disabled) { background: #2563eb; }
        .send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .bubble.loading {
          display: flex;
          gap: 4px;
          align-items: center;
          padding: 0.75rem 1rem;
          background: #f3f4f6;
          border-radius: 12px;
          border-bottom-left-radius: 4px;
        }
        .bubble.loading span {
          width: 8px; height: 8px;
          background: #9ca3af;
          border-radius: 50%;
          animation: blink 1.2s infinite;
        }
        .bubble.loading span:nth-child(2) { animation-delay: 0.2s; }
        .bubble.loading span:nth-child(3) { animation-delay: 0.4s; }
        @keyframes blink {
          0%, 80%, 100% { opacity: 0.3; }
          40% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}
