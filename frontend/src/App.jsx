import React, { useEffect, useMemo, useRef, useState } from 'react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function Badge({ status }) {
  const cls = String(status || '').toLowerCase().replaceAll(' ', '-')
  return <span className={`badge ${cls}`}>{status}</span>
}

function App() {
  const [page, setPage] = useState('Dashboard')
  const [history, setHistory] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const [lang, setLang] = useState('en')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [username, setUsername] = useState('inspector')
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [loggingIn, setLoggingIn] = useState(false)
    const [authMode, setAuthMode] = useState('login')
  const [cameraOpen, setCameraOpen] = useState(false)
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const fileInputRef = useRef(null)
  const [token, setToken] = useState(localStorage.getItem('smartpack_token') || '')

  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {}

  async function login(e) {

      async function register(e) {
        e.preventDefault(); setLoggingIn(true); setLoginError('')
        try {
          const r = await fetch(`${API}/api/auth/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })
          const data = await r.json()
          if (!r.ok) throw new Error(data.detail || 'Registration failed')
          setAuthMode('login'); setLoginError('Account created. Sign in with your new account.'); setPassword('')
        } catch (e) { setLoginError(e.message) } finally { setLoggingIn(false) }
      }
    e.preventDefault(); setLoggingIn(true); setLoginError('')
    try {
      const r = await fetch(`${API}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, password }) })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Login failed')
      localStorage.setItem('smartpack_token', data.access_token); setToken(data.access_token); setPassword('')
    } catch (e) { setLoginError(e.message) } finally { setLoggingIn(false) }
  }

  function logout() { localStorage.removeItem('smartpack_token'); setToken(''); setHistory([]); setAnalysis(null) }

  async function loadHistory() {
    try {
      const r = await fetch(`${API}/api/inspections`, { headers: authHeaders })
      if (r.ok) setHistory(await r.json())
    } catch (_) {}
  }

  useEffect(() => { if (token) loadHistory() }, [token])

  useEffect(() => () => streamRef.current?.getTracks().forEach(track => track.stop()), [])

  const stats = useMemo(() => ({
    total: history.length,
    compliant: history.filter(x => x.status === 'PASS').length,
    review: history.filter(x => x.status === 'LOW CONFIDENCE').length,
    flags: history.filter(x => (x.violations || []).length > 0).length,
  }), [history])

  async function chooseFile(e) {
    const f = e.target.files?.[0]
    if (!f) return
    setError('')
    try {
      const bitmap = await createImageBitmap(f)
      const canvas = document.createElement('canvas')
      canvas.width = bitmap.width; canvas.height = bitmap.height
      canvas.getContext('2d').drawImage(bitmap, 0, 0)
      bitmap.close()
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.92))
      if (!blob) throw new Error('Image conversion failed')
      const normalized = new File([blob], `smart-pack-${Date.now()}.jpg`, { type: 'image/jpeg' })
      setFile(normalized); setPreview(URL.createObjectURL(normalized)); setAnalysis(null)
    } catch (_) {
      setFile(f); setPreview(URL.createObjectURL(f)); setAnalysis(null)
    }
  }

  async function openCamera() {
    setError('')
    if (!window.isSecureContext) return setError('Live preview requires HTTPS or localhost. Use Device camera below to capture a photo over this LAN address.')
    if (!navigator.mediaDevices?.getUserMedia) return setError('Live camera is not available in this browser or connection.')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
      streamRef.current = stream
      setCameraOpen(true)
      requestAnimationFrame(() => { if (videoRef.current) videoRef.current.srcObject = stream })
    } catch (_) { setError('Camera permission was denied or the camera is unavailable.') }
  }

  function closeCamera() {
    streamRef.current?.getTracks().forEach(track => track.stop())
    streamRef.current = null
    setCameraOpen(false)
  }

  useEffect(() => {
    if (page !== 'Scan Product' && cameraOpen) closeCamera()
  }, [page, cameraOpen])

  useEffect(() => {
    if (cameraOpen && videoRef.current && streamRef.current) videoRef.current.srcObject = streamRef.current
  }, [cameraOpen])

  if (!token) return <Login mode={authMode} setMode={setAuthMode} username={username} password={password} setUsername={setUsername} setPassword={setPassword} loginError={loginError} loggingIn={loggingIn} onSubmit={authMode === 'login' ? login : register} />

  function captureCamera() {
    const video = videoRef.current
    if (!video?.videoWidth) return setError('Camera is still starting. Please try again.')
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth; canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(blob => {
      if (!blob) return setError('Could not capture the camera image.')
      const captured = new File([blob], `smart-pack-${Date.now()}.jpg`, { type: 'image/jpeg' })
      setFile(captured); setPreview(URL.createObjectURL(captured)); setAnalysis(null); setError(''); closeCamera()
    }, 'image/jpeg', 0.92)
  }

  async function analyze() {
    if (!file) return setError('Please upload or capture a package image first.')
    setLoading(true); setError('')
    try {
      const fd = new FormData(); fd.append('file', file)
      const r = await fetch(`${API}/api/analyze?lang=${lang}`, { method: 'POST', headers: authHeaders, body: fd })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail || 'Analysis failed')
      setAnalysis(data); await loadHistory(); setPage('Inspection')
    } catch (e) { setError(e.message) } finally { setLoading(false) }
  }

  function openInspection(item) { setAnalysis(item); setPage('Inspection') }
  function report(id) { window.open(`${API}/api/reports/${id}/pdf${token ? `?token=${encodeURIComponent(token)}` : ''}`, '_blank') }

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brandmark">S</div><div><b>Smart Pack</b><small>Legal Metrology AI</small></div></div>
      {['Dashboard','Scan Product','Inspection','History','Reports'].map(item => <button key={item} className={`nav ${page===item?'active':''}`} onClick={()=>setPage(item)}><span>{({Dashboard:'▦','Scan Product':'⌕',Inspection:'◫',History:'◷',Reports:'▤'})[item]}</span>{item}</button>)}
      <div className="side-note"><b>SIH 2026 MVP</b><span>AI-assisted packaged commodity compliance</span></div>
    </aside>

    <main className="main">
      <header><div><span className="crumb">Smart Pack / {page}</span><h1>{page}</h1></div><button className="user" onClick={logout}>● Inspector · Sign out</button></header>

      {page === 'Dashboard' && <>
        <section className="hero"><div><div className="eyebrow">LEGAL METROLOGY COMPLIANCE</div><h2>Scan. Analyze. Comply. Protect consumers.</h2><p>Upload a packaged-commodity label, extract declarations with OCR, run configurable rule checks, preserve evidence and generate a compliance assessment.</p></div><button className="primary" onClick={()=>setPage('Scan Product')}>＋ New Inspection</button></section>
        <section className="stats"><Stat title="Inspections" value={stats.total}/><Stat title="Compliant" value={stats.compliant}/><Stat title="Needs Review" value={stats.review}/><Stat title="With Review Flags" value={stats.flags}/></section>
        <section className="grid2"><div className="panel"><PanelHead title="Recent inspections" action="View all" onClick={()=>setPage('History')}/>{history.slice(0,6).map(x=><Row key={x.id} item={x} onClick={()=>openInspection(x)}/>)}{!history.length&&<Empty text="No inspections yet. Start with a product image."/>}</div><div className="panel"><h3>End-to-end workflow</h3><div className="steps">{['Camera / upload','PaddleOCR multilingual extraction','Category detection','LMPC rule repository','Font/readability review','Compliance scoring','Human review if uncertain','Evidence + PDF report'].map((x,i)=><div className="step" key={x}><span>{i+1}</span>{x}</div>)}</div></div></section>
      </>}

      {page === 'Scan Product' && <section className="panel scan"><div className="panelhead"><div><h2>Scan / Upload Package</h2><p className="muted">Use live camera detection or upload a clear front, back or side label image.</p></div></div><div className="scan-controls"><label>OCR language<select value={lang} onChange={e=>setLang(e.target.value)}><option value="en">English</option><option value="hi">Hindi</option><option value="ta">Tamil</option><option value="te">Telugu</option></select></label><div><button className="secondary" onClick={cameraOpen ? closeCamera : openCamera}>{cameraOpen ? 'Close camera' : 'Open live camera'}</button><button className="secondary" onClick={()=>fileInputRef.current?.click()}>Device camera</button></div></div>{cameraOpen&&<div className="camera-panel"><video ref={videoRef} autoPlay playsInline muted/><button className="primary" onClick={captureCamera}>Capture live image</button></div>}<label className="drop"><input ref={fileInputRef} type="file" accept="image/*" capture="environment" onChange={chooseFile}/>{preview?<img src={preview} alt="Selected package"/>:<><div className="camera">▣</div><b>Drop image here or choose a package image</b><span>All image formats · max 12 MB</span></>}</label>{error&&<div className="error">{error}</div>}<button className="primary big" onClick={analyze} disabled={loading}>{loading?'Analyzing image…':'Analyze Product'}</button><div className="tip"><b>Important:</b> This is an AI-assisted preliminary assessment. A flagged or passed result must be reviewed against the current applicable legal requirements before enforcement action.</div></section>}

      {page === 'Inspection' && <Inspection data={analysis} api={API} token={token} onReport={report} onNew={()=>setPage('Scan Product')}/>} 
      {page === 'History' && <section className="panel"><PanelHead title="Inspection History" action={`${history.length} records`}/>{history.map(x=><Row key={x.id} item={x} onClick={()=>openInspection(x)}/>)}{!history.length&&<Empty text="No records yet."/>}</section>}
      {page === 'Reports' && <section className="panel"><h2>Compliance Reports</h2><p className="muted">Evidence-backed PDF reports from completed inspections.</p>{history.map(x=><div className="reportrow" key={x.id}><div><b>{x.inspection_code || `Inspection #${x.id}`}</b><span>{x.category} · {new Date(x.created_at).toLocaleString()}</span></div><button onClick={()=>report(x.id)}>Download PDF</button></div>)}{!history.length&&<Empty text="Reports will appear after your first inspection."/>}</section>}
    </main>
  </div>
}

function Stat({title,value}){return <div className="stat"><span>{title}</span><strong>{value}</strong></div>}
function Login({mode,setMode,username,password,setUsername,setPassword,loginError,loggingIn,onSubmit}){const registering=mode==='register'; return <main className="login-shell"><form className="login-panel" onSubmit={onSubmit}><div className="brandmark">S</div><div className="eyebrow">SMART PACK</div><h1>{registering?'Create inspector account':'Inspector sign in'}</h1><p className="muted">{registering?'Create an account to manage inspections and reports.':'Access compliance inspections, evidence and reports.'}</p><label>Username<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" minLength="3" required/></label><label>Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete={registering?'new-password':'current-password'} minLength="8" required/></label>{loginError&&<div className="error">{loginError}</div>}<button className="primary big" disabled={loggingIn}>{loggingIn?(registering?'Creating account…':'Signing in…'):(registering?'Create account':'Sign in')}</button><button type="button" className="auth-switch" onClick={()=>{setMode(registering?'login':'register');setPassword('');}}>{registering?'Already have an account? Sign in':'Need an account? Register'}</button></form></main>}
function PanelHead({title,action,onClick}){return <div className="panelhead"><h3>{title}</h3>{action&&<button onClick={onClick}>{action}</button>}</div>}
function Row({item,onClick}){return <button className="row" onClick={onClick}><div className="dot">⌕</div><div className="rowmain"><b>{item.inspection_code || `#${item.id}`} · {item.category}</b><span>{new Date(item.created_at).toLocaleString()} · score {item.score}%</span></div><Badge status={item.status}/><span className="arrow">→</span></button>}
function Empty({text}){return <div className="empty">{text}</div>}

function Inspection({data,api,token,onReport,onNew}){
  if(!data) return <section className="emptybig"><div><h2>No inspection selected</h2><button className="primary" onClick={onNew}>Start inspection</button></div></section>
  const img = data.annotated_url || data.image_url
  return <section className="inspection">
    <div className="panel resulthead"><div><span className="eyebrow">{data.inspection_code || `INSPECTION #${data.id}`}</span><h2>{data.category}</h2><p className="muted">AI-assisted preliminary compliance assessment · {data.language}</p></div><Badge status={data.status}/></div>
    <div className="grid2"><div className="panel"><h3>Evidence image</h3>{img?<img className="evidence" src={`${api}${img}`}/>:<div className="placeholder">Image unavailable</div>}<div className="evidence-meta"><span>OCR confidence</span><b>{((data.ocr_confidence||0)*100).toFixed(0)}%</b></div></div><div className="panel"><h3>Extracted declarations</h3><div className="fields">{Object.entries(data.fields||{}).map(([k,v])=><div className="field" key={k}><span>{k.replaceAll('_',' ')}</span><b className={v?'found':'missing'}>{v||'Not detected'}</b></div>)}</div><div className="result-summary"><strong>{data.score}% {data.status === 'PASS' ? 'PASS' : 'REVIEW'}</strong><span>Calories, date, country and label declarations are shown from OCR evidence.</span></div></div></div>
    <div className="panel"><PanelHead title="Compliance checks" action={`${data.score}% score`}/>{(data.checks||[]).map(c=><div className="check" key={c.code}><div><b>{c.title}</b><span>{c.message}</span></div><Badge status={c.status}/></div>)}</div>
    <div className="panel"><h3>Violations / review items</h3>{(data.violations||[]).length ? data.violations.map((v,i)=><div className="violation" key={i}><b>{v.title}</b><span>{v.message}</span><small>Rule reference: {v.rule}</small></div>) : <div className="success">✓ No configured review flags detected. Human verification is still recommended.</div>}</div>
    <div className="panel"><h3>OCR text</h3><pre className="rawtext">{data.raw_text || 'No OCR text returned. Check image quality or OCR service logs.'}</pre></div>
    <div className="actions"><button className="secondary" onClick={onNew}>New inspection</button><button className="primary" onClick={()=>onReport(data.id)}>Download PDF report</button></div>
  </section>
}

export default App
