import { useState, useRef, useEffect } from 'react'
import './App.css'
import Logo from './Logo.jsx'

const API = import.meta.env.VITE_API_BASE ?? ''

/* ── Suggestion chips shown on empty state ───────────────────────────────── */
const CHIPS = [
  { label: 'Customer profile',  text: 'Show me the profile for TechCorp Ltd' },
  { label: 'Open issues',       text: 'What are the open issues for FinServe Group' },
  { label: 'Issue history',     text: 'Summarise the history of issue 1' },
  { label: 'Critical issues',   text: 'Which customers have critical open issues' },
  { label: 'Escalation brief',  text: 'Generate an escalation brief for TechCorp' },
  { label: 'Next action',       text: 'Create a next action for issue 4' },
]

/* ── Saved chats storage key per user ───────────────────────────────────── */
function savedChatsKey(username) { return `acme_chats_${username}` }

function loadSavedChats(username) {
  try { return JSON.parse(localStorage.getItem(savedChatsKey(username)) || '[]') }
  catch { return [] }
}

function persistSavedChats(username, chats) {
  localStorage.setItem(savedChatsKey(username), JSON.stringify(chats))
}

/* ── Preview mode ───────────────────────────────────────────────────────── */
const PREVIEW_USER = {
  username: 'carol',
  roles: ['admin'],
  permissions: ['read', 'update_issue', 'create_next_action'],
}

const MOCK_REPLIES = {
  'techcorp':   'TechCorp Ltd — Enterprise tier\n\nAccount Manager: Bob Smith · alice@techcorp.com\n\nOpen Issues:\n- API rate limiting causing failures (Critical)\n- SSO integration broken after upgrade (High)',
  'finserve':   'FinServe Group — 2 open issues\n\n- Compliance report generation error (Critical)\n- Data retention policy misconfigured (High)',
  'issue 1':    'Issue 1 — API Rate Limiting\n\nStatus: Open · Priority: Critical\n\nHistory:\n- Bob Smith: Escalated to engineering. Root cause is misconfigured throttle limits.\n- Engineering: Bucket set to 100 instead of 1000. Patch on Friday.\n\nNext Action: Deploy rate-limit patch to production gateway by 2025-05-10',
  'critical':   'Customers with critical open issues:\n\n- TechCorp Ltd — API rate limiting causing failures\n- FinServe Group — Compliance report generation error',
  'escalation': 'TechCorp Ltd — Escalation Brief\n\n1. Customer Overview\nEnterprise tier · Account Manager: Bob Smith · alice@techcorp.com\n\n2. Active Issues\n- API rate limiting (Critical, 5 days open)\n- SSO integration broken (High, 3 days)\n\n3. Key Risks\n- API failures risk SLA breach within 48 hours\n- SSO blocks all new user onboarding\n\n4. Recommended Actions\n- Deploy rate-limit patch by 2025-05-10\n- Obtain Okta config from client IT by 2025-05-09',
  'emma':       'Emma Davis — HealthPlus Ltd\n\nTier: Standard · Account Manager: Bob Smith · emma@healthplus.com\n\nOpen Issue: Dashboard widgets not loading (Medium)',
}
function mockReply(q) {
  const ql = q.toLowerCase()
  for (const [k, v] of Object.entries(MOCK_REPLIES)) {
    if (ql.includes(k)) return v
  }
  return 'Preview mode — try asking about TechCorp, FinServe, issue 1, critical issues, escalation brief, or Emma Davis.'
}

/* ── API ────────────────────────────────────────────────────────────────── */
async function apiLogin(username, password) {
  const res = await fetch(`${API}/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) throw new Error('Invalid credentials')
  return res.json()
}
async function apiMe(token) {
  const res = await fetch(`${API}/me`, { headers: { Authorization: `Bearer ${token}` } })
  if (!res.ok) throw new Error('Could not fetch user info')
  return res.json()
}
async function apiChat(token, query) {
  const res = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (res.status === 403) throw new Error('Permission denied. Your role cannot perform this action.')
  if (!res.ok) throw new Error(`Server error ${res.status}`)
  return res.json()
}

/* ── Helpers ────────────────────────────────────────────────────────────── */
function roleColour(role) {
  return { admin: '#FFE600', support_user: '#4ade80', sales_user: '#60a5fa' }[role] ?? '#888'
}
function getInitials(name) {
  const p = name.trim().split(/\s+/)
  return p.length > 1 ? (p[0][0] + p[1][0]).toUpperCase() : name.slice(0, 2).toUpperCase()
}
function truncate(str, n) { return str.length > n ? str.slice(0, n) + '…' : str }
function timestamp() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }

/* ── Markdown renderer ──────────────────────────────────────────────────── */
function sanitizeText(text) {
  return text
    .replace(/\p{Emoji_Presentation}/gu, '')
    .replace(/[\u{1F300}-\u{1FAFF}]/gu, '')
    .replace(/\s*—\s*/g, ': ')
    .replace(/\s*--\s*/g, ': ')
    .replace(/#(\d+)/g, '$1')   // #1 → 1 (issue refs)
    .replace(/#/g, '')           // any remaining stray #
}

function inlineFormat(raw) {
  const parts = raw.split(/(\*\*[^*]+\*\*)/)
  return parts.map((p, i) =>
    p.startsWith('**') && p.endsWith('**')
      ? <strong key={i}>{sanitizeText(p.slice(2, -2))}</strong>
      : sanitizeText(p)
  )
}

function parseTableRow(line) {
  return line.replace(/^\||\|$/g, '').split('|').map(c => c.trim())
}

function MarkdownContent({ text }) {
  const lines = text
    .replace(/\p{Emoji_Presentation}/gu, '')
    .replace(/[\u{1F300}-\u{1FAFF}]/gu, '')
    .replace(/\s*—\s*/g, ': ')
    .replace(/\s*--\s*/g, ': ')
    .split('\n')
  const elements = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    // H1
    if (/^# /.test(line)) {
      elements.push(<h1 key={elements.length} className="md-h1">{inlineFormat(line.slice(2))}</h1>)
      i++; continue
    }

    // H2
    if (/^## /.test(line)) {
      elements.push(<h2 key={elements.length} className="md-h2">{inlineFormat(line.slice(3))}</h2>)
      i++; continue
    }

    // H3
    if (/^### /.test(line)) {
      elements.push(<h3 key={elements.length} className="md-h3">{inlineFormat(line.slice(4))}</h3>)
      i++; continue
    }

    // Horizontal rule
    if (/^---+$/.test(trimmed)) {
      elements.push(<hr key={elements.length} className="md-hr" />)
      i++; continue
    }

    // Pipe table: header row followed by separator
    if (line.startsWith('|') && i + 1 < lines.length && /^\|[-| :]+\|/.test(lines[i + 1])) {
      const headers = parseTableRow(line)
      i += 2
      const rows = []
      while (i < lines.length && lines[i].startsWith('|')) {
        rows.push(parseTableRow(lines[i]))
        i++
      }
      elements.push(
        <table key={elements.length} className="md-table">
          <thead><tr>{headers.map((h, j) => <th key={j}>{inlineFormat(h)}</th>)}</tr></thead>
          <tbody>{rows.map((row, r) => (
            <tr key={r}>{row.map((cell, j) => <td key={j}>{inlineFormat(cell)}</td>)}</tr>
          ))}</tbody>
        </table>
      )
      continue
    }

    // Blockquote
    if (line.startsWith('> ')) {
      const bqLines = []
      while (i < lines.length && lines[i].startsWith('> ')) {
        bqLines.push(lines[i].slice(2))
        i++
      }
      elements.push(
        <blockquote key={elements.length} className="md-blockquote">
          {bqLines.map((l, j) => <p key={j} className="md-p">{inlineFormat(l)}</p>)}
        </blockquote>
      )
      continue
    }

    // Numbered list — skip blank lines between items to keep one <ol>
    if (/^\d+\. /.test(line)) {
      const items = []
      let counter = 1
      while (i < lines.length) {
        if (/^\d+\. /.test(lines[i])) {
          items.push(<li key={i} value={counter++}>{inlineFormat(lines[i].replace(/^\d+\. /, ''))}</li>)
          i++
        } else if (lines[i].trim() === '' && i + 1 < lines.length && /^\d+\. /.test(lines[i + 1])) {
          i++ // skip blank line between numbered items
        } else {
          break
        }
      }
      elements.push(<ol key={elements.length} className="md-list">{items}</ol>)
      continue
    }

    // Unordered list — skip blank lines between items to keep one <ul>
    if (/^[-*] /.test(line)) {
      const items = []
      while (i < lines.length) {
        if (/^[-*] /.test(lines[i])) {
          items.push(<li key={i}>{inlineFormat(lines[i].slice(2))}</li>)
          i++
        } else if (lines[i].trim() === '' && i + 1 < lines.length && /^[-*] /.test(lines[i + 1])) {
          i++
        } else {
          break
        }
      }
      elements.push(<ul key={elements.length} className="md-list">{items}</ul>)
      continue
    }

    // Empty line
    if (trimmed === '') { i++; continue }

    // Paragraph
    elements.push(<p key={elements.length} className="md-p">{inlineFormat(line)}</p>)
    i++
  }

  return <div className="md-content">{elements}</div>
}

/* ── Icons ──────────────────────────────────────────────────────────────── */
function SendIcon() {
  return (
    <svg className="send-icon" viewBox="0 0 24 24" aria-hidden="true">
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  )
}
function NewChatIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  )
}
function EyeIcon({ off }) {
  return off ? (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  ) : (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
      <circle cx="12" cy="12" r="3"/>
    </svg>
  )
}
function AssistantAvatar() { return <div className="asst-avatar">A</div> }
function Typing() {
  return (
    <div className="message assistant">
      <AssistantAvatar />
      <div className="typing-bubble">
        <div className="dot" /><div className="dot" /><div className="dot" />
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   LOGIN
══════════════════════════════════════════════════════════════════════════ */
function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw,   setShowPw]   = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!username.trim()) { setError('Please enter your username.'); return }
    setLoading(true); setError('')
    try {
      const tokenData = await apiLogin(username.trim(), password)
      const user      = await apiMe(tokenData.access_token)
      onLogin(tokenData.access_token, user)
    } catch (err) {
      setError(err.message || 'Login failed.')
    } finally { setLoading(false) }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo"><div className="login-logo-icon">A</div></div>
        <div className="login-heading">ACME</div>
        <div className="login-subheading">Operations Assistant</div>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit} className="login-form" noValidate>
          <div className="login-field">
            <label className="login-label">Username</label>
            <input className="login-input" type="text" value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="Enter your username" autoComplete="username" autoFocus />
          </div>
          <div className="login-field">
            <label className="login-label">Password</label>
            <div className="login-pw-wrap">
              <input className="login-input" type={showPw ? 'text' : 'password'}
                value={password} onChange={e => setPassword(e.target.value)}
                placeholder="Enter your password" autoComplete="current-password" />
              <button type="button" className="login-pw-toggle"
                onClick={() => setShowPw(v => !v)} tabIndex={-1}>
                <EyeIcon off={showPw} />
              </button>
            </div>
          </div>
          <button type="submit" className="login-submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign In'}
          </button>
        </form>
        <button className="login-preview" onClick={() => onLogin('preview-mode', PREVIEW_USER)} type="button">
          Continue in preview mode
        </button>
      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   CHAT APP
══════════════════════════════════════════════════════════════════════════ */
function ChatApp({ token, user, onSignOut }) {
  const username  = user.username
  const role      = user.roles?.[0] ?? 'sales_user'
  const rc        = roleColour(role)
  const av        = getInitials(username)
  const roleLabel = role.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  const isPreview = token === 'preview-mode'

  // Chat sessions: array of { id, title, time, messages[] }
  const [sessions,    setSessions]    = useState(() => loadSavedChats(username))
  const [activeId,    setActiveId]    = useState(null)   // current session id
  const [messages,    setMessages]    = useState([])
  const [inputVal,    setInputVal]    = useState('')
  const [typing,      setTyping]      = useState(false)
  const chatRef  = useRef(null)
  const inputRef = useRef(null)

  // Persist sessions to localStorage whenever they change
  useEffect(() => {
    if (!isPreview) persistSavedChats(username, sessions)
  }, [sessions])

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [messages, typing])

  /* ── New chat ── */
  function newChat() {
    setActiveId(null)
    setMessages([])
    setInputVal('')
    inputRef.current?.focus()
  }

  /* ── Load a saved session ── */
  function loadSession(id) {
    const s = sessions.find(s => s.id === id)
    if (!s) return
    setActiveId(id)
    setMessages(s.messages)
    inputRef.current?.focus()
  }

  /* ── Delete a saved session ── */
  function deleteSession(e, id) {
    e.stopPropagation()
    const updated = sessions.filter(s => s.id !== id)
    setSessions(updated)
    if (activeId === id) newChat()
  }

  /* ── Save current messages to sessions ── */
  function saveSession(msgs) {
    if (msgs.length === 0) return
    const firstUserMsg = msgs.find(m => m.role === 'user')
    if (!firstUserMsg) return
    const title = truncate(firstUserMsg.text, 36)
    const time  = timestamp()

    if (activeId) {
      // Update existing session
      setSessions(prev => prev.map(s =>
        s.id === activeId ? { ...s, messages: msgs, time } : s
      ))
    } else {
      // Create new session
      const id = Date.now().toString()
      setActiveId(id)
      setSessions(prev => [{ id, title, time, messages: msgs }, ...prev].slice(0, 20))
    }
  }

  /* ── Send ── */
  async function send() {
    const text = inputVal.trim()
    if (!text || typing) return
    const updated = [...messages, { role: 'user', text }]
    setMessages(updated)
    setInputVal('')
    setTyping(true)

    if (isPreview) {
      setTimeout(() => {
        setTyping(false)
        const final = [...updated, { role: 'assistant', text: mockReply(text), trace: null }]
        setMessages(final)
        saveSession(final)
      }, 1000)
      return
    }

    try {
      const data = await apiChat(token, text)
      const final = [...updated, {
        role: 'assistant',
        text: data.response ?? 'No response.',
        trace: data.trace_id,
      }]
      setMessages(final)
      saveSession(final)
    } catch (err) {
      const final = [...updated, { role: 'assistant', text: err.message, isError: true }]
      setMessages(final)
    } finally { setTyping(false) }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function handleChip(text) {
    setInputVal(text)
    inputRef.current?.focus()
  }

  const hasMessages = messages.length > 0

  return (
    <div className="shell">

      {/* ══ SIDEBAR ══ */}
      <aside className="sidebar">

        {/* Brand */}
        <div className="sb-top">
          <Logo variant="dark" width={200} />
        </div>

        {/* Saved chats */}
        <div className="sb-middle">
          <div className="sb-chats-header">
            <span className="sb-section-label">Saved chats</span>
            <button className="sb-new-btn" onClick={newChat} title="New chat">
              <NewChatIcon />
            </button>
          </div>

          {sessions.length === 0 ? (
            <div className="sb-empty-chats">No saved chats yet</div>
          ) : (
            sessions.map(s => (
              <div
                key={s.id}
                className={`sb-chat-item${activeId === s.id ? ' active' : ''}`}
                onClick={() => loadSession(s.id)}
              >
                <div className="sb-chat-title">{s.title}</div>
                <div className="sb-chat-meta">
                  <span className="sb-chat-time">{s.time}</span>
                  <button
                    className="sb-chat-del"
                    onClick={e => deleteSession(e, s.id)}
                    title="Delete"
                  >×</button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* User block pinned at bottom */}
        <div className="sb-bottom">
          <div className="sb-user">
            <div className="sb-avatar" style={{
              background: `color-mix(in srgb, ${rc} 18%, transparent)`,
              borderColor: `color-mix(in srgb, ${rc} 35%, transparent)`,
              color: rc,
            }}>
              {av}
            </div>
            <div className="sb-user-info">
              <div className="sb-user-name">{username.replace(/\b\w/g, c => c.toUpperCase())}</div>
              <div className="sb-user-role">{roleLabel}</div>
            </div>
            <button className="sb-signout" onClick={onSignOut}>Sign out</button>
          </div>
        </div>

      </aside>

      {/* ══ MAIN PANEL ══ */}
      <div className="main">

        <div className="topbar">
          <div className="topbar-left">
            <span className="topbar-title">Acme Operations</span>
            <span className="topbar-sub">&nbsp;/ Assistant</span>
          </div>
          <div className="topbar-right">
            <button className="topbar-new-btn" onClick={newChat}>
              <NewChatIcon /> New chat
            </button>
            <div className="topbar-status">
              <span className="status-dot" />
              12 open issues &nbsp;·&nbsp; 3 critical
            </div>
          </div>
        </div>

        <div ref={chatRef} className={`chat-area ${hasMessages ? 'filled' : 'empty'}`}>
          {!hasMessages ? (
            <>
              <div className="welcome">
                <div className="welcome-icon">A</div>
                <div className="welcome-heading">How can I help you today?</div>
                <div className="welcome-sub">
                  Ask about customers, open issues, or request an escalation brief.
                </div>
              </div>
              <div className="chip-grid">
                {CHIPS.map((chip, i) => (
                  <button key={i} className="chip" onClick={() => handleChip(chip.text)}>
                    <span className="chip-label">{chip.label}</span>
                    <span className="chip-text">{chip.text}</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="messages-list">
              {messages.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  {msg.role === 'assistant' && <AssistantAvatar />}
                  <div className={`bubble${msg.isError ? ' bubble-error' : ''}`}>
                    {msg.role === 'assistant'
                      ? <MarkdownContent text={msg.text} />
                      : msg.text.split('\n').map((line, j, arr) => (
                          <span key={j}>{line}{j < arr.length - 1 && <br />}</span>
                        ))
                    }
                    {msg.trace && <div className="bubble-trace">trace {msg.trace}</div>}
                  </div>
                </div>
              ))}
              {typing && <Typing />}
            </div>
          )}
        </div>

        <div className="input-bar">
          <input
            ref={inputRef}
            className="input-field"
            value={inputVal}
            onChange={e => setInputVal(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about a customer, issue, or next action..."
            disabled={typing}
          />
          <button className="send-btn" onClick={send} aria-label="Send"
            disabled={typing} style={{ opacity: typing ? 0.4 : 1 }}>
            <SendIcon />
          </button>
        </div>

      </div>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   ROOT
══════════════════════════════════════════════════════════════════════════ */
export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('acme_token'))
  const [user,  setUser]  = useState(() => {
    const u = sessionStorage.getItem('acme_user')
    return u ? JSON.parse(u) : null
  })

  function handleLogin(newToken, newUser) {
    sessionStorage.setItem('acme_token', newToken)
    sessionStorage.setItem('acme_user',  JSON.stringify(newUser))
    setToken(newToken); setUser(newUser)
  }

  function handleSignOut() {
    sessionStorage.removeItem('acme_token')
    sessionStorage.removeItem('acme_user')
    setToken(null); setUser(null)
  }

  if (!token || !user) return <LoginPage onLogin={handleLogin} />
  return <ChatApp token={token} user={user} onSignOut={handleSignOut} />
}
