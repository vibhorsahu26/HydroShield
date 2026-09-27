import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, GitCompareArrows, LoaderCircle, PlayCircle, RefreshCw } from 'lucide-react'
import { useHydroShield } from '../state/HydroShieldContext'
import { formatModelName, formatStatus } from '../utils/formatters'

function formatNumber(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: digits })
}

function prettyMetricKey(key) { return formatStatus(key) }

function formatMetricValue(group, key, value) {
  if (value == null) return '—'
  if (key === 'iou') return `${formatNumber(Number(value) * 100, 2)}%`
  if (key.endsWith('_area_m2')) return `${formatNumber(value, 0)} m²`
  if (group === 'arrival_time') return `${formatNumber(value, 2)}`
  if (key === 'count') return formatNumber(value, 0)
  return formatNumber(value, 2)
}

const GROUP_META = {
  flood: { title: 'Flood extent', description: 'Inundation footprint comparison.' },
  depth: { title: 'Depth', description: 'Water-depth difference metrics.' },
  velocity: { title: 'Velocity', description: 'Flow-velocity difference metrics.' },
  arrival_time: { title: 'Arrival time', description: 'Flood-arrival-time difference metrics.' },
}

function variantLabel(item, variantsByScenario) {
  const variant = (variantsByScenario[item.scenario_id] || []).find((entry) => entry.id === item.variant_id)
  return formatStatus(variant?.preset || variant?.code || 'Scenario variant')
}

function labelForAnalysis(item, variantsByScenario) {
  return `${formatModelName(item.job?.model)} · ${variantLabel(item, variantsByScenario)} · ${item.id.slice(0, 8)}`
}

function ComparisonGroup({ group, metrics }) {
  const entries = Object.entries(metrics || {})
  const meta = GROUP_META[group] || { title: prettyMetricKey(group), description: 'Comparison metrics.' }
  return (
    <article className="rounded-2xl border border-sky-700/30 bg-white/75 p-4 min-w-0">
      <h3 className="text-sm font-black uppercase tracking-wide text-slate-800">{meta.title}</h3>
      <p className="mt-1 text-xs font-medium text-slate-500">{meta.description}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {entries.map(([key, value]) => (
          <div key={key} className="min-w-0 rounded-xl border border-sky-700/20 bg-sky-50/70 p-3">
            <div className="text-[0.68rem] font-bold uppercase tracking-wide text-slate-500">{prettyMetricKey(key)}</div>
            <div className="mt-1 break-words text-base font-black leading-6 text-slate-900">{formatMetricValue(group, key, value)}</div>
          </div>
        ))}
      </div>
    </article>
  )
}

function Comparision() {
  const { analyses, variantsByScenario, compareResults, createComparisonDemo, refreshSimulations } = useHydroShield()
  const [type, setType] = useState('scenario')
  const [left, setLeft] = useState('')
  const [right, setRight] = useState('')
  const [comparison, setComparison] = useState(null)
  const [demoRun, setDemoRun] = useState(null)
  const [busy, setBusy] = useState(false)
  const autoComparedRef = useRef(false)

  const compatibleAnalyses = useMemo(() => analyses.filter((item) => item.job?.status === 'completed'), [analyses])
  const compatiblePairs = useMemo(() => {
    if (type === 'model') {
      return compatibleAnalyses.filter((item) => compatibleAnalyses.some((other) => other.id !== item.id && other.variant_id === item.variant_id && other.job?.model !== item.job?.model))
    }
    return compatibleAnalyses.filter((item) => compatibleAnalyses.some((other) => other.id !== item.id && other.job?.model === item.job?.model && other.variant_id !== item.variant_id))
  }, [compatibleAnalyses, type])

  const sourceForDemo = useMemo(() => compatibleAnalyses.find((item) => item.job?.model === 'sph'), [compatibleAnalyses])

  useEffect(() => {
    setLeft((current) => current && compatiblePairs.some((item) => item.id === current) ? current : compatiblePairs[0]?.id || '')
  }, [compatiblePairs])

  useEffect(() => {
    const l = compatiblePairs.find((item) => item.id === left)
    const candidate = compatiblePairs.find((item) => item.id !== left && (type === 'scenario'
      ? item.job?.model === l?.job?.model && item.variant_id !== l?.variant_id
      : item.variant_id === l?.variant_id && item.job?.model !== l?.job?.model))
    setRight((current) => current && compatiblePairs.some((item) => item.id === current) ? current : candidate?.id || '')
  }, [compatiblePairs, left, type])

  useEffect(() => {
    if (!demoRun || type !== 'scenario' || autoComparedRef.current) return
    const pair = compatiblePairs.find((item) => item.variant_id !== sourceForDemo?.variant_id && item.job?.model === sourceForDemo?.job?.model)
    if (!pair || !sourceForDemo) return
    autoComparedRef.current = true
    setLeft(sourceForDemo.id)
    setRight(pair.id)
    compareResults({ left_analysis_id: sourceForDemo.id, right_analysis_id: pair.id, comparison_type: 'scenario' })
      .then((result) => {
        setComparison(result)
        try { sessionStorage.setItem('hydroshield.lastComparison.id', result.id) } catch { /* optional */ }
      })
      .catch(() => { autoComparedRef.current = false })
  }, [compatiblePairs, compareResults, demoRun, sourceForDemo, type])

  async function runComparison() {
    if (!left || !right) throw new Error('Choose two compatible analysis results.')
    setBusy(true)
    try {
      const result = await compareResults({ left_analysis_id: left, right_analysis_id: right, comparison_type: type })
      setComparison(result)
      try { sessionStorage.setItem('hydroshield.lastComparison.id', result.id) } catch { /* optional */ }
    } finally {
      setBusy(false)
    }
  }

  async function createScenarioComparison() {
    if (!sourceForDemo) throw new Error('Complete an SPH analysis first.')
    setBusy(true)
    setDemoRun(null)
    autoComparedRef.current = false
    try {
      const result = await createComparisonDemo(sourceForDemo.id)
      setDemoRun(result)
      await refreshSimulations()
    } finally {
      setBusy(false)
    }
  }

  const metricGroups = Object.entries(comparison?.metrics || {})
  const waitingForDemo = Boolean(demoRun && !comparison)

  return (
    <div className="space-y-4">
      <section className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/90 p-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-100 text-sky-700"><GitCompareArrows size={20} /></div>
          <div>
            <div className="text-xs font-bold uppercase tracking-[0.14em] text-sky-700">Analysis</div>
            <h1 className="text-3xl font-black">Model & Scenario Comparison</h1>
          </div>
        </div>
        <p className="mt-3 text-sm font-medium text-slate-600">Compare completed flood analyses on the same study grid.</p>
      </section>

      <section className="rounded-[20px] border-2 border-sky-700/70 bg-white/60 p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="grid flex-1 gap-4 lg:grid-cols-3">
            <label><span className="field-label">Comparison type</span><select value={type} onChange={(e) => { setType(e.target.value); setLeft(''); setRight(''); setComparison(null); setDemoRun(null); autoComparedRef.current = false }} className="field"><option value="scenario">Scenario</option><option value="model">Model</option></select></label>
            <label><span className="field-label">Left analysis</span><select value={left} onChange={(e) => setLeft(e.target.value)} className="field"><option value="">Select analysis</option>{compatiblePairs.map((item) => <option key={item.id} value={item.id}>{labelForAnalysis(item, variantsByScenario)}</option>)}</select></label>
            <label><span className="field-label">Right analysis</span><select value={right} onChange={(e) => setRight(e.target.value)} className="field"><option value="">Select analysis</option>{compatiblePairs.map((item) => <option key={item.id} value={item.id}>{labelForAnalysis(item, variantsByScenario)}</option>)}</select></label>
          </div>
          <button type="button" disabled={!left || !right || busy} onClick={() => runComparison().catch((e) => window.alert(e.message))} className="inline-flex items-center gap-2 rounded-xl bg-sky-700 px-4 py-3 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-45">
            {busy ? <LoaderCircle size={16} className="animate-spin" /> : <PlayCircle size={16} />} Compare
          </button>
        </div>

        {type === 'scenario' && compatiblePairs.length < 2 && !waitingForDemo && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-2xl border-2 border-cyan-300 bg-cyan-50 p-4">
            <div>
              <div className="flex items-center gap-2 text-sm font-black text-slate-900"><PlayCircle size={17} className="text-cyan-700" /> Create a second SPH scenario</div>
              <p className="mt-1 text-xs font-semibold text-slate-600">A comparison run will use another scenario variant on the same study.</p>
            </div>
            <button type="button" disabled={!sourceForDemo || busy} onClick={() => createScenarioComparison().catch((e) => window.alert(e.message))} className="inline-flex items-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-xs font-black text-slate-950 disabled:cursor-not-allowed disabled:opacity-45">
              {busy ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />} Prepare comparison run
            </button>
          </div>
        )}

        {demoRun && !comparison && (
          <div className="mt-4 flex items-center gap-3 rounded-2xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-xs font-bold text-emerald-900">
            <LoaderCircle size={16} className="animate-spin" /> {demoRun.comparison_variant_preset} is running. The comparison will appear automatically when analysis is ready.
          </div>
        )}
      </section>

      {comparison && (
        <section className="min-w-0 overflow-hidden rounded-[20px] border-2 border-sky-700/70 bg-sky-50/80 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-lg font-black"><CheckCircle2 size={19} className="text-emerald-600" /> Comparison complete</div>
              <p className="mt-1 text-xs font-medium text-slate-500">Right analysis minus left analysis for continuous rasters.</p>
            </div>
            <div className="rounded-full border border-sky-700/25 bg-white/70 px-3 py-1 text-xs font-bold tracking-wide text-sky-800">{comparison.comparison_type === 'model' ? 'Model comparison' : 'Scenario comparison'}</div>
          </div>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {metricGroups.map(([group, metrics]) => <ComparisonGroup key={group} group={group} metrics={metrics} />)}
          </div>
        </section>
      )}
    </div>
  )
}

export default Comparision
