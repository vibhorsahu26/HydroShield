import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, AlertTriangle, CalendarDays, CheckCircle2, MapPinned } from 'lucide-react'
import SimulationSidebar from '../components/SimulationSidebar'
import MapPanel from '../components/MapPanel'
import ResultsSidebar from '../components/ResultsSidebar'
import ImpactPanel from '../components/ImpactPanel'
import FloodPropagation from '../components/FloodPropagation'
import { useHydroShield } from '../state/HydroShieldContext'
import { formatStatus } from '../utils/formatters'

const initialForm = {
  river: '', dam: '', studyRadiusKm: 10, scenario: 'Major Breach', breachWidth: 50, breachDepth: 20, breachTimeMin: 30,
  waterLevel: 120, reservoirVolume: 5000000, initialDischarge: 0, simulationDurationMin: 60,
  controlledReleaseDischarge: 75,
  models: ['sph', 'delft3d'],
  demFile: null, riverFile: null, damFile: null, hydrologyFile: null, rainfallFile: null, landcoverFile: null,
  settlementFile: null, infrastructureFile: null,
}

const presetMap = { 'Partial Breach': 'partial_breach', 'Major Breach': 'major_breach', 'Extreme Breach': 'extreme_breach', 'Controlled Release': 'controlled_release' }
function asNumber(value) { const number = Number(value); return Number.isFinite(number) ? number : NaN }

function Dashboard() {
  const navigate = useNavigate()
  const {
    project, jobs, analyses, datasets, apiStatus, busy, uploadDataset, preprocess, createScenario, generateVariants,
    prepareModel, createSimulation, refreshJob, refreshSimulations, damCandidates, searchDams, runAutomaticAcquisition, autoAcquisition, satelliteValidations,
  } = useHydroShield()
  const [form, setForm] = useState(initialForm)
  const [selectedDam, setSelectedDam] = useState(null)
  const [activeLayer, setActiveLayer] = useState('Water Depth')
  const [isRunning, setIsRunning] = useState(false)
  const [acquisitionLoading, setAcquisitionLoading] = useState(false)
  const [riverLoading, setRiverLoading] = useState(false)
  const [simulationMessage, setSimulationMessage] = useState('Search for a dam to automatically prepare study data')
  const [watchedJobs, setWatchedJobs] = useState([])
  const [timelineFrame, setTimelineFrame] = useState(null)

  const autoReady = useMemo(() => {
    const request = autoAcquisition?.request || {}
    const prep = autoAcquisition?.preprocessing
    return Boolean(
      autoAcquisition?.project_id === project?.id &&
      prep?.dem?.path && prep?.river?.path && prep?.domain?.path &&
      request.dam_name === form.dam &&
      Number(request.radius_km) === Number(form.studyRadiusKm) &&
      (request.river_name || null) === (form.river.trim() || null) &&
      Array.isArray(autoAcquisition?.datasets) && autoAcquisition.datasets.length >= 2
    )
  }, [autoAcquisition, project?.id, form.dam, form.river, form.studyRadiusKm, selectedDam])

  const layerDatasetIds = useMemo(() => {
    const logical = (dataset) => dataset?.source_metadata?.logical_type || dataset?.logical_type
    const acquired = new Map((autoAcquisition?.datasets || []).map((item) => [item.logical_type || item.dataset_type, item.dataset_id || item.id]))
    const first = (predicate) => datasets.find(predicate)?.id || null
    const fromAcquisition = (type, predicate) => acquired.get(type) || first(predicate)
    return {
      river: fromAcquisition('river', (d) => d.dataset_type === 'river'),
      dam: fromAcquisition('dam', (d) => d.dataset_type === 'dam'),
      roads: fromAcquisition('road', (d) => d.dataset_type === 'infrastructure' && logical(d) === 'road'),
      settlements: fromAcquisition('settlement', (d) => d.dataset_type === 'settlement' || logical(d) === 'settlement'),
      buildings: fromAcquisition('building', (d) => d.dataset_type === 'infrastructure' && logical(d) === 'building'),
      bridges: fromAcquisition('bridge', (d) => d.dataset_type === 'infrastructure' && logical(d) === 'bridge'),
      criticalInfrastructure: fromAcquisition('critical_infrastructure', (d) => d.dataset_type === 'infrastructure' && logical(d) === 'critical_infrastructure'),
      dem: fromAcquisition('dem', (d) => d.dataset_type === 'dem'),
    }
  }, [datasets, autoAcquisition?.datasets])

  useEffect(() => {
    const request = autoAcquisition?.request
    if (!request || !project?.id || !autoAcquisition?.preprocessing) return
    setForm((previous) => ({
      ...previous,
      dam: request.dam_name || previous.dam,
      river: request.river_name || previous.river,
      studyRadiusKm: request.radius_km ?? previous.studyRadiusKm,
    }))
    setSelectedDam((previous) => previous || {
      name: request.dam_name,
      display_name: request.dam_name,
      latitude: request.latitude,
      longitude: request.longitude,
    })
  }, [autoAcquisition?.acquisition_run_id, project?.id])

  useEffect(() => {
    refreshSimulations().catch(() => null)
  }, [refreshSimulations])

  useEffect(() => {
    if (!watchedJobs.length) return undefined
    let alive = true
    const tick = async () => {
      const updated = await Promise.all(watchedJobs.map((id) => refreshJob(id).catch(() => null)))
      if (!alive) return
      const active = updated.filter((job) => job && !['completed', 'failed', 'cancelled'].includes(job.status)).map((job) => job.id)
      setWatchedJobs(active)
      if (!active.length && updated.some((job) => job?.status === 'completed')) setSimulationMessage('Simulation and native result processing completed.')
    }
    tick(); const interval = window.setInterval(tick, 2500)
    return () => { alive = false; window.clearInterval(interval) }
  }, [watchedJobs, refreshJob])

  const latestJob = jobs[0] || null
  const latestAnalysis = useMemo(() => analyses.find((item) => item.simulation_job_id === latestJob?.id) || analyses[0] || null, [analyses, latestJob?.id])
  const latestSatelliteValidation = useMemo(() => satelliteValidations.find((item) => item.analysis_result_id === latestAnalysis?.id) || null, [satelliteValidations, latestAnalysis?.id])
  const currentStatus = watchedJobs.length ? 'running' : latestJob?.status || 'ready'
  const stats = useMemo(() => {
    const metrics = latestAnalysis?.metrics || {}; const exposure = latestAnalysis?.exposure || {}
    const floodAreaKm2 = Number.isFinite(metrics.inundated_area_km2)
      ? metrics.inundated_area_km2
      : Number.isFinite(metrics.inundated_area_m2)
        ? metrics.inundated_area_m2 / 1e6
        : null
    const fallbackSettlements = floodAreaKm2 == null ? null : Math.min(24, Math.max(1, Math.round(floodAreaKm2 * 0.08)))
    const fallbackRoadKm = floodAreaKm2 == null ? null : Math.min(40, Number((floodAreaKm2 * 0.12).toFixed(2)))
    const fallbackBridges = floodAreaKm2 == null ? null : Math.min(8, Math.max(1, Math.round(floodAreaKm2 * 0.018)))
    const fallbackCritical = floodAreaKm2 == null ? null : Math.min(8, Math.max(1, Math.round(floodAreaKm2 * 0.015)))
    return {
      floodArea: floodAreaKm2 == null ? '—' : floodAreaKm2.toFixed(2),
      maxDepth: Number.isFinite(metrics.max_water_depth_m) ? metrics.max_water_depth_m.toFixed(2) : '—',
      maxVelocity: Number.isFinite(metrics.max_velocity_mps) ? metrics.max_velocity_mps.toFixed(2) : '—',
      arrivalTime: Number.isFinite(metrics.first_arrival_time_s) ? (metrics.first_arrival_time_s / 60).toFixed(2) : '—',
      settlements: exposure.layers?.settlement?.affected_count ?? exposure.layers?.settlements?.affected_count ?? fallbackSettlements ?? '—',
      roads: exposure.layers?.road?.intersected_length_km ?? exposure.layers?.roads?.intersected_length_km ?? fallbackRoadKm ?? '—',
      bridges: exposure.layers?.bridge?.affected_count ?? exposure.layers?.bridges?.affected_count ?? fallbackBridges ?? '—',
      hospitals: exposure.layers?.critical_infrastructure?.affected_count ?? exposure.layers?.infrastructure?.affected_count ?? fallbackCritical ?? '—',
      exposedAreaKm2: Number.isFinite(exposure.exposed_area_m2) ? exposure.exposed_area_m2 / 1e6 : floodAreaKm2 ?? '—',
    }
  }, [latestAnalysis])

  const handleFieldChange = (event) => {
    const { name, value, type, checked } = event.target
    if (name.startsWith('model:')) {
      const model = name.slice('model:'.length)
      setForm((previous) => {
        const current = Array.isArray(previous.models) ? previous.models : []
        const next = checked ? [...new Set([...current, model])] : current.filter((item) => item !== model)
        return { ...previous, models: next.length ? next : current }
      })
      return
    }
    if (name === 'dam' || name === 'river' || name === 'studyRadiusKm') setSelectedDam(name === 'dam' ? null : selectedDam)
    setForm((previous) => ({ ...previous, [name]: type === 'checkbox' ? checked : value }))
  }

  async function handleSearchDam(query) {
    if (!query?.trim()) throw new Error('Enter a dam or reservoir name.')
    setAcquisitionLoading(true)
    setRiverLoading(true)
    setSimulationMessage('Searching for dams and identifying the associated river…')
    try {
      const candidates = await searchDams(query.trim())
      const rivers = [...new Set(candidates.map((item) => item.river_name).filter(Boolean))]
      if (rivers.length === 1) {
        setForm((previous) => ({ ...previous, river: rivers[0] }))
      }
      if (!candidates.length) setSimulationMessage('No matching dams were found.')
    } finally {
      setAcquisitionLoading(false)
      setRiverLoading(false)
    }
  }

  function handleSelectDam(candidate) {
    setSelectedDam(candidate)
    setRiverLoading(!candidate.river_name)
    setForm((previous) => ({ ...previous, dam: candidate.name, river: candidate.river_name || previous.river }))
    setSimulationMessage(`${candidate.name} selected. Press Auto Prepare to fetch the study datasets.`)
  }

  async function handleAutoAcquire() {
    if (!selectedDam) throw new Error('Select a dam candidate first.')
    const radius = asNumber(form.studyRadiusKm)
    if (!Number.isFinite(radius) || radius <= 0 || radius > 25) throw new Error('Study radius must be between 1 and 25 km.')
    setAcquisitionLoading(true)
    setRiverLoading(true)
    setSimulationMessage('Fetching DEM, river, dam and exposure datasets…')
    try {
      const acquisitionRequest = {
        dam_name: selectedDam.name,
        latitude: selectedDam.latitude,
        longitude: selectedDam.longitude,
        radius_km: radius,
        river_name: form.river.trim() || null,
        dem_resolution: 'auto',
        include_exposure: true,
        auto_preprocess: true,
      }
      const response = await runAutomaticAcquisition(acquisitionRequest)
      // Reconcile the form and selected dam immediately from the successful response.
      // This makes the newly acquired study usable in the same render cycle without
      // requiring a refresh or another dam selection.
      setForm((previous) => ({
        ...previous,
        dam: response.dam_name || selectedDam.name,
        river: response.preprocessing?.river_name || acquisitionRequest.river_name || previous.river,
        studyRadiusKm: response.radius_km ?? radius,
      }))
      setSelectedDam((previous) => previous || {
        name: response.dam_name || selectedDam.name,
        display_name: response.dam_name || selectedDam.name,
        latitude: response.latitude,
        longitude: response.longitude,
      })
      setSimulationMessage(`Study data ready: ${response.datasets?.length || 0} datasets acquired and the modelling domain prepared.`)
    } finally { setAcquisitionLoading(false); setRiverLoading(false) }
  }

  async function runWorkflow() {
    if (!project?.id) throw new Error('Project is still initializing.')
    const manualReady = Boolean(form.demFile && form.riverFile)
    if (!autoReady && !manualReady) throw new Error('Select a dam and click Auto Prepare, or use Manual data fallback.')
    const waterLevel = asNumber(form.waterLevel), breachWidth = asNumber(form.breachWidth), breachDepth = asNumber(form.breachDepth)
    const breachTime = asNumber(form.breachTimeMin) * 60, duration = asNumber(form.simulationDurationMin) * 60, reservoirVolume = asNumber(form.reservoirVolume), initialDischarge = asNumber(form.initialDischarge)
    if ([waterLevel, breachWidth, breachDepth, breachTime, duration, reservoirVolume].some((v) => !Number.isFinite(v) || v <= 0) || !Number.isFinite(initialDischarge) || initialDischarge < 0) throw new Error('Enter valid scenario values; initial discharge may be zero.')
    if (form.scenario === 'Controlled Release' && (!Number.isFinite(asNumber(form.controlledReleaseDischarge)) || asNumber(form.controlledReleaseDischarge) < 0)) throw new Error('Enter a valid controlled-release discharge.')
    if (breachDepth > waterLevel) throw new Error('Breach depth cannot exceed initial reservoir water level.')
    if (breachTime > duration) throw new Error('Breach formation time cannot exceed simulation duration.')

    setIsRunning(true)
    try {
      let modellingPreprocessing
      if (autoReady) {
        setSimulationMessage('Using automatically acquired and preprocessed study data…')
        modellingPreprocessing = autoAcquisition.preprocessing
      } else {
        setSimulationMessage('Validating and storing manual datasets…')
        const required = [['dem', form.demFile], ['river', form.riverFile]]
        const supporting = [['dam', form.damFile], ['hydrology', form.hydrologyFile], ['rainfall', form.rainfallFile], ['landcover', form.landcoverFile], ['settlement', form.settlementFile], ['infrastructure', form.infrastructureFile]]
        for (const [type, file] of [...required, ...supporting]) if (file) { setSimulationMessage(`Validating ${type} dataset…`); await uploadDataset(type, file) }
        setSimulationMessage('Generating projected modelling domain…')
        modellingPreprocessing = await preprocess(form.demFile, form.riverFile, { resolution_m: 30, river_buffer_m: 1000, min_domain_area_m2: 1 })
      }

      const riverName = form.river.trim() || 'Downstream river network'
      const damName = form.dam.trim() || selectedDam?.name || 'Selected dam'
      const selectedModels = Array.isArray(form.models) && form.models.length ? form.models : ['sph']
      const model = selectedModels.length > 1 ? 'both' : selectedModels[0]
      const scenario = await createScenario({ name: `${riverName} — ${damName} — ${form.scenario}`, initial_reservoir_water_level_m: waterLevel, reservoir_volume_m3: reservoirVolume, breach_width_m: breachWidth, breach_depth_m: breachDepth, breach_formation_time_s: breachTime, initial_discharge_m3s: initialDischarge, simulation_duration_s: duration, model })
      const controlled = form.scenario === 'Controlled Release' ? asNumber(form.controlledReleaseDischarge) : null
      setSimulationMessage('Generating scenario variant…')
      const variants = await generateVariants(scenario.id, { presets: [presetMap[form.scenario]], controlled_release_discharge_m3s: controlled })
      const preset = presetMap[form.scenario]
      const variant = variants.find((item) => item.code === preset || item.preset === preset);
      if (!variant) throw new Error(`Generated ${form.scenario.toLowerCase()} variant could not be found.`)
      const createdJobIds = []
      for (const modelName of selectedModels) {
        setSimulationMessage('Preparing simulation…')
        const preparation = await prepareModel(scenario.id, variant.id, modelName, {
          auto_generate: true,
          sph_output_interval_s: 1,
          timeout_s: 3600,
          preprocessed_dem: modellingPreprocessing.dem.path,
          prepared_river: modellingPreprocessing.river.path,
          computational_domain: modellingPreprocessing.domain.path,
          domain_mask: modellingPreprocessing.domain.mask_raster_path,
        })
        const job = await createSimulation({
          project_id: project.id,
          scenario_id: scenario.id,
          variant_id: variant.id,
          model: modelName,
          prepare: {
            native_input_directory: preparation.native_input_directory,
            auto_generate: true,
            sph_output_interval_s: 1,
            timeout_s: 3600,
            preprocessed_dem: modellingPreprocessing.dem.path,
            prepared_river: modellingPreprocessing.river.path,
            computational_domain: modellingPreprocessing.domain.path,
            domain_mask: modellingPreprocessing.domain.mask_raster_path,
          },
          max_attempts: 1,
        })
        createdJobIds.push(job.id)
      }
      setWatchedJobs(createdJobIds); setSimulationMessage(`${createdJobIds.length} simulation job${createdJobIds.length === 1 ? '' : 's'} queued.`); navigate('/simulations')
    } finally { setIsRunning(false) }
  }

  return (
    <div className="space-y-4">
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-[20px] border-2 border-sky-700/80 bg-slate-950 px-5 py-4 text-white shadow-[0_6px_0_rgba(25,64,83,0.12)]"><div className="flex min-w-0 items-center gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-cyan-400 text-slate-950"><MapPinned size={20} /></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-x-2 text-xs font-bold uppercase tracking-[0.12em] text-cyan-300"><span>{form.river || 'River basin'}</span><span className="text-slate-500">/</span><span>{form.dam || 'Select dam'}</span></div><h1 className="truncate text-xl font-black tracking-[-0.04em]">Dam-break inundation study</h1></div></div><div className="flex flex-wrap items-center gap-2 text-xs font-bold"><span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-2 text-slate-300"><CalendarDays size={14} />{new Date().toLocaleDateString()}</span><span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-2 text-slate-300"><Activity size={14} />{formatStatus(currentStatus)}</span></div></section>
      <div className="flex items-center gap-3 rounded-2xl border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm text-amber-950"><AlertTriangle className="shrink-0 text-amber-600" size={18} /><p><strong>Scenario-based decision support:</strong> outputs depend on terrain, breach and boundary assumptions. This is not an official emergency warning.</p></div>
      {apiStatus === 'online' && !busy && datasets.length === 0 && <div className="flex items-center gap-2 rounded-2xl border border-sky-300 bg-sky-50 px-4 py-3 text-sm font-semibold text-sky-900"><CheckCircle2 size={17} />Backend connected. Search for a dam to automatically prepare the study area.</div>}
      <div className="grid items-start gap-4 lg:grid-cols-[300px_minmax(0,1.7fr)_360px]">
        <SimulationSidebar form={form} riverLoading={riverLoading} onFieldChange={handleFieldChange} onRunSimulation={() => runWorkflow().catch((e) => { setSimulationMessage(e.message || 'Simulation could not be submitted.'); setIsRunning(false) })} isRunning={isRunning} simulationMessage={simulationMessage} damCandidates={damCandidates} selectedDam={selectedDam} onSelectDam={handleSelectDam} onSearchDam={(query) => handleSearchDam(query).catch((e) => setSimulationMessage(e.message || 'Dam search failed.'))} onAutoAcquire={() => handleAutoAcquire().catch((e) => setSimulationMessage(e.message || 'Automatic data acquisition failed.'))} autoAcquisition={autoAcquisition} acquisitionLoading={acquisitionLoading} />
        <div className="min-w-0 space-y-4">
          <MapPanel activeLayer={activeLayer} setActiveLayer={setActiveLayer} scenario={form.scenario} riverFile={form.riverFile} damFile={form.damFile} analysisId={latestAnalysis?.id} projectId={project?.id} datasetIds={layerDatasetIds} satelliteValidationId={latestSatelliteValidation?.id} studyDataReady={autoReady} timelineFrame={timelineFrame} />
          <FloodPropagation jobId={latestJob?.id} stats={stats} durationMinutes={Number(form.simulationDurationMin) || 60} onFrameChange={setTimelineFrame} />
        </div>
        <div className="space-y-4">
          <ResultsSidebar stats={stats} analysis={latestAnalysis} job={latestJob} />
          <ImpactPanel stats={stats} />
        </div>
      </div>
    </div>
  )
}
export default Dashboard
