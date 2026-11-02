/**
 * MessageBubble.jsx — Renders a single chat message bubble.
 *
 * CITATIONS:
 *   When the backend returns a citations array each source is shown as a
 *   compact card below the answer — document name, page number, and a short
 *   excerpt.  The user can see exactly which passage in which document
 *   grounded each claim in the answer.
 *
 * EVALUATION BADGE:
 *   If evaluate=true was sent in the request the backend returns faithfulness
 *   and relevancy scores.  These are rendered as colour-coded chips so the
 *   user can judge answer quality at a glance.
 */

import { useState } from 'react'

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isError = message.role === 'error'
  const [showSources, setShowSources] = useState(false)

  const hasCitations = message.citations && message.citations.length > 0
  const hasEval = message.evaluation

  return (
    <div className={`message ${message.role}`}>
      <div className={`bubble ${isError ? 'error' : isUser ? 'user' : 'assistant'}`}>
        <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{message.text}</p>

        {/* Evaluation scores */}
        {hasEval && (
          <div className="eval-row">
            <EvalChip label="Faithful" value={hasEval.faithfulness} />
            <EvalChip label="Relevant" value={hasEval.answer_relevancy} />
            <EvalChip label="Context" value={hasEval.context_relevancy} />
          </div>
        )}

        {/* Citations toggle */}
        {hasCitations && (
          <button
            className="sources-badge"
            onClick={() => setShowSources((s) => !s)}
          >
            {message.citations.length} source{message.citations.length !== 1 ? 's' : ''}
            {' '}{showSources ? '▲' : '▼'}
          </button>
        )}

        {/* Expanded citation cards */}
        {showSources && hasCitations && (
          <div className="citations">
            {message.citations.map((c) => (
              <div key={c.index} className="citation-card">
                <span className="citation-num">[{c.index}]</span>
                <span className="citation-doc">{c.document_name}</span>
                {c.page_number && (
                  <span className="citation-page">p. {c.page_number}</span>
                )}
                <p className="citation-excerpt">{c.excerpt}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        .message { display: flex; margin-bottom: 0.5rem; }
        .message.user { justify-content: flex-end; }
        .message.assistant, .message.error { justify-content: flex-start; }
        .bubble {
          max-width: 75%;
          padding: 0.75rem 1rem;
          border-radius: 12px;
          font-size: 0.95rem;
          line-height: 1.5;
        }
        .bubble.user {
          background: #3b82f6;
          color: white;
          border-bottom-right-radius: 4px;
        }
        .bubble.assistant {
          background: #f3f4f6;
          color: #1a1a2e;
          border-bottom-left-radius: 4px;
        }
        .bubble.error {
          background: #fef2f2;
          color: #dc2626;
          border: 1px solid #fecaca;
          border-bottom-left-radius: 4px;
        }
        .sources-badge {
          display: inline-block;
          margin-top: 0.5rem;
          font-size: 0.75rem;
          color: #6b7280;
          background: white;
          padding: 0.15rem 0.5rem;
          border-radius: 99px;
          border: 1px solid #e5e7eb;
          cursor: pointer;
        }
        .citations { margin-top: 0.5rem; display: flex; flex-direction: column; gap: 0.4rem; }
        .citation-card {
          background: white;
          border: 1px solid #e5e7eb;
          border-radius: 8px;
          padding: 0.5rem 0.75rem;
          font-size: 0.8rem;
        }
        .citation-num { font-weight: 700; color: #3b82f6; margin-right: 0.4rem; }
        .citation-doc { font-weight: 600; color: #374151; }
        .citation-page { color: #9ca3af; margin-left: 0.4rem; font-size: 0.75rem; }
        .citation-excerpt { color: #6b7280; margin: 0.3rem 0 0; font-style: italic; }
        .eval-row { display: flex; gap: 0.4rem; margin-top: 0.5rem; flex-wrap: wrap; }
        .eval-chip {
          font-size: 0.7rem;
          padding: 0.1rem 0.5rem;
          border-radius: 99px;
          font-weight: 600;
        }
        .eval-chip.high { background: #dcfce7; color: #166534; }
        .eval-chip.mid  { background: #fef9c3; color: #854d0e; }
        .eval-chip.low  { background: #fee2e2; color: #991b1b; }
      `}</style>
    </div>
  )
}

function EvalChip({ label, value }) {
  if (value < 0) return null  // evaluation failed
  const cls = value >= 0.7 ? 'high' : value >= 0.4 ? 'mid' : 'low'
  return (
    <span className={`eval-chip ${cls}`}>
      {label}: {(value * 100).toFixed(0)}%
    </span>
  )
}

