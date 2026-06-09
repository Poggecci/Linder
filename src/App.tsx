// src/App.tsx
import { useState, useEffect, useRef } from 'react'
import { Routes, Route, useNavigate, useParams, useLocation } from 'react-router-dom'
import { Heart, X, MessageSquare, Send, Bell, RefreshCw, User, LogOut, ChevronRight, Volume2, Shield } from 'lucide-react'

// VAPID Public Key from the backend config
const VAPID_PUBLIC_KEY = "BAKAqMDXe_hYBTXKvGDxC07cbGzD0sWYgd_242ROKPGD4xh3uaMdx0xZMResnX2Bjp6O0VF7BwWV8189ydnDl2M"

// Types
interface Candidate {
  user_id: string
  riot_id: string
  champion_name: string
  kills: number
  deaths: number
  assists: number
  win: boolean
  cs: number
}

interface Message {
  id: string
  senderId: string
  senderName: string
  content: string
  createdAt: string
}

interface ToastMessage {
  id: string
  text: string
  type: 'info' | 'success' | 'error'
}

// Helpers
function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const outputArray = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i)
  }
  return outputArray
}

// Synthesize League of Legends-like matchmaking chime using Web Audio API
const playMatchSound = () => {
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext
    if (!AudioContextClass) return
    const ctx = new AudioContextClass()
    
    // Play a premium major-triad chime (LoL match-found style)
    const playTone = (freq: number, start: number, duration: number) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      
      osc.type = 'sine'
      osc.frequency.setValueAtTime(freq, start)
      
      gain.gain.setValueAtTime(0.25, start)
      gain.gain.exponentialRampToValueAtTime(0.001, start + duration)
      
      osc.connect(gain)
      gain.connect(ctx.destination)
      
      osc.start(start)
      osc.stop(start + duration)
    }
    
    playTone(440, ctx.currentTime, 0.4) // A4
    playTone(554.37, ctx.currentTime + 0.1, 0.4) // C#5
    playTone(659.25, ctx.currentTime + 0.2, 0.8) // E5
  } catch (e) {
    console.error("Audio Context playback failed", e)
  }
}

// Global App State wrapper
export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  
  // Auth State
  const [token, setToken] = useState<string | null>(localStorage.getItem('linder_token'))
  const [userId, setUserId] = useState<string | null>(localStorage.getItem('linder_user_id'))
  const [riotId, setRiotId] = useState<string | null>(localStorage.getItem('linder_riot_id'))
  
  // PWA & Notification State
  const [swRegistration, setSwRegistration] = useState<ServiceWorkerRegistration | null>(null)
  const [isSubscribed, setIsSubscribed] = useState(false)
  const [subscribing, setSubscribing] = useState(false)
  
  // Matchmaking Proposal State
  const [proposalId, setProposalId] = useState<string | null>(null)
  const [proposalExpiresIn, setProposalExpiresIn] = useState<number>(30)
  const [proposalActive, setProposalActive] = useState<boolean>(false)
  const [accepting, setAccepting] = useState<boolean>(false)
  
  // Keep track of the current matched candidate to display in the lobby later
  const [matchedCandidate, setMatchedCandidate] = useState<Candidate | null>(null)
  
  // Toast System
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  
  const showToast = (text: string, type: 'info' | 'success' | 'error' = 'info') => {
    const id = Math.random().toString(36).substring(2, 9)
    setToasts(prev => [...prev, { id, text, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }

  // Base API path
  const getApiUrl = (path: string) => {
    const apiBase = import.meta.env.VITE_API_URL || ''
    const base = apiBase.endsWith('/') ? apiBase.slice(0, -1) : apiBase
    const normalizedPath = path.startsWith('/') ? path : `/${path}`
    return `${base}${normalizedPath}`
  }

  // Fetch API headers
  const getHeaders = () => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    return headers
  }

  // Register Service Worker
  useEffect(() => {
    const registerSW = async () => {
      if ('serviceWorker' in navigator) {
        try {
          const base = import.meta.env.BASE_URL || '/linder/'
          const reg = await navigator.serviceWorker.register(`${base}sw.js`, { scope: base })
          console.log('Service Worker registered successfully with scope:', reg.scope)
          setSwRegistration(reg)
          
          // Check if subscription exists
          const subscription = await reg.pushManager.getSubscription()
          setIsSubscribed(!!subscription)
        } catch (error) {
          console.error('Service worker registration failed:', error)
        }
      }
    }
    
    registerSW()
  }, [])

  // Listen to Service Worker postMessage
  useEffect(() => {
    const handleSWMessage = (event: MessageEvent) => {
      const data = event.data
      console.log('Received SW postMessage:', data)
      
      if (!data) return
      
      switch (data.type) {
        case 'MATCH_PROPOSED':
          // Display the 30-Second Countdown Modal lock
          setProposalId(data.proposal_id)
          setProposalExpiresIn(data.expires_in || 30)
          setProposalActive(true)
          setAccepting(false)
          playMatchSound()
          if (navigator.vibrate) {
            navigator.vibrate([200, 100, 200])
          }
          showToast("Reciprocal LIKE Match Proposed!", "success")
          break
          
        case 'MATCH_SUCCESS':
          // Partner accepted, match success!
          setProposalActive(false)
          setAccepting(false)
          setProposalId(null)
          showToast("Match Connected!", "success")
          navigate(`/lobby/${data.lobby_id}`)
          break
          
        case 'MATCH_DECLINED':
          // Either party declined
          setProposalActive(false)
          setAccepting(false)
          setProposalId(null)
          showToast("Partner declined connection", "error")
          break
          
        case 'NAVIGATE':
          // Handle native notification banner click redirects
          if (data.url) {
            // E.g. /match/accept?id=PROPOSAL_ID
            const match = data.url.match(/id=([^&]+)/)
            if (match && match[1]) {
              setProposalId(match[1])
              setProposalExpiresIn(30)
              setProposalActive(true)
              setAccepting(false)
              playMatchSound()
            }
          }
          break
      }
    }
    
    navigator.serviceWorker.addEventListener('message', handleSWMessage)
    return () => {
      navigator.serviceWorker.removeEventListener('message', handleSWMessage)
    }
  }, [navigate])

  // Check for proposal ID in the URL on mount or hash change
  useEffect(() => {
    const checkUrlForProposal = () => {
      const hashParts = window.location.hash.split('?')
      const queryStr = hashParts[1] || (window.location.search ? window.location.search.substring(1) : '')
      if (queryStr) {
        const params = new URLSearchParams(queryStr)
        const propId = params.get('id')
        if (propId) {
          setProposalId(propId)
          setProposalExpiresIn(30)
          setProposalActive(true)
          setAccepting(false)
          playMatchSound()
          
          // Clear query param so we don't loop on refresh
          const hashWithoutParams = hashParts[0]
          navigate(hashWithoutParams.replace(/^#/, ''), { replace: true })
          showToast("Match request loaded from notification!", "success")
        }
      }
    }
    
    // Only check if logged in
    if (token) {
      checkUrlForProposal()
      window.addEventListener('hashchange', checkUrlForProposal)
    }
    return () => window.removeEventListener('hashchange', checkUrlForProposal)
  }, [token, navigate])

  // Notification Push Subscription flow
  const subscribeToPush = async () => {
    if (!swRegistration) {
      showToast("Service worker not active yet", "error")
      return
    }
    setSubscribing(true)
    try {
      // Request permission
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        showToast("Notification permission denied", "error")
        setSubscribing(false)
        return
      }
      
      // Subscribe
      const subscription = await swRegistration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
      })
      
      // Send to server
      const response = await fetch(getApiUrl('/api/v1/notifications/subscribe'), {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify(subscription)
      })
      
      if (response.ok) {
        setIsSubscribed(true)
        showToast("Push notifications enabled!", "success")
      } else {
        const err = await response.json()
        showToast(`Failed to register push: ${err.detail || 'Error'}`, "error")
      }
    } catch (error) {
      console.error("Web Push Subscription failed:", error)
      showToast("Could not subscribe. Proceeding with in-app notifications.", "info")
    } finally {
      setSubscribing(false)
    }
  }

  // Handle Log Out
  const handleLogout = () => {
    localStorage.removeItem('linder_token')
    localStorage.removeItem('linder_user_id')
    localStorage.removeItem('linder_riot_id')
    setToken(null)
    setUserId(null)
    setRiotId(null)
    navigate('/')
    showToast("Logged out successfully", "info")
  }

  return (
    <div className="app-container">
      {/* Toast Overlay */}
      <div className="toast-container">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast ${toast.type === 'error' ? 'error' : toast.type === 'success' ? 'success' : ''}`}>
            <span>{toast.text}</span>
          </div>
        ))}
      </div>

      {/* Global 30-Second Overlay Modal Lock */}
      {proposalActive && proposalId && (
        <ProposalModal
          proposalId={proposalId}
          expiresIn={proposalExpiresIn}
          accepting={accepting}
          setAccepting={setAccepting}
          onClose={() => {
            setProposalActive(false)
            setProposalId(null)
          }}
          getHeaders={getHeaders}
          getApiUrl={getApiUrl}
          showToast={showToast}
          navigate={navigate}
          matchedCandidate={matchedCandidate}
        />
      )}

      {/* App Header */}
      {token && (
        <header className="app-header">
          <div className="header-logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>Linder</div>
          <div className="header-status">
            <span className="status-indicator"></span>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              {riotId || 'Summoner'}
            </span>
            <button className="icon-btn" onClick={handleLogout} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '4px' }}>
              <LogOut size={16} />
            </button>
          </div>
        </header>
      )}

      {/* Notification status bar if not subscribed */}
      {token && !isSubscribed && (
        <div className="notification-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Bell size={14} />
            <span>Enable W3C Web Push for real-time matches</span>
          </div>
          <button className="notification-bar-btn" disabled={subscribing} onClick={subscribeToPush}>
            {subscribing ? 'Enabling...' : 'Enable'}
          </button>
        </div>
      )}

      {/* Main Routing Screen */}
      <Routes>
        <Route path="/" element={
          token ? (
            <SwipeDeck
              getHeaders={getHeaders}
              getApiUrl={getApiUrl}
              showToast={showToast}
              setProposalId={setProposalId}
              setProposalExpiresIn={setProposalExpiresIn}
              setProposalActive={setProposalActive}
              setMatchedCandidate={setMatchedCandidate}
            />
          ) : (
            <LoginScreen
              setToken={setToken}
              setUserId={setUserId}
              setRiotId={setRiotId}
              getApiUrl={getApiUrl}
              showToast={showToast}
            />
          )
        } />
        
        <Route path="/lobby/:lobbyId" element={
          token ? (
            <ChatLobby
              userId={userId || 'usr_me'}
              riotId={riotId || 'Me'}
              matchedCandidate={matchedCandidate}
            />
          ) : (
            <LoginScreen
              setToken={setToken}
              setUserId={setUserId}
              setRiotId={setRiotId}
              getApiUrl={getApiUrl}
              showToast={showToast}
            />
          )
        } />
      </Routes>

      {/* Developer Testing / Simulation Panel */}
      <DevTestingPanel
        token={token}
        setToken={setToken}
        setUserId={setUserId}
        setRiotId={setRiotId}
        getApiUrl={getApiUrl}
        showToast={showToast}
        setProposalId={setProposalId}
        setProposalExpiresIn={setProposalExpiresIn}
        setProposalActive={setProposalActive}
        playMatchSound={playMatchSound}
      />
    </div>
  )
}

// ======================== COMPONENTS ========================

// 1. LOGIN SCREEN
interface LoginProps {
  setToken: (t: string) => void
  setUserId: (id: string) => void
  setRiotId: (id: string) => void
  getApiUrl: (path: string) => string
  showToast: (text: string, type?: 'info' | 'success' | 'error') => void
}

function LoginScreen({ setToken, setUserId, setRiotId, getApiUrl, showToast }: LoginProps) {
  const [puuid, setPuuid] = useState('')
  const [riotName, setRiotName] = useState('')
  const [riotTag, setRiotTag] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!puuid || !riotName || !riotTag) {
      showToast("Please fill all fields", "error")
      return
    }

    setLoading(true)
    try {
      const response = await fetch(getApiUrl('/api/v1/auth/token'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          puuid,
          riot_id_name: riotName,
          riot_id_tag: riotTag
        })
      })

      if (response.ok) {
        const data = await response.json()
        localStorage.setItem('linder_token', data.access_token)
        localStorage.setItem('linder_user_id', data.user_id)
        localStorage.setItem('linder_riot_id', `${riotName}#${riotTag}`)
        
        setToken(data.access_token)
        setUserId(data.user_id)
        setRiotId(`${riotName}#${riotTag}`)
        showToast("Welcome to the Rift!", "success")
      } else {
        const err = await response.json()
        showToast(`Registration failed: ${err.detail || 'Error'}`, "error")
      }
    } catch (error) {
      console.error(error)
      showToast("Connection to backend failed", "error")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="screen centered-screen">
      <div style={{ textAlign: 'center', marginBottom: '32px' }}>
        <h1 style={{ fontSize: '3rem', fontWeight: 800, letterSpacing: '4px', textTransform: 'uppercase', background: 'linear-gradient(135deg, #f0e6d2 0%, #c89b3c 50%, #785a28 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', filter: 'drop-shadow(0 0 10px rgba(200, 155, 60, 0.2))' }}>Linder</h1>
        <div style={{ color: 'var(--teal-light)', fontSize: '0.8rem', letterSpacing: '6px', fontWeight: 600, textTransform: 'uppercase', marginTop: '-4px' }}>Matchmaking client</div>
      </div>

      <div className="glass-panel">
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}>
          <div className="form-group">
            <label className="form-label">Riot PUUID</label>
            <input 
              className="text-input" 
              type="text" 
              placeholder="e.g. puuid_faker" 
              value={puuid}
              onChange={(e) => setPuuid(e.target.value)}
              disabled={loading}
            />
          </div>
          
          <div style={{ display: 'flex', gap: '12px' }}>
            <div className="form-group" style={{ flex: 2 }}>
              <label className="form-label">Riot Name</label>
              <input 
                className="text-input" 
                type="text" 
                placeholder="Faker" 
                value={riotName}
                onChange={(e) => setRiotName(e.target.value)}
                disabled={loading}
              />
            </div>
            
            <div className="form-group" style={{ flex: 1 }}>
              <label className="form-label">Tagline</label>
              <input 
                className="text-input" 
                type="text" 
                placeholder="KR1" 
                value={riotTag}
                onChange={(e) => setRiotTag(e.target.value)}
                disabled={loading}
              />
            </div>
          </div>

          <button className="gold-button" style={{ marginTop: '12px' }} disabled={loading}>
            {loading ? (
              <span className="loading-spinner"></span>
            ) : (
              <>
                <span>Enter the Rift</span>
                <ChevronRight size={18} />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}

// 2. SWIPE DECK
interface SwipeDeckProps {
  getHeaders: () => Record<string, string>
  getApiUrl: (path: string) => string
  showToast: (text: string, type?: 'info' | 'success' | 'error') => void
  setProposalId: (id: string) => void
  setProposalExpiresIn: (s: number) => void
  setProposalActive: (b: boolean) => void
  setMatchedCandidate: (c: Candidate) => void
}

function SwipeDeck({ getHeaders, getApiUrl, showToast, setProposalId, setProposalExpiresIn, setProposalActive, setMatchedCandidate }: SwipeDeckProps) {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [matchId, setMatchId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [swipeClass, setSwipeClass] = useState<string>('') // Anim class

  const fetchCandidates = async () => {
    setLoading(true)
    try {
      const response = await fetch(getApiUrl('/api/v1/candidates'), {
        headers: getHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        setCandidates(data.candidates || [])
        setMatchId(data.match_id || '')
      } else {
        const err = await response.json()
        showToast(`Failed to load candidates: ${err.detail || 'Error'}`, "error")
      }
    } catch (e) {
      console.error(e)
      showToast("Backend connection failed", "error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCandidates()
  }, [])

  const handleSwipe = async (action: 'LIKE' | 'PASS') => {
    if (candidates.length === 0 || swipeClass) return
    
    const candidate = candidates[0]
    
    // Set swipe animation trigger
    setSwipeClass(action === 'LIKE' ? 'swipe-right-anim' : 'swipe-left-anim')
    
    // Execute API swipe in parallel/background
    try {
      const response = await fetch(getApiUrl('/api/v1/swipes'), {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          target_user_id: candidate.user_id,
          action: action
        })
      })

      if (response.ok) {
        const data = await response.json()
        
        // Wait for animation to finish before removing candidate from list
        setTimeout(() => {
          setCandidates(prev => prev.slice(1))
          setSwipeClass('')
          
          if (data.matched) {
            // reciprocal like, match created!
            setMatchedCandidate(candidate)
            setProposalId(data.proposal_id)
            setProposalExpiresIn(data.expires_in_seconds || 30)
            setProposalActive(true)
            playMatchSound()
            if (navigator.vibrate) {
              navigator.vibrate([200, 100, 200])
            }
          }
        }, 300)
      } else {
        const err = await response.json()
        showToast(`Swipe failed: ${err.detail || 'Error'}`, "error")
        setSwipeClass('')
      }
    } catch (e) {
      console.error(e)
      showToast("Swipe connection failed", "error")
      setSwipeClass('')
    }
  }

  if (loading) {
    return (
      <div className="screen centered-screen">
        <RefreshCw className="spinner" style={{ color: 'var(--gold)', width: '36px', height: '36px' }} />
        <p style={{ marginTop: '16px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Searching recent matches...</p>
      </div>
    )
  }

  const currentCandidate = candidates[0]

  return (
    <div className="screen" style={{ justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '1.2rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Recent Teammates</h2>
        {matchId && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            <span>Match:</span>
            <code style={{ color: 'var(--teal-light)' }}>{matchId}</code>
          </div>
        )}
      </div>

      <div className="swipe-deck-container">
        {currentCandidate ? (
          <div className="candidate-card-wrapper">
            <div className={`candidate-card ${swipeClass} ${currentCandidate.win ? 'win-theme' : 'loss-theme'}`}>
              
              {/* Card Header */}
              <div className="card-top">
                <div className="champion-display">
                  <div className="champion-name">{currentCandidate.champion_name}</div>
                  <div className="summoner-name">{currentCandidate.riot_id}</div>
                </div>
                <div className={`match-badge ${currentCandidate.win ? 'win' : 'defeat'}`}>
                  {currentCandidate.win ? 'Victory' : 'Defeat'}
                </div>
              </div>

              {/* Card Stats Grid */}
              <div className="card-stats-grid">
                <div className="stat-item">
                  <span className="stat-label">Performance</span>
                  <span className="stat-value kda">
                    {currentCandidate.kills}/{currentCandidate.deaths}/{currentCandidate.assists}
                  </span>
                </div>
                
                <div className="stat-item">
                  <span className="stat-label">KDA Ratio</span>
                  <span className="stat-value" style={{ color: '#fff' }}>
                    {currentCandidate.deaths === 0 
                      ? ((currentCandidate.kills + currentCandidate.assists)).toFixed(1) + ' (Perfect)'
                      : ((currentCandidate.kills + currentCandidate.assists) / currentCandidate.deaths).toFixed(2)
                    }
                  </span>
                </div>

                <div className="stat-item">
                  <span className="stat-label">Farm</span>
                  <span className="stat-value cs">{currentCandidate.cs} CS</span>
                </div>

                <div className="stat-item">
                  <span className="stat-label">Match Rank</span>
                  <span className="stat-value" style={{ color: 'var(--gold-light)' }}>S+</span>
                </div>
              </div>

              {/* Card CTA Swipes */}
              <div className="card-actions">
                <button className="action-btn pass" onClick={() => handleSwipe('PASS')} title="Swipe Left (Pass)">
                  <X size={28} />
                </button>
                <button className="action-btn like" onClick={() => handleSwipe('LIKE')} title="Swipe Right (Like)">
                  <Heart size={28} fill="currentColor" />
                </button>
              </div>

            </div>
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-icon">👑</div>
            <h3 className="empty-title">All Caught Up</h3>
            <p className="empty-desc">No more players from your recent match are on Linder. Queue up again to find more partners!</p>
            <button className="secondary-button" onClick={fetchCandidates} style={{ marginTop: '12px' }}>
              <RefreshCw size={14} />
              <span>Refresh Candidates</span>
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// 3. 30-SECOND COUNTDOWN MATCH OVERLAY MODAL LOCK
interface ProposalModalProps {
  proposalId: string
  expiresIn: number
  accepting: boolean
  setAccepting: (b: boolean) => void
  onClose: () => void
  getHeaders: () => Record<string, string>
  getApiUrl: (path: string) => string
  showToast: (text: string, type?: 'info' | 'success' | 'error') => void
  navigate: (path: string) => void
  matchedCandidate: Candidate | null
}

function ProposalModal({ proposalId, expiresIn, accepting, setAccepting, onClose, getHeaders, getApiUrl, showToast, navigate, matchedCandidate }: ProposalModalProps) {
  const [timeLeft, setTimeLeft] = useState(expiresIn)
  const timerRef = useRef<number | null>(null)

  // Circular timer constants
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference - (timeLeft / 30) * circumference

  useEffect(() => {
    setTimeLeft(expiresIn)
    
    timerRef.current = window.setInterval(() => {
      setTimeLeft(prev => {
        if (prev <= 1) {
          clearInterval(timerRef.current!)
          onClose()
          showToast("Match request expired", "error")
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [proposalId, expiresIn])

  const handleAction = async (action: 'ACCEPT' | 'DECLINE') => {
    if (action === 'ACCEPT') {
      setAccepting(true)
    } else {
      if (timerRef.current) clearInterval(timerRef.current)
      onClose()
    }

    try {
      const response = await fetch(getApiUrl('/api/v1/match/respond'), {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          proposal_id: proposalId,
          action: action
        })
      })

      if (response.ok) {
        const data = await response.json()
        if (action === 'DECLINE') {
          showToast("Match declined", "info")
        } else if (data.status === 'SUCCESS') {
          if (timerRef.current) clearInterval(timerRef.current)
          onClose()
          showToast("Match Connected!", "success")
          navigate(`/lobby/${data.lobby_id}`)
        } else if (data.status === 'PENDING') {
          // Keep showing waiting spinner, let SW message trigger navigation on partner ACCEPT
          showToast("Accepted! Waiting for partner...", "info")
        } else if (data.status === 'DECLINED') {
          if (timerRef.current) clearInterval(timerRef.current)
          onClose()
          showToast("Partner declined connection", "error")
        }
      } else {
        const err = await response.json()
        showToast(`Action failed: ${err.detail || 'Error'}`, "error")
        setAccepting(false)
      }
    } catch (e) {
      console.error(e)
      showToast("Response execution failed", "error")
      setAccepting(false)
    }
  }

  const isWarning = timeLeft <= 10

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-title">Match Found!</div>
        
        {matchedCandidate ? (
          <div style={{ color: 'var(--gold-light)', fontWeight: 600 }}>
            Connect with {matchedCandidate.riot_id} ({matchedCandidate.champion_name})?
          </div>
        ) : (
          <div className="modal-subtitle">A player from your last match wants to connect. You have 30 seconds to accept!</div>
        )}

        {/* Circular Countdown Progress */}
        <div className="timer-container">
          <svg className="timer-circle-svg">
            <circle className="timer-circle-bg" cx="60" cy="60" r={radius} />
            <circle 
              className={`timer-circle-progress ${isWarning ? 'warning' : ''}`} 
              cx="60" 
              cy="60" 
              r={radius} 
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
            />
          </svg>
          <div className={`timer-text ${isWarning ? 'warning' : ''}`}>{timeLeft}</div>
        </div>

        <div className="modal-actions">
          <button 
            className="gold-button" 
            style={{ width: '100%' }} 
            disabled={accepting} 
            onClick={() => handleAction('ACCEPT')}
          >
            {accepting ? (
              <>
                <span className="loading-spinner"></span>
                <span style={{ marginLeft: '8px' }}>Waiting for Partner...</span>
              </>
            ) : (
              'Accept Connection'
            )}
          </button>
          
          <button 
            className="secondary-button" 
            style={{ width: '100%', borderColor: 'rgba(232, 64, 64, 0.4)', color: 'var(--red)' }} 
            disabled={accepting} 
            onClick={() => handleAction('DECLINE')}
          >
            Decline
          </button>
        </div>
      </div>
    </div>
  )
}

// 4. CHAT LOBBY VIEW (WITH MOCK CHAT BOT)
interface ChatLobbyProps {
  userId: string
  riotId: string
  matchedCandidate: Candidate | null
}

function ChatLobby({ userId, riotId, matchedCandidate }: ChatLobbyProps) {
  const navigate = useNavigate()
  const { lobbyId } = useParams()
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const messageEndRef = useRef<HTMLDivElement | null>(null)
  
  // Extract partner name from candidate info or default
  const partnerName = matchedCandidate ? matchedCandidate.riot_id : "Rift Partner"
  const partnerChampion = matchedCandidate ? matchedCandidate.champion_name : "Champion"
  const isPartnerWin = matchedCandidate ? matchedCandidate.win : true
  const partnerKDA = matchedCandidate ? `${matchedCandidate.kills}/${matchedCandidate.deaths}/${matchedCandidate.assists}` : "10/2/8"

  // Simulator bot dialogues
  const botReplies = [
    `Nice! Your play last game was solid. Ready to queue up again?`,
    `I usually play mid or support. What lanes do you run?`,
    `Add me on League client! Let's get on Discord voice.`,
    `Do you want to run draft pick or ranked? I'm trying to climb.`,
    `I can lock in ${partnerChampion} or try something else. What do you think?`,
    `Awesome. Send me a friend request, my Riot ID is ${partnerName}!`,
  ]
  const botReplyIndex = useRef(0)

  // Auto-scroll chat log
  useEffect(() => {
    if (messageEndRef.current) {
      messageEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  // Trigger welcome message
  useEffect(() => {
    const welcomeTimer = setTimeout(() => {
      const welcomeMessage: Message = {
        id: 'w1',
        senderId: 'partner',
        senderName: partnerName,
        content: `Hey! Good game last match on the Rift. ${isPartnerWin ? "Glad we got that Victory!" : "Unlucky loss, but we did our best."} My stats were ${partnerKDA} on ${partnerChampion}. Let's team up!`,
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      setMessages([welcomeMessage])
    }, 1000)

    return () => clearTimeout(welcomeTimer)
  }, [partnerName, partnerChampion, isPartnerWin, partnerKDA])

  const handleSend = () => {
    if (!inputValue.trim()) return

    const userMessage: Message = {
      id: Math.random().toString(),
      senderId: userId,
      senderName: riotId.split('#')[0],
      content: inputValue,
      createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')

    // Trigger mock bot response after 2 seconds
    setTimeout(() => {
      const replyText = botReplies[botReplyIndex.current % botReplies.length]
      botReplyIndex.current++
      
      const botMessage: Message = {
        id: Math.random().toString(),
        senderId: 'partner',
        senderName: partnerName.split('#')[0],
        content: replyText,
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      }
      
      setMessages(prev => [...prev, botMessage])
    }, 2000)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSend()
    }
  }

  return (
    <div className="lobby-screen">
      {/* Lobby Header */}
      <div className="lobby-header">
        <div className="partner-avatar">
          {partnerName[0].toUpperCase()}
        </div>
        <div className="partner-info">
          <div className="partner-name">{partnerName}</div>
          <div className="partner-status">
            <span className="partner-status-dot"></span>
            <span>Online • Played {partnerChampion}</span>
          </div>
        </div>
        <button className="secondary-button" style={{ padding: '8px 12px', fontSize: '0.8rem' }} onClick={() => navigate('/')}>
          Leave Lobby
        </button>
      </div>

      {/* Message Area */}
      <div className="chat-message-list">
        {messages.map(msg => {
          const isMe = msg.senderId === userId
          return (
            <div key={msg.id} className={`message-bubble-wrapper ${isMe ? 'sent' : 'received'}`}>
              <div className="message-bubble">
                {msg.content}
              </div>
              <div className="message-meta">
                {msg.senderName} • {msg.createdAt}
              </div>
            </div>
          )
        })}
        <div ref={messageEndRef} />
      </div>

      {/* Input Area */}
      <div className="chat-input-area">
        <input 
          className="chat-input"
          type="text" 
          placeholder="Message teammate..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
        />
        <button className="send-btn" disabled={!inputValue.trim()} onClick={handleSend}>
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}

// 5. DEVELOPER SIMULATOR AND SHORTCUTS
interface DevPanelProps {
  token: string | null
  setToken: (t: string | null) => void
  setUserId: (id: string | null) => void
  setRiotId: (id: string | null) => void
  getApiUrl: (path: string) => string
  showToast: (text: string, type?: 'info' | 'success' | 'error') => void
  setProposalId: (id: string) => void
  setProposalExpiresIn: (s: number) => void
  setProposalActive: (b: boolean) => void
  playMatchSound: () => void
}

function DevTestingPanel({ token, setToken, setUserId, setRiotId, getApiUrl, showToast, setProposalId, setProposalExpiresIn, setProposalActive, playMatchSound }: DevPanelProps) {
  const [isOpen, setIsOpen] = useState(true)

  const handleQuickLogin = async (userType: 'usr_1' | 'usr_2') => {
    const isUser1 = userType === 'usr_1'
    const puuid = isUser1 ? "puuid_user_1" : "puuid_user_2"
    const riotName = isUser1 ? "User_1" : "User_2"
    const riotTag = "NA1"

    try {
      const response = await fetch(getApiUrl('/api/v1/auth/token'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          puuid,
          riot_id_name: riotName,
          riot_id_tag: riotTag
        })
      })

      if (response.ok) {
        const data = await response.json()
        localStorage.setItem('linder_token', data.access_token)
        localStorage.setItem('linder_user_id', data.user_id)
        localStorage.setItem('linder_riot_id', `${riotName}#${riotTag}`)

        setToken(data.access_token)
        setUserId(data.user_id)
        setRiotId(`${riotName}#${riotTag}`)
        showToast(`Logged in as Mock ${riotName}!`, "success")
      } else {
        showToast("Mock Auth registration failed", "error")
      }
    } catch (e) {
      console.error(e)
      showToast("Mock Auth server error. Attempting bypass offline tokens.", "info")
      
      // Offline fallback bypass
      const mockToken = `mock_token_user_${userType}`
      localStorage.setItem('linder_token', mockToken)
      localStorage.setItem('linder_user_id', userType)
      localStorage.setItem('linder_riot_id', `${riotName}#${riotTag}`)

      setToken(mockToken)
      setUserId(userType)
      setRiotId(`${riotName}#${riotTag}`)
    }
  }

  const simulateLocalPush = () => {
    // Generate a mock proposal ID and trigger the modal locally for instant review
    const mockPropId = Math.random().toString(36).substring(2, 9)
    setProposalId(mockPropId)
    setProposalExpiresIn(30)
    setProposalActive(true)
    playMatchSound()
    if (navigator.vibrate) {
      navigator.vibrate([200, 100, 200])
    }
    showToast("Simulating MATCH_PROPOSED push notification!", "info")
  }

  return (
    <div className="dev-shortcuts-drawer">
      <div className="dev-shortcuts-header" onClick={() => setIsOpen(!isOpen)} style={{ cursor: 'pointer' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Shield size={14} style={{ color: 'var(--gold)' }} />
          <span>Local Simulation Console</span>
        </div>
        <span style={{ fontSize: '0.75rem' }}>{isOpen ? 'Collapse [-]' : 'Expand [+]'}</span>
      </div>

      {isOpen && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '4px' }}>
          <div className="dev-buttons">
            <button className="dev-btn" onClick={() => handleQuickLogin('usr_1')}>
              Mock Login: User 1
            </button>
            <button className="dev-btn" onClick={() => handleQuickLogin('usr_2')}>
              Mock Login: User 2
            </button>
          </div>
          
          {token && (
            <button className="dev-btn" style={{ width: '100%', borderColor: 'rgba(0, 151, 196, 0.4)' }} onClick={simulateLocalPush}>
              ⚡ Trigger "Match Found" (Overlay Countdown)
            </button>
          )}
        </div>
      )}
    </div>
  )
}
