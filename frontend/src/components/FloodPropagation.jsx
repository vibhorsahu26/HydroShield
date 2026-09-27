import { useEffect, useMemo, useState } from 'react'
import { Pause, Play, RotateCcw, Waves } from 'lucide-react'
import { api, API_BASE_URL } from '../api/client'

function formatTime(seconds) {
  const value = Number(seconds) || 0
  if (value < 60) return `${Math.round(value)} sec`
  const minutes = value / 60
  if (minutes < 60) return `${minutes.toFixed(minutes % 1 ? 1 : 0)} min`
  return `${(minutes / 60).toFixed(1)} hr`
}

function FloodPropagation({ jobId, stats, durationMinutes = 60, onFrameChange }) {
  const [timeline, setTimeline] = useState(null)
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    setTimeline(null); setIndex(0); setPlaying(false); setError(''); onFrameChange?.(null)
    if (!jobId) return () => { alive = false }
    api.getSimulationTimeline(jobId).then((payload) => payload)
      .then((payload) => {
        if (!alive) return
        setTimeline(payload)
        if (payload.frames?.length) {
          onFrameChange?.(payload.frames[0])
          setPlaying(true)
        }
      })
      .catch((err) => alive && setError(err.message || 'Flood propagation is unavailable.'))
    return () => { alive = false }
  }, [jobId, onFrameChange])

  useEffect(() => {
    if (!playing || !timeline?.frames?.length) return undefined
    const timer = window.setInterval(() => {
      setIndex((current) => {
        const next = current + 1
        const wrapped = next >= timeline.frames.length ? 0 : next
        onFrameChange?.(timeline.frames[wrapped])
        return wrapped
      })
    }, 900)
    return () => window.clearInterval(timer)
  }, [playing, timeline, onFrameChange])

  const frame = timeline?.frames?.[index] || null
  const progress = useMemo(() => timeline?.frames?.length ? ((index + 1) / timeline.frames.length) * 100 : 0, [index, timeline])

  function chooseFrame(nextIndex) {
    setIndex(nextIndex)
    const next = timeline?.frames?.[nextIndex]
    if (next) onFrameChange?.(next)
  }

  return <section className="rounded-[20px] border-2 border-sky-700/70 bg-white/85 p-4 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2 text-[0.68rem] font-black uppercase tracking-[0.14em] text-sky-700"><Waves size={14}/> Flood propagation</div>
        <h3 className="mt-1 text-xl font-black text-slate-900">Water-depth timeline</h3>
        <p className="mt-1 text-xs font-semibold text-slate-500">Step through time-indexed depth fields from the completed run.</p>
      </div>
      {frame && <div className="rounded-xl border border-sky-700/20 bg-sky-50 px-3 py-2 text-right"><div className="text-[0.62rem] font-black uppercase text-slate-500">Current time</div><div className="text-lg font-black text-slate-900">{formatTime(frame.time_s)}</div></div>}
    </div>

    {!jobId && <div className="mt-4 rounded-xl border border-dashed border-sky-700/30 bg-slate-50 p-5 text-center text-xs font-semibold text-slate-500">Run a simulation to load propagation frames.</div>}
    {jobId && !timeline?.available && !error && <div className="mt-4 rounded-2xl border border-sky-700/15 bg-slate-50 p-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[['Release', '0 min'], ['Downstream arrival', `${stats?.arrivalTime !== '—' ? stats.arrivalTime : Math.max(8, Math.round(durationMinutes * 0.28))} min`], ['Maximum depth', stats?.maxDepth !== '—' ? `${stats.maxDepth} m` : '—'], ['Final extent', stats?.floodArea !== '—' ? `${stats.floodArea} km²` : '—']].map(([label, value]) => <div key={label} className="rounded-xl border border-sky-700/15 bg-white px-3 py-2"><div className="text-[0.6rem] font-black uppercase tracking-wide text-slate-400">{label}</div><div className="mt-1 text-sm font-black text-slate-800">{value}</div></div>)}
      </div>
      <div className="mt-2 text-[0.67rem] font-semibold text-slate-500">Propagation summary is available; time-indexed solver frames will replace this view when provided by the run.</div>
    </div>}
    {error && <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs font-bold text-amber-900">{error}</div>}

    {timeline?.available && frame && <>
      <div className="mt-4 overflow-hidden rounded-2xl border border-sky-700/25 bg-slate-950">
        <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2 text-[0.65rem] font-bold text-slate-300"><span>Frame {index + 1} / {timeline.frames.length}</span><span>{formatTime(frame.time_s)}</span></div>
        <div className="flex items-center justify-center bg-slate-900 p-3"><img src={`${API_BASE_URL}${frame.image_path}${String(frame.image_path).includes("?") ? "&" : "?"}frame=${index}`} alt={`Flood depth propagation at ${formatTime(frame.time_s)}`} className="max-h-[260px] w-full object-contain" /></div>
        <div className="px-3 pb-3 pt-2"><div className="h-2 overflow-hidden rounded-full bg-slate-700"><div className="h-full rounded-full bg-cyan-400 transition-all" style={{ width: `${progress}%` }}/></div></div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setPlaying((value) => !value)} className="inline-flex items-center gap-2 rounded-xl border-2 border-sky-700/60 bg-sky-50 px-3 py-2 text-xs font-black text-sky-800">{playing ? <Pause size={14}/> : <Play size={14}/>} {playing ? 'Pause' : 'Play'}</button>
        <button type="button" onClick={() => chooseFrame(0)} className="inline-flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700"><RotateCcw size={14}/> Reset</button>
        <input aria-label="Flood propagation timeline" type="range" min="0" max={Math.max(0, timeline.frames.length - 1)} value={index} onChange={(event) => chooseFrame(Number(event.target.value))} className="min-w-[180px] flex-1 accent-sky-600" />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-[0.66rem] font-bold text-slate-500"><span>Start · {formatTime(timeline.frames[0].time_s)}</span><span className="text-center">{formatTime(timeline.frames[Math.floor(timeline.frames.length / 2)].time_s)}</span><span className="text-right">Final frame · {formatTime(timeline.frames.at(-1).time_s)}</span></div>
    </>}
  </section>
}

export default FloodPropagation
