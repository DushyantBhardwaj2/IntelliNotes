"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Upload,
  Trash2,
  Send,
  Globe,
  FileText,
  ChevronDown,
  ChevronRight,
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  RefreshCw,
  Layers,
  Sparkles,
  CheckCircle2,
} from "lucide-react";

interface DocumentInfo {
  doc_id: string;
  filename: string;
  chunk_count: number;
}

interface TraceStep {
  step: string;
  [key: string]: any;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  groundingVerdict?: boolean | null;
  trace?: TraceStep[];
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string>("");
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [webEnabled, setWebEnabled] = useState<boolean>(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadStatus, setUploadStatus] = useState<string>("");
  const [backendHealth, setBackendHealth] = useState<{
    status: string;
    model?: string;
    chunks_in_store?: number;
  } | null>(null);
  const [openTraces, setOpenTraces] = useState<Record<string, boolean>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Initialize session
  useEffect(() => {
    const newSession = "session_" + Math.random().toString(36).substring(2, 10);
    setSessionId(newSession);
    checkHealth();
    fetchDocuments();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const checkHealth = async () => {
    try {
      const res = await fetch("/api/health");
      if (res.ok) {
        const data = await res.json();
        setBackendHealth(data);
      } else {
        setBackendHealth({ status: "unavailable" });
      }
    } catch {
      setBackendHealth({ status: "error" });
    }
  };

  const fetchDocuments = async () => {
    try {
      const res = await fetch("/api/documents");
      if (res.ok) {
        const data = await res.json();
        setDocuments(data || []);
      }
    } catch (err) {
      console.error("Failed to load documents", err);
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadStatus("Error: Only PDF files are supported.");
      return;
    }

    setIsUploading(true);
    setUploadStatus("Uploading & indexing chunks...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        setUploadStatus(`Uploaded ${data.filename} (${data.processed_chunks} chunks).`);
        fetchDocuments();
        checkHealth();
      } else {
        setUploadStatus(`Upload failed: ${data.detail || "Server error"}`);
      }
    } catch (err: any) {
      setUploadStatus(`Upload failed: ${err.message || "Network error"}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteDocument = async (docId: string) => {
    if (!confirm("Delete this document and its embeddings?")) return;
    try {
      const res = await fetch(`/api/documents/${docId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        fetchDocuments();
        checkHealth();
        if (selectedDocId === docId) setSelectedDocId("");
      } else {
        alert("Failed to delete document");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Clear ALL documents from the vector database?")) return;
    try {
      const res = await fetch("/api/documents", {
        method: "DELETE",
      });
      if (res.ok) {
        fetchDocuments();
        checkHealth();
        setSelectedDocId("");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = inputMessage.trim();
    if (!query || isLoading) return;

    const userMsg: Message = {
      id: "msg_" + Date.now(),
      role: "user",
      content: query,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage("");
    setIsLoading(true);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: query,
          session_id: sessionId,
          web_enabled: webEnabled,
          doc_id: selectedDocId || undefined,
        }),
      });

      const data = await res.json();
      if (res.ok) {
        const assistantMsg: Message = {
          id: "msg_" + (Date.now() + 1),
          role: "assistant",
          content: data.answer || "No response text received.",
          groundingVerdict: data.grounding_verdict,
          trace: data.trace,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        // Auto open trace on newest message
        setOpenTraces((prev) => ({ ...prev, [assistantMsg.id]: true }));
      } else {
        const errorMsg: Message = {
          id: "msg_" + (Date.now() + 1),
          role: "assistant",
          content: `Error: ${data.detail || "Failed to process chat query."}`,
        };
        setMessages((prev) => [...prev, errorMsg]);
      }
    } catch (err: any) {
      const errorMsg: Message = {
        id: "msg_" + (Date.now() + 1),
        role: "assistant",
        content: `Network error: ${err.message || "Failed to reach server"}`,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
      checkHealth();
    }
  };

  const resetSession = () => {
    setSessionId("session_" + Math.random().toString(36).substring(2, 10));
    setMessages([]);
  };

  const toggleTrace = (msgId: string) => {
    setOpenTraces((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  return (
    <div style={{ display: "flex", height: "100vh", width: "100vw", overflow: "hidden" }}>
      {/* Sidebar: Documents & Knowledge Base */}
      <aside
        style={{
          width: "320px",
          backgroundColor: "var(--bg-surface)",
          borderRight: "1px solid var(--border-color)",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}
      >
        {/* Brand / Logo */}
        <div
          style={{
            padding: "18px 20px",
            borderBottom: "1px solid var(--border-color)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
              }}
            >
              <Sparkles size={18} />
            </div>
            <div>
              <h1 style={{ fontSize: "16px", fontWeight: "700", color: "#f3f4f6" }}>
                IntelliNotes
              </h1>
              <p style={{ fontSize: "11px", color: "var(--text-muted)" }}>Agentic RAG Assistant</p>
            </div>
          </div>
          <button
            onClick={resetSession}
            title="Start new conversation session"
            style={{
              background: "transparent",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
              padding: "4px 8px",
              borderRadius: "6px",
              fontSize: "11px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <RefreshCw size={12} />
            New
          </button>
        </div>

        {/* Backend health status indicator */}
        <div
          style={{
            padding: "10px 20px",
            background: "rgba(17, 24, 39, 0.6)",
            borderBottom: "1px solid var(--border-color)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor: backendHealth?.status === "ok" ? "var(--success)" : "var(--danger)",
                boxShadow:
                  backendHealth?.status === "ok"
                    ? "0 0 8px rgba(16, 185, 129, 0.6)"
                    : "0 0 8px rgba(239, 68, 68, 0.6)",
              }}
            />
            <span style={{ color: "var(--text-secondary)" }}>
              {backendHealth?.status === "ok" ? "Backend Online" : "Connecting..."}
            </span>
          </div>
          <span style={{ color: "var(--text-muted)", fontSize: "11px" }}>
            {backendHealth?.chunks_in_store ?? 0} chunks
          </span>
        </div>

        {/* Upload Section */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border-color)" }}>
          <div style={{ marginBottom: "10px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: "12px", fontWeight: "600", textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--text-muted)" }}>
              Knowledge Base
            </span>
            {documents.length > 0 && (
              <button
                onClick={handleClearAll}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  fontSize: "11px",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "2px",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--danger)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
              >
                Clear All
              </button>
            )}
          </div>

          <label
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "16px",
              border: "1px dashed var(--border-color)",
              borderRadius: "8px",
              cursor: isUploading ? "not-allowed" : "pointer",
              backgroundColor: "var(--bg-card)",
              transition: "border-color 0.2s",
            }}
          >
            <Upload size={20} color="var(--accent)" style={{ marginBottom: "6px" }} />
            <span style={{ fontSize: "12px", fontWeight: "500", color: "var(--text-primary)" }}>
              {isUploading ? "Processing PDF..." : "Upload Notes PDF"}
            </span>
            <span style={{ fontSize: "10px", color: "var(--text-muted)", marginTop: "2px" }}>
              Max 20 MB (.pdf)
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              disabled={isUploading}
              onChange={handleUpload}
              style={{ display: "none" }}
            />
          </label>

          {uploadStatus && (
            <p
              style={{
                marginTop: "8px",
                fontSize: "11px",
                color: uploadStatus.startsWith("Error") || uploadStatus.startsWith("Upload failed")
                  ? "var(--danger)"
                  : "var(--success)",
              }}
            >
              {uploadStatus}
            </p>
          )}
        </div>

        {/* Documents List */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
          {documents.length === 0 ? (
            <div style={{ textAlign: "center", padding: "30px 10px", color: "var(--text-muted)", fontSize: "12px" }}>
              <FileText size={28} style={{ margin: "0 auto 8px auto", opacity: 0.4 }} />
              <p>No documents uploaded.</p>
              <p style={{ fontSize: "11px", marginTop: "4px" }}>
                Upload a lecture PDF or document to chat over your notes.
              </p>
            </div>
          ) : (
            documents.map((doc) => (
              <div
                key={doc.doc_id}
                onClick={() => setSelectedDocId(selectedDocId === doc.doc_id ? "" : doc.doc_id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 12px",
                  borderRadius: "6px",
                  marginBottom: "6px",
                  backgroundColor:
                    selectedDocId === doc.doc_id ? "var(--accent-light)" : "var(--bg-card)",
                  border:
                    selectedDocId === doc.doc_id
                      ? "1px solid var(--accent)"
                      : "1px solid var(--border-color)",
                  cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "8px", overflow: "hidden" }}>
                  <FileText size={16} color={selectedDocId === doc.doc_id ? "var(--accent)" : "var(--text-muted)"} />
                  <div style={{ overflow: "hidden" }}>
                    <p
                      style={{
                        fontSize: "12px",
                        fontWeight: "500",
                        color: "var(--text-primary)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                      title={doc.filename}
                    >
                      {doc.filename}
                    </p>
                    <p style={{ fontSize: "10px", color: "var(--text-muted)" }}>
                      {doc.chunk_count} chunk{doc.chunk_count === 1 ? "" : "s"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteDocument(doc.doc_id);
                  }}
                  title="Delete document"
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    padding: "4px",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = "var(--danger)")}
                  onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Active Session & Scope */}
        <div
          style={{
            padding: "12px 16px",
            borderTop: "1px solid var(--border-color)",
            backgroundColor: "var(--bg-card)",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
            <span>Active Session:</span>
            <code style={{ color: "var(--text-secondary)" }}>{sessionId}</code>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span>Filter Scope:</span>
            <span style={{ color: selectedDocId ? "var(--accent)" : "var(--text-secondary)" }}>
              {selectedDocId ? "Selected Doc" : "All Documents"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          backgroundColor: "var(--bg-primary)",
          overflow: "hidden",
        }}
      >
        {/* Chat Header Bar */}
        <header
          style={{
            padding: "14px 24px",
            borderBottom: "1px solid var(--border-color)",
            backgroundColor: "var(--bg-surface)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ fontSize: "14px", fontWeight: "600", color: "var(--text-primary)" }}>
              Conversation
            </span>
            {selectedDocId && (
              <span
                style={{
                  fontSize: "11px",
                  backgroundColor: "var(--accent-light)",
                  color: "var(--accent)",
                  padding: "2px 8px",
                  borderRadius: "12px",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                Filtered: {documents.find((d) => d.doc_id === selectedDocId)?.filename || selectedDocId}
              </span>
            )}
          </div>

          {/* Web Search Toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                cursor: "pointer",
                fontSize: "12px",
                color: webEnabled ? "var(--text-primary)" : "var(--text-muted)",
                backgroundColor: webEnabled ? "rgba(59, 130, 246, 0.1)" : "transparent",
                padding: "6px 12px",
                borderRadius: "6px",
                border: "1px solid " + (webEnabled ? "var(--accent)" : "var(--border-color)"),
                transition: "all 0.2s",
              }}
            >
              <Globe size={14} color={webEnabled ? "var(--accent)" : "var(--text-muted)"} />
              <span>Web Search Fallback</span>
              <input
                type="checkbox"
                checked={webEnabled}
                onChange={(e) => setWebEnabled(e.target.checked)}
                style={{ cursor: "pointer" }}
              />
            </label>
          </div>
        </header>

        {/* Message Thread */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {messages.length === 0 ? (
            <div
              style={{
                margin: "auto",
                textAlign: "center",
                maxWidth: "460px",
                color: "var(--text-secondary)",
              }}
            >
              <div
                style={{
                  width: "56px",
                  height: "56px",
                  borderRadius: "16px",
                  background: "linear-gradient(135deg, rgba(59,130,246,0.2), rgba(139,92,246,0.2))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  margin: "0 auto 16px auto",
                  color: "var(--accent)",
                }}
              >
                <Layers size={28} />
              </div>
              <h2 style={{ fontSize: "18px", fontWeight: "600", color: "var(--text-primary)", marginBottom: "8px" }}>
                Welcome to IntelliNotes
              </h2>
              <p style={{ fontSize: "13px", lineHeight: "1.6", color: "var(--text-muted)" }}>
                Ask any question about your uploaded PDF notes. The agent will retrieve relevant page citations, grade context relevance, optionally search the web if your notes are insufficient, and verify answer grounding.
              </p>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: msg.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                {/* Bubble */}
                <div
                  style={{
                    maxWidth: "80%",
                    padding: "12px 16px",
                    borderRadius: "10px",
                    backgroundColor: msg.role === "user" ? "var(--accent)" : "var(--bg-card)",
                    color: msg.role === "user" ? "#ffffff" : "var(--text-primary)",
                    border: msg.role === "user" ? "none" : "1px solid var(--border-color)",
                    fontSize: "14px",
                    lineHeight: "1.6",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {msg.content}
                </div>

                {/* Grounding verdict & trace (Assistant only) */}
                {msg.role === "assistant" && (
                  <div style={{ marginTop: "6px", width: "80%", maxWidth: "80%" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                      {/* Grounding Badge */}
                      {msg.groundingVerdict === true && (
                        <span
                          style={{
                            fontSize: "11px",
                            backgroundColor: "var(--success-bg)",
                            color: "var(--success)",
                            padding: "2px 8px",
                            borderRadius: "12px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          <ShieldCheck size={12} /> Grounded in Notes
                        </span>
                      )}
                      {msg.groundingVerdict === false && (
                        <span
                          style={{
                            fontSize: "11px",
                            backgroundColor: "var(--warning-bg)",
                            color: "var(--warning)",
                            padding: "2px 8px",
                            borderRadius: "12px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          <ShieldAlert size={12} /> Caution: Low Grounding Confidence
                        </span>
                      )}
                      {msg.groundingVerdict === null && (
                        <span
                          style={{
                            fontSize: "11px",
                            backgroundColor: "rgba(59,130,246,0.1)",
                            color: "var(--accent)",
                            padding: "2px 8px",
                            borderRadius: "12px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          <Globe size={12} /> Direct / Web Synthesized
                        </span>
                      )}

                      {/* Trace Accordion Toggle */}
                      {msg.trace && msg.trace.length > 0 && (
                        <button
                          onClick={() => toggleTrace(msg.id)}
                          style={{
                            background: "transparent",
                            border: "1px solid var(--border-color)",
                            color: "var(--text-muted)",
                            fontSize: "11px",
                            padding: "2px 8px",
                            borderRadius: "6px",
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          {openTraces[msg.id] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          Agent Trace ({msg.trace.length} steps)
                        </button>
                      )}
                    </div>

                    {/* Collapsible Trace Steps Timeline */}
                    {openTraces[msg.id] && msg.trace && msg.trace.length > 0 && (
                      <div
                        style={{
                          marginTop: "8px",
                          padding: "12px",
                          backgroundColor: "var(--bg-surface)",
                          border: "1px solid var(--border-color)",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                      >
                        <p style={{ fontWeight: "600", color: "var(--text-secondary)", marginBottom: "8px", display: "flex", alignItems: "center", gap: "6px" }}>
                          <Layers size={14} color="var(--accent)" />
                          Execution Trace Timeline
                        </p>
                        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                          {msg.trace.map((step, idx) => (
                            <div
                              key={idx}
                              style={{
                                padding: "8px 10px",
                                backgroundColor: "var(--bg-card)",
                                borderRadius: "6px",
                                borderLeft: "3px solid var(--accent)",
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                                <span style={{ fontWeight: "600", color: "var(--text-primary)", textTransform: "capitalize" }}>
                                  Step {idx + 1}: {step.step || "node"}
                                </span>
                                {step.route && (
                                  <span style={{ fontSize: "10px", color: "var(--accent)", backgroundColor: "var(--accent-light)", padding: "1px 6px", borderRadius: "4px" }}>
                                    route: {step.route}
                                  </span>
                                )}
                              </div>

                              {/* Details */}
                              {step.reason && (
                                <p style={{ color: "var(--text-secondary)", fontSize: "11px", marginBottom: "4px" }}>
                                  <strong>Reason:</strong> {step.reason}
                                </p>
                              )}
                              {step.query && (
                                <p style={{ color: "var(--text-secondary)", fontSize: "11px", marginBottom: "4px" }}>
                                  <strong>Query:</strong> {step.query}
                                </p>
                              )}
                              {step.chunks_found !== undefined && (
                                <p style={{ color: "var(--text-secondary)", fontSize: "11px" }}>
                                  <strong>Chunks Retrieved:</strong> {step.chunks_found}
                                </p>
                              )}
                              {step.citations && step.citations.length > 0 && (
                                <div style={{ marginTop: "4px", fontSize: "11px", color: "var(--text-muted)" }}>
                                  <strong>Citations:</strong>
                                  <ul style={{ paddingLeft: "16px", marginTop: "2px" }}>
                                    {step.citations.map((c: any, cidx: number) => (
                                      <li key={cidx}>
                                        {c.filename || "Doc"} — Page {c.page}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {step.web_sources && step.web_sources.length > 0 && (
                                <div style={{ marginTop: "4px", fontSize: "11px", color: "var(--text-muted)" }}>
                                  <strong>Web Sources:</strong>
                                  <ul style={{ paddingLeft: "16px", marginTop: "2px" }}>
                                    {step.web_sources.map((s: any, sidx: number) => (
                                      <li key={sidx}>
                                        <a href={s.url} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", textDecoration: "none" }}>
                                          {s.title || s.url}
                                        </a>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}

          {isLoading && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--text-muted)", fontSize: "13px" }}>
              <div
                style={{
                  width: "12px",
                  height: "12px",
                  borderRadius: "50%",
                  border: "2px solid var(--accent)",
                  borderTopColor: "transparent",
                  animation: "spin 1s linear infinite",
                }}
              />
              <span>Reasoning & executing agent graph...</span>
              <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div style={{ padding: "16px 24px", borderTop: "1px solid var(--border-color)", backgroundColor: "var(--bg-surface)" }}>
          <form onSubmit={handleSendMessage} style={{ display: "flex", gap: "10px" }}>
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Ask a question about your uploaded notes..."
              disabled={isLoading}
              style={{
                flex: 1,
                padding: "12px 16px",
                backgroundColor: "var(--bg-card)",
                border: "1px solid var(--border-color)",
                borderRadius: "8px",
                color: "var(--text-primary)",
                fontSize: "14px",
                outline: "none",
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border-focus)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border-color)")}
            />
            <button
              type="submit"
              disabled={isLoading || !inputMessage.trim()}
              style={{
                padding: "12px 20px",
                backgroundColor: inputMessage.trim() && !isLoading ? "var(--accent)" : "var(--bg-card)",
                color: inputMessage.trim() && !isLoading ? "#ffffff" : "var(--text-muted)",
                border: "1px solid var(--border-color)",
                borderRadius: "8px",
                cursor: inputMessage.trim() && !isLoading ? "pointer" : "not-allowed",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "14px",
                fontWeight: "500",
                transition: "all 0.2s",
              }}
            >
              <Send size={16} />
              Send
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
