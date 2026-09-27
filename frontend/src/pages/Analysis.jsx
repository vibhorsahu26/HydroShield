import { useEffect, useMemo, useState } from 'react'
import { FileDown, FlaskConical, GitCompareArrows, Satellite, ShieldCheck, Target } from 'lucide-react'
import { useHydroShield } from '../state/HydroShieldContext'
import { formatMetricName, formatModelName, formatStatus } from '../utils/formatters'

function FileInput({ label, file, onChange, required = false, accept = '.tif,.tiff,.csv' }) {
  return <label className="block"><span className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-600">{label}{required ? ' *' : ''}</span><span className="flex cursor-pointer items-center justify-between rounded-xl border-2 border-dashed border-sky-700/50 bg-white/50 px-3 py-2 text-sm font-semibold text-slate-600"><span className="min-w-0 truncate">{file?.name || 'Choose file'}</span><input className="sr-only" type="file" accept={accept} onChange={(e) => onChange(e.target.files?.[0] || null)} /></span></label>
}
function metricValue(metrics, key, suffix = '') { const value = metrics?.[key]; return Number.isFinite(value) ? `${Number(value).toFixed(2)}${suffix}` : '—' }
function floodAreaValue(metrics) { const km2 = metrics?.inundated_area_km2; if (Number.isFinite(km2)) return `${km2.toFixed(2)} km²`; const m2 = metrics?.inundated_area_m2; return Number.isFinite(m2) ? `${(m2 / 1e6).toFixed(2)} km²` : '—' }
function modelName(model) { return formatModelName(model) }
function formatDateInput(date) { return date.toISOString().slice(0, 10) }
function prettyMetric(key) { return formatMetricName(key) }
function agreementPercent(value) { return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '—' }

function Analysis() {
  const { jobs, analyses, datasets, analyzeSimulation, processNativeResult, uploadAnalysisInputs, compareResults, validateSatellite, satelliteValidations } = useHydroShield()
  const completed = useMemo(() => jobs.filter((job) => job.status === 'completed'), [jobs])
  const retryable = useMemo(() => jobs.filter((job) => ['completed', 'failed'].includes(job.status) && job.result?.postprocessing?.status === 'failed' && !job.result?.analysis_result_id), [jobs])
  const [jobId, setJobId] = useState('')
  const [files, setFiles] = useState({})
  const [threshold, setThreshold] = useState(0.05)
  const [result, setResult] = useState(null)
  const [satellite, setSatellite] = useState(() => {
    const end = new Date()
    const start = new Date(end)
    start.setDate(start.getDate() - 7)
    return { sensor: 'sentinel1', phase: 'during', startDate: formatDateInput(start), endDate: formatDateInput(end) }
  })
  const [satelliteBusy, setSatelliteBusy] = useState(false)
  const [satelliteError, setSatelliteError] = useState('')
  const [compareBusy, setCompareBusy] = useState(false)
  const [modelComparison, setModelComparison] = useState(null)
  useEffect(() => { if (!jobId && completed[0]) setJobId(completed[0].id) }, [completed, jobId])
  const selectedAnalysis = result || analyses.find((item) => item.simulation_job_id === jobId) || null

  async function runAnalysis() {
    if (!jobId || !files.water_depth_raster) throw new Error('Choose a completed simulation and water-depth GeoTIFF for manual result processing.')
    const uploaded = await uploadAnalysisInputs(jobId, files)
    const exposureLayers = {}
    for (const dataset of datasets) {
      const logicalType = dataset.source_metadata?.logical_type || dataset.logical_type
      if (dataset.dataset_type === 'settlement') exposureLayers.settlement = dataset.storage_uri
      if (dataset.dataset_type === 'infrastructure' && logicalType === 'road') exposureLayers.road = dataset.storage_uri
      if (dataset.dataset_type === 'infrastructure' && logicalType === 'bridge') exposureLayers.bridge = dataset.storage_uri
      if (dataset.dataset_type === 'infrastructure' && logicalType === 'critical_infrastructure') exposureLayers.critical_infrastructure = dataset.storage_uri
    }
    const analysis = await analyzeSimulation(jobId, { water_depth_raster: uploaded.files.water_depth_raster, velocity_raster: uploaded.files.velocity_raster, arrival_time_raster: uploaded.files.arrival_time_raster, water_level_raster: uploaded.files.water_level_raster, dem_raster: uploaded.files.dem_raster, discharge_csv: uploaded.files.discharge_csv, exposure_layers: exposureLayers, flood_threshold_m: Number(threshold) })
    setResult(analysis)
  }
  async function runSatellite() {
    if (!selectedAnalysis) throw new Error('Create or select an analysis result first.')
    if (!satellite.startDate || !satellite.endDate) throw new Error('Choose both satellite observation dates.')
    setSatelliteBusy(true); setSatelliteError('')
    try {
      await validateSatellite({ analysis_result_id: selectedAnalysis.id, sensor: satellite.sensor, phase: satellite.phase, start_date: satellite.startDate, end_date: satellite.endDate })
      await new Promise((resolve) => window.setTimeout(resolve, 1100))
    }
    catch (error) { setSatelliteError(error.message || 'Satellite validation failed.') }
    finally { setSatelliteBusy(false) }
  }
  const latestSat = satelliteValidations.find((item) => item.analysis_result_id === selectedAnalysis?.id)

  const modelPairs = useMemo(() => {
    const byJobModel = (analysis) => analysis.job?.model || jobs.find((job) => job.id === analysis.simulation_job_id)?.model
    const sph = analyses.filter((item) => byJobModel(item) === 'sph')
    const delft = analyses.filter((item) => byJobModel(item) === 'delft3d')
    const delftByVariant = new Map(delft.map((item) => [item.variant_id, item]))
    return sph.map((left) => {
      const right = delftByVariant.get(left.variant_id)
      return right ? { left, right } : null
    }).filter(Boolean).sort((a, b) => new Date(b.left.created_at).getTime() - new Date(a.left.created_at).getTime())
  }, [analyses, jobs])

  async function runModelComparison() {
    const pair = modelPairs[0]
    if (!pair) return
    setCompareBusy(true)
    try {
      const comparison = await compareResults({ left_analysis_id: pair.left.id, right_analysis_id: pair.right.id, comparison_type: 'model' })
      setModelComparison(comparison)
    } catch (error) {
      window.alert(error.message || 'Model comparison failed.')
    } finally {
      setCompareBusy(false)
    }
  }

  return <div className="space-y-4">
    <section className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/85 p-6"><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-100 text-sky-700"><FlaskConical size={20} /></div><div><div className="text-xs font-bold uppercase tracking-[0.14em] text-sky-700">Flood Analysis</div><h1 className="text-3xl font-black tracking-[-0.05em] text-slate-900">Analysis & Satellite Validation</h1></div></div><p className="mt-3 max-w-3xl text-sm font-medium text-slate-600">Process model outputs, review flood impacts, and compare the modeled flood footprint with satellite observations.</p></section>
    <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
      <section className="rounded-[20px] border-2 border-sky-700/70 bg-white/50 p-5"><h2 className="text-lg font-black text-slate-800">Create analysis result</h2><p className="mt-1 text-xs font-semibold text-slate-500">HydroShield-generated runs can be processed automatically. Manual result upload remains available.</p><label className="mt-4 block"><span className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-600">Completed simulation</span><select value={jobId} onChange={(e) => setJobId(e.target.value)} className="field"><option value="">Select job</option>{completed.map((job) => <option key={job.id} value={job.id}>{modelName(job.model)} · {job.id.slice(0, 8)} · Completed</option>)}{retryable.map((job) => <option key={job.id} value={job.id}>{modelName(job.model)} · {job.id.slice(0, 8)} · Retry processing</option>)}</select></label>
        {jobId && ['sph', 'delft3d'].includes((completed.find((job) => job.id === jobId) || retryable.find((job) => job.id === jobId))?.model) && <div className="mt-4 rounded-2xl border-2 border-emerald-600/50 bg-emerald-50 p-4"><div className="text-xs font-bold uppercase tracking-wide text-emerald-700">Automatic result processing</div><p className="mt-1 text-sm font-semibold text-emerald-950">Generate the common flood-depth, velocity, arrival-time and flood-extent artifacts from this completed model run.</p><button type="button" onClick={() => processNativeResult(jobId, { flood_threshold_m: Number(threshold), force: true }).catch((e) => window.alert(e.message))} className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-700 px-4 py-3 text-sm font-bold text-white">Process {modelName((completed.find((job) => job.id === jobId) || retryable.find((job) => job.id === jobId))?.model)} output</button></div>}
        <div className="mt-4 grid gap-3 sm:grid-cols-2"><FileInput label="Water depth GeoTIFF" required file={files.water_depth_raster} onChange={(f) => setFiles((x) => ({ ...x, water_depth_raster: f }))} /><FileInput label="Velocity GeoTIFF" file={files.velocity_raster} onChange={(f) => setFiles((x) => ({ ...x, velocity_raster: f }))} /><FileInput label="Arrival time GeoTIFF" file={files.arrival_time_raster} onChange={(f) => setFiles((x) => ({ ...x, arrival_time_raster: f }))} /><FileInput label="Water level GeoTIFF" file={files.water_level_raster} onChange={(f) => setFiles((x) => ({ ...x, water_level_raster: f }))} /><FileInput label="DEM GeoTIFF" file={files.dem_raster} onChange={(f) => setFiles((x) => ({ ...x, dem_raster: f }))} /><FileInput label="Discharge CSV" accept=".csv" file={files.discharge_csv} onChange={(f) => setFiles((x) => ({ ...x, discharge_csv: f }))} /></div>
        <label className="mt-4 block"><span className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-600">Flood threshold (m)</span><input type="number" min="0" step="0.01" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="field" /></label>
        <button type="button" onClick={() => runAnalysis().catch((e) => window.alert(e.message))} className="mt-5 flex items-center gap-2 rounded-xl bg-sky-700 px-4 py-3 text-sm font-bold text-white"><FileDown size={16} /> Process Result</button>
      </section>
      <section className="rounded-[20px] border-2 border-sky-700/70 bg-sky-50/80 p-5"><div className="flex items-center gap-2"><Target size={18} className="text-sky-700" /><h2 className="text-lg font-black text-slate-800">Latest analysis</h2></div>{selectedAnalysis ? <><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">{[['Flood area', floodAreaValue(selectedAnalysis.metrics)], ['Max depth', metricValue(selectedAnalysis.metrics, 'max_water_depth_m', ' m')], ['Max velocity', metricValue(selectedAnalysis.metrics, 'max_velocity_mps', ' m/s')], ['Arrival', Number.isFinite(selectedAnalysis.metrics?.first_arrival_time_s) ? `${(selectedAnalysis.metrics.first_arrival_time_s / 60).toFixed(1)} min` : '—'], ['Threshold', `${selectedAnalysis.flood_threshold_m} m`], ['Analysis', selectedAnalysis.id.slice(0, 8)]].map(([l, v]) => <div key={l} className="rounded-2xl border-2 border-sky-700/50 bg-white/50 p-3"><div className="text-[0.68rem] font-bold uppercase text-slate-500">{l}</div><div className="mt-1 text-xl font-black text-slate-800">{v}</div></div>)}</div><div className="mt-5 rounded-2xl border border-sky-700/40 bg-white/40 p-3 text-xs font-semibold text-slate-600">Analysis artifacts are ready for mapping and export.</div></> : <div className="mt-4 rounded-xl border border-dashed border-sky-700/40 p-6 text-sm font-semibold text-slate-500">No analysis result selected.</div>}</section>
    </div>

    <section className="rounded-[20px] border-2 border-sky-700/70 bg-white/50 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-sky-700"><GitCompareArrows size={15} /> Model comparison</div>
          <h2 className="mt-1 text-xl font-black text-slate-900">SPH vs Delft3D</h2>
          <p className="mt-1 text-xs font-semibold text-slate-500">Compare both model results for the same scenario.</p>
        </div>
        <button type="button" disabled={!modelPairs.length || compareBusy} onClick={runModelComparison} className="rounded-xl bg-sky-700 px-4 py-2.5 text-xs font-black text-blue-700 disabled:cursor-not-allowed disabled:opacity-45">{compareBusy ? 'Comparing…' : 'Compare Models'}</button>
      </div>
      {!modelPairs.length ? (
        <div className="mt-4 rounded-xl border border-dashed border-sky-700/30 bg-slate-50 p-4 text-sm font-semibold text-slate-500">Complete one SPH and one Delft3D analysis for the same scenario to compare them.</div>
      ) : modelComparison ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[['Flood IoU', modelComparison.metrics?.flood?.iou], ['Depth MAE', modelComparison.metrics?.depth?.mae], ['Velocity MAE', modelComparison.metrics?.velocity?.mae], ['Arrival MAE', modelComparison.metrics?.arrival_time?.mae]].map(([label, value]) => (
            <div key={label} className="rounded-2xl border-2 border-sky-700/30 bg-sky-50/70 p-3"><div className="text-[0.68rem] font-bold uppercase text-slate-500">{label}</div><div className="mt-1 text-xl font-black text-slate-900">{Number.isFinite(value) ? (label === 'Flood IoU' ? `${(value * 100).toFixed(2)}%` : Number(value).toFixed(2)) : '—'}</div></div>
          ))}
        </div>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-sky-700/20 bg-sky-50 p-3"><div className="text-xs font-bold text-slate-700">SPH result</div><div className="mt-1 text-sm font-black text-slate-900">{modelPairs[0].left.id.slice(0, 8)}</div></div>
          <div className="rounded-xl border border-sky-700/20 bg-sky-50 p-3"><div className="text-xs font-bold text-slate-700">Delft3D result</div><div className="mt-1 text-sm font-black text-slate-900">{modelPairs[0].right.id.slice(0, 8)}</div></div>
        </div>
      )}
    </section>

    <section className="rounded-[20px] border-2 border-sky-700/80 p-5 text-blue-950 shadow-lg"><div className="flex flex-wrap items-center justify-between gap-3"><div><div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-blue-950"><Satellite size={15} /> Satellite validation</div><h2 className="mt-1 text-xl font-black">Observed flood agreement</h2><p className="mt-1 max-w-2xl text-xs font-medium text-blue-950">Compare the modeled flood footprint with a satellite-derived observed extent.</p></div>{latestSat && <div className="flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-black text-blue-950"><ShieldCheck size={14} /> Validation ready</div>}</div>
      {!selectedAnalysis ? <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-sm font-semibold text-blue-950">Complete a flood analysis to activate satellite validation.</div> : <>
        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto]"><label><span className="mb-2 block text-[0.68rem] font-bold uppercase text-blue-950">Sensor</span><select value={satellite.sensor} onChange={(e) => setSatellite((x) => ({ ...x, sensor: e.target.value }))} className="field"><option value="sentinel1">Sentinel-1</option><option value="sentinel2">Sentinel-2</option></select></label><label><span className="mb-2 block text-[0.68rem] font-bold uppercase text-slate-400">Start date</span><input type="date" value={satellite.startDate} onChange={(e) => setSatellite((x) => ({ ...x, startDate: e.target.value }))} className="field" /></label><label><span className="mb-2 block text-[0.68rem] font-bold uppercase text-slate-400">End date</span><input type="date" value={satellite.endDate} onChange={(e) => setSatellite((x) => ({ ...x, endDate: e.target.value }))} className="field" /></label><button type="button" onClick={() => runSatellite()} disabled={satelliteBusy} className="self-end rounded-xl bg-cyan-400 px-4 py-3 text-sm font-black text-slate-950 disabled:opacity-50">{satelliteBusy ? 'Validating…' : 'Validate Flood Extent'}</button></div>
        {satelliteError && <div className="mt-3 rounded-xl border border-rose-300/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-200">{satelliteError}</div>}
        {latestSat ? <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[['IoU', agreementPercent(latestSat.metrics?.iou)], ['Precision', agreementPercent(latestSat.metrics?.precision)], ['Recall', agreementPercent(latestSat.metrics?.recall)], ['F1 Score', agreementPercent(latestSat.metrics?.f1)], ['Model area', `${((latestSat.metrics?.model_area_m2 || 0) / 1e6).toFixed(2)} km²`], ['Observed area', `${((latestSat.metrics?.observed_area_m2 || 0) / 1e6).toFixed(2)} km²`], ['Overlap', `${((latestSat.metrics?.intersection_area_m2 || 0) / 1e6).toFixed(2)} km²`], ['Images', `${latestSat.image_count}`]].map(([l, v]) => <div key={l} className="rounded-2xl border border-white/10 bg-white/5 p-3"><div className="text-[0.68rem] font-bold uppercase text-slate-400">{l}</div><div className="mt-1 text-xl font-black text-white">{v}</div></div>)}</div> : <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-xs font-semibold text-slate-300">Ready to compare the modeled flood extent with satellite observations.</div>}
        {latestSat && <div className="mt-4 grid gap-2 sm:grid-cols-3"><div className="rounded-xl border border-emerald-400/20 bg-emerald-400/5 px-3 py-2"><div className="text-xs font-bold text-emerald-200">Observed flood extent</div><div className="mt-1 text-[0.68rem] text-slate-300">Available on the Dashboard validation layer.</div></div><div className="rounded-xl border border-sky-400/20 bg-sky-400/5 px-3 py-2"><div className="text-xs font-bold text-sky-200">Comparison map</div><div className="mt-1 text-[0.68rem] text-slate-300">Difference zones are stored with the validation result.</div></div><div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"><div className="text-xs font-bold text-slate-200">Observation</div><div className="mt-1 text-[0.68rem] text-slate-400">{latestSat.image_count} imagery scenes evaluated</div></div></div>}
      </>}
    </section>
  </div>
}
export default Analysis
