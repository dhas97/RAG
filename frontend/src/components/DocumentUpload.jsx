/**
 * DocumentUpload.jsx — Panel for uploading, listing, and deleting documents.
 *
 * WHY THIS FILE EXISTS:
 *   The RAG assistant is only useful when it has documents to reason about.
 *   This panel gives the user a way to manage those documents:
 *     - Upload a new PDF or TXT file (drag-and-drop or file picker).
 *     - See which files have already been uploaded and how many chunks each
 *       produced (a proxy for how much text was indexed).
 *     - Delete a document when it is no longer needed.
 *
 * PROPS:
 *   onUploadSuccess  — Callback fired after a successful upload so the parent
 *                      (App.jsx) can increment docRefreshKey if needed.
 *   refreshKey       — A number that increments whenever a new upload is
 *                      confirmed. This component watches it via useEffect and
 *                      re-fetches the document list when it changes.
 *
 * UPLOAD FLOW:
 *   1. User drops a file on the drop zone or picks one via the file input.
 *   2. uploadFile() creates a FormData object (required for multipart upload)
 *      and POSTs it to /api/documents/upload/.
 *   3. The backend extracts text, generates embeddings, and saves everything.
 *      This can take several seconds for large PDFs.
 *   4. On success, the document list is re-fetched and onUploadSuccess() is
 *      called so the parent knows to update the refreshKey.
 *
 * WHY SILENT CATCH IN fetchDocuments?
 *   On first page load the backend container might still be starting up.
 *   Silently ignoring the error means the user sees an empty list rather than
 *   a scary error message — they can try uploading and the list will populate
 *   as soon as the backend is ready.
 *
 * WHY CLEAR THE FILE INPUT AFTER SELECTION?
 *   Without resetting e.target.value, selecting the same file a second time
 *   won't trigger the onChange event because the browser considers the value
 *   unchanged. Clearing it ensures every selection triggers an upload.
 */

import { useState, useEffect, useRef } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function DocumentUpload({ onUploadSuccess, refreshKey }) {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(null) // {name, done, total}
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const pollRef = useRef(null)

  useEffect(() => {
    fetchDocuments()
  }, [refreshKey])

  async function fetchDocuments() {
    try {
      const res = await fetch(`${API_BASE}/api/documents/`)
      if (res.ok) {
        const data = await res.json()
        setDocuments(data)
      }
    } catch {
      // Silently ignore — backend may not be ready yet on first load.
    }
  }

  async function uploadFile(file) {
    setError('')
    setUploading(true)
    setUploadProgress({ name: file.name, done: 0, total: 0 })
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch(`${API_BASE}/api/documents/upload/`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Upload failed')

      // Start polling for progress — backend returns 202 immediately
      pollStatus(data.id, file.name)
    } catch (err) {
      setError(err.message)
      setUploading(false)
      setUploadProgress(null)
    }
  }

  function pollStatus(docId, fileName) {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/documents/${docId}/status/`)
        if (!res.ok) return
        const data = await res.json()
        setUploadProgress({ name: fileName, done: data.chunks_done, total: data.chunks_total })

        if (data.status === 'done') {
          clearInterval(pollRef.current)
          setUploading(false)
          setUploadProgress(null)
          await fetchDocuments()
          onUploadSuccess?.()
        } else if (data.status === 'failed') {
          clearInterval(pollRef.current)
          setUploading(false)
          setUploadProgress(null)
          setError(data.error_message || 'Ingestion failed')
        }
      } catch {
        // network hiccup — keep polling
      }
    }, 2000)
  }

  function handleFileInput(e) {
    const file = e.target.files[0]
    if (file) uploadFile(file)
    // Reset so re-selecting the same file still triggers onChange next time.
    e.target.value = ''
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }

  async function handleDelete(id) {
    try {
      await fetch(`${API_BASE}/api/documents/${id}/`, { method: 'DELETE' })
      // Remove from local state immediately so the UI updates without a refetch.
      setDocuments((prev) => prev.filter((d) => d.id !== id))
    } catch {
      setError('Failed to delete document')
    }
  }

  return (
    <div className="docs-container">
      <div
        className={`drop-zone ${dragOver ? 'drag-over' : ''} ${uploading ? 'uploading' : ''}`}
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
      >
      {uploading ? (
          <div style={{ width: '100%' }}>
            <p style={{ marginBottom: '0.5rem' }}>
              Processing <strong>{uploadProgress?.name}</strong>…
            </p>
            {uploadProgress?.total > 0 ? (
              <>
                <div className="progress-bar-bg">
                  <div
                    className="progress-bar-fill"
                    style={{ width: `${Math.round((uploadProgress.done / uploadProgress.total) * 100)}%` }}
                  />
                </div>
                <p style={{ fontSize: '0.8rem', color: '#6b7280', marginTop: '0.35rem' }}>
                  {uploadProgress.done} / {uploadProgress.total} chunks embedded
                </p>
              </>
            ) : (
              <p style={{ fontSize: '0.85rem', color: '#6b7280' }}>Chunking document…</p>
            )}
          </div>
        ) : (
          <>
            <p>Drop a PDF or TXT file here</p>
            <span style={{ color: '#9ca3af' }}>or</span>
            <label className="upload-btn">
              Browse files
              <input type="file" accept=".pdf,.txt" onChange={handleFileInput} hidden />
            </label>
          </>
        )}
      </div>

      {error && <p className="error-msg">{error}</p>}

      <div className="doc-list">
        <h3>Uploaded Documents ({documents.length})</h3>
        {documents.length === 0 ? (
          <p className="empty">No documents uploaded yet.</p>
        ) : (
          documents.map((doc) => (
            <div key={doc.id} className="doc-item">
              <div>
                <span className="doc-name">{doc.name}</span>
                <span className="doc-meta">
                  {doc.chunk_count} chunk{doc.chunk_count !== 1 ? 's' : ''} · {doc.file_type.toUpperCase()}
                </span>
              </div>
              <button className="del-btn" onClick={() => handleDelete(doc.id)}>
                Delete
              </button>
            </div>
          ))
        )}
      </div>

      <style>{`
        .docs-container { display: flex; flex-direction: column; gap: 1.5rem; }
        .drop-zone {
          border: 2px dashed #d1d5db;
          border-radius: 12px;
          padding: 2.5rem;
          text-align: center;
          background: white;
          transition: all 0.2s;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.75rem;
          color: #6b7280;
        }
        .drop-zone.drag-over { border-color: #3b82f6; background: #eff6ff; }
        .drop-zone.uploading { opacity: 0.85; pointer-events: none; }
        .progress-bar-bg {
          width: 100%; height: 8px; background: #e5e7eb;
          border-radius: 4px; overflow: hidden;
        }
        .progress-bar-fill {
          height: 100%; background: #3b82f6;
          border-radius: 4px; transition: width 0.4s ease;
        }
        .upload-btn {
          padding: 0.6rem 1.25rem;
          background: #3b82f6;
          color: white;
          border-radius: 8px;
          cursor: pointer;
          font-size: 0.9rem;
          font-weight: 600;
        }
        .upload-btn:hover { background: #2563eb; }
        .error-msg { color: #dc2626; font-size: 0.9rem; }
        .doc-list {
          background: white;
          border-radius: 12px;
          border: 1px solid #e5e7eb;
          padding: 1.25rem;
        }
        .doc-list h3 { font-size: 1rem; font-weight: 600; margin-bottom: 1rem; }
        .empty { color: #9ca3af; font-size: 0.9rem; }
        .doc-item {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.75rem 0;
          border-bottom: 1px solid #f3f4f6;
        }
        .doc-item:last-child { border-bottom: none; }
        .doc-name { font-size: 0.9rem; font-weight: 500; display: block; }
        .doc-meta { font-size: 0.78rem; color: #9ca3af; }
        .del-btn {
          background: none;
          border: 1px solid #fecaca;
          color: #dc2626;
          padding: 0.35rem 0.75rem;
          border-radius: 6px;
          cursor: pointer;
          font-size: 0.8rem;
        }
        .del-btn:hover { background: #fef2f2; }
      `}</style>
    </div>
  )
}
