import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api, ApiError } from '../api/client'

const STORAGE_KEY = 'hydroshield.project.id'
const HydroShieldContext = createContext(null)

function projectStorageId() {
  try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
}
function saveProjectId(id) {
  try { localStorage.setItem(STORAGE_KEY, id) } catch { /* runtime state remains usable */ }
}

export function HydroShieldProvider({ children }) {
  const [project, setProject] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [scenarios, setScenarios] = useState([])
  const [variantsByScenario, setVariantsByScenario] = useState({})
  const [jobs, setJobs] = useState([])
  const [analyses, setAnalyses] = useState([])
  const [satelliteValidations, setSatelliteValidations] = useState([])
  const [damCandidates, setDamCandidates] = useState([])
  const [acquisitionRuns, setAcquisitionRuns] = useState([])
  const [autoAcquisition, setAutoAcquisition] = useState(null)
  const [solverRuntime, setSolverRuntime] = useState(null)
  const [apiStatus, setApiStatus] = useState('checking')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const bootstrapRef = useRef(false)
  const jobsRef = useRef([])
  const analysesRef = useRef([])
  const nativeProcessingRef = useRef(new Set())

  useEffect(() => { jobsRef.current = jobs }, [jobs])
  useEffect(() => { analysesRef.current = analyses }, [analyses])

  const withError = useCallback(async (operation) => {
    setError('')
    try { return await operation() } catch (err) {
      setError(err instanceof ApiError ? err.message : err?.message || 'Unexpected error.')
      throw err
    }
  }, [])

  const refreshProjectData = useCallback(async (projectId = project?.id) => {
    if (!projectId) return
    const [projectData, datasetData, scenarioData, jobData, acquisitionData] = await Promise.all([
      api.getProject(projectId), api.listDatasets(projectId), api.listScenarios(projectId), api.listSimulations(projectId), api.listAcquisitionRuns(projectId),
    ])
    setProject(projectData); setDatasets(datasetData); setScenarios(scenarioData); setJobs(jobData); setAcquisitionRuns(acquisitionData)
    const latestAcquisition = acquisitionData.find((run) => run.status === 'completed' && run.provider_summary?.preprocessing)
    if (latestAcquisition) {
      const request = latestAcquisition.request || {}
      const acquiredDatasets = datasetData.filter((dataset) => dataset.acquisition_run_id === latestAcquisition.id).map((dataset) => ({
        dataset_id: dataset.id, dataset_type: dataset.dataset_type, logical_type: dataset.source_metadata?.logical_type || dataset.dataset_type,
        filename: dataset.filename, provider: dataset.provider, source: dataset.source_url, source_id: dataset.source_id,
        status: dataset.validation_status, storage_uri: dataset.storage_uri, checksum_sha256: dataset.checksum_sha256, warnings: dataset.warnings || [],
      }))
      setAutoAcquisition({
        acquisition_run_id: latestAcquisition.id, project_id: projectId, dam_name: request.dam_name, latitude: request.latitude, longitude: request.longitude,
        radius_km: request.radius_km, bbox_wgs84: latestAcquisition.provider_summary.bbox_wgs84 || [], datasets: acquiredDatasets,
        preprocessing: latestAcquisition.provider_summary.preprocessing, warnings: latestAcquisition.warnings || [],
        attribution: ['© OpenStreetMap contributors'], request,
      })
    } else { setAutoAcquisition(null) }
    const entries = await Promise.all(scenarioData.map(async (scenario) => [scenario.id, await api.listVariants(projectId, scenario.id)]))
    setVariantsByScenario(Object.fromEntries(entries))
    const completedJobs = jobData.filter((job) => job.status === 'completed')
    const resultSets = await Promise.all(completedJobs.map(async (job) => {
      try { return { job, results: await api.listResults(job.id) } }
      catch { return { job, results: [] } }
    }))
    const nextAnalyses = resultSets.flatMap(({ job, results }) => results.map((result) => ({ ...result, job })))
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    setAnalyses(nextAnalyses)
    const validationSets = await Promise.all(nextAnalyses.map(async (analysis) => {
      try { return await api.listSatelliteValidations(analysis.id) }
      catch { return [] }
    }))
    setSatelliteValidations(validationSets.flat().sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
    setApiStatus('online')
    return { projectData, datasetData, scenarioData, jobData }
  }, [project?.id])

  const reconcileNativeResult = useCallback(async (job) => {
    if (job?.status !== 'completed' || !['sph', 'delft3d'].includes(job?.model) || job?.result?.analysis_result_id || nativeProcessingRef.current.has(job.id)) return
    nativeProcessingRef.current.add(job.id)
    try {
      const result = await api.processNativeResult(job.id, { flood_threshold_m: 0.05 })
      const refreshedJob = await api.getSimulation(job.id).catch(() => job)
      setJobs((current) => current.map((item) => item.id === refreshedJob.id ? refreshedJob : item))
      setAnalyses((current) => [...current.filter((item) => item.simulation_job_id !== job.id), { ...result, job }].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
    } catch {
      // Automatic server-side processing is retried only through an explicit Analysis-page action
      // after a failed reconciliation, preventing a tight polling loop against a broken result.
    }
  }, [])

  const refreshSimulations = useCallback(async (projectId = project?.id) => {
    if (!projectId) return []
    const jobData = await api.listSimulations(projectId)
    setJobs(jobData)

    const knownAnalysisJobs = new Set(analysesRef.current.map((item) => item.simulation_job_id))
    const completedJobs = jobData.filter((job) => job.status === 'completed' && !knownAnalysisJobs.has(job.id))
    for (const job of completedJobs) void reconcileNativeResult(job)
    if (completedJobs.length) {
      const resultSets = await Promise.all(completedJobs.map(async (job) => {
        try { return { job, results: await api.listResults(job.id) } }
        catch { return { job, results: [] } }
      }))
      const fresh = resultSets.flatMap(({ job, results }) => results.map((result) => ({ ...result, job })))
      if (fresh.length) {
        setAnalyses((current) => {
          const byId = new Map(current.map((item) => [item.id, item]))
          for (const item of fresh) byId.set(item.id, item)
          return [...byId.values()].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        })
        const validationSets = await Promise.all(fresh.map(async (analysis) => {
          try { return await api.listSatelliteValidations(analysis.id) }
          catch { return [] }
        }))
        setSatelliteValidations((current) => {
          const byId = new Map(current.map((item) => [item.id, item]))
          for (const item of validationSets.flat()) byId.set(item.id, item)
          return [...byId.values()].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        })
      }
    }
    return jobData
  }, [project?.id, reconcileNativeResult])

  useEffect(() => {
    if (!project?.id) return undefined
    let alive = true
    let inFlight = false
    const tick = async () => {
      if (inFlight) return
      inFlight = true
      try {
        await refreshSimulations(project.id)
      } catch {
        // Initial bootstrap/error state owns the visible API error; polling should not
        // turn a transient refresh failure into a noisy global error banner.
      } finally {
        inFlight = false
      }
    }
    const interval = window.setInterval(() => { if (alive) tick() }, 2500)
    return () => { alive = false; window.clearInterval(interval) }
  }, [project?.id, refreshSimulations])

  const bootstrap = useCallback(async () => {
    if (bootstrapRef.current) return
    bootstrapRef.current = true; setBusy(true)
    try {
      await api.health(); setApiStatus('online')
      try { setSolverRuntime(await api.solverPreflight()) } catch { setSolverRuntime(null) }
      const storedId = projectStorageId()
      if (storedId) {
        try {
          // Validate the persisted workspace before requesting its dependent resources.
          // A stale localStorage id should not produce a cascade of avoidable 404s.
          await api.getProject(storedId)
          await refreshProjectData(storedId)
          return
        } catch (err) {
          if (!(err instanceof ApiError) || err.status !== 404) throw err
          try { localStorage.removeItem(STORAGE_KEY) } catch { /* keep going with a fresh workspace */ }
        }
      }
      const created = await api.createProject({ name: `HydroShield Workspace ${new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)}`, description: 'Web workspace for HydroShield dam-break and flood inundation simulations.' })
      saveProjectId(created.id)
      await refreshProjectData(created.id)
    } catch (err) {
      setApiStatus('offline'); setError(err instanceof Error ? err.message : 'Unable to connect to the HydroShield backend.')
    } finally { setBusy(false) }
  }, [refreshProjectData])

  useEffect(() => { bootstrap() }, [bootstrap])

  const searchDams = useCallback(async (query, countryCode = null) => {
    const response = await withError(() => api.searchDams({ query, country_code: countryCode || undefined }))
    setDamCandidates(response.candidates || [])
    return response.candidates || []
  }, [withError])
  const runAutomaticAcquisition = useCallback(async (payload) => {
    if (!project?.id) throw new Error('Project is not ready yet.')
    const response = await withError(() => api.runAutomaticAcquisition(project.id, payload))
    const normalizedDatasets = (response.datasets || []).map((item) => ({
      ...item,
      id: item.dataset_id,
      project_id: project.id,
      dataset_type: item.dataset_type,
      filename: item.filename,
      storage_uri: item.storage_uri,
      validation_status: item.status,
      logical_type: item.logical_type,
      source_metadata: { ...(item.source_metadata || {}), logical_type: item.logical_type },
    }))
    const normalizedResponse = { ...response, request: payload, datasets: normalizedDatasets }
    setAutoAcquisition(normalizedResponse)
    setAcquisitionRuns((current) => [{ id: response.acquisition_run_id, project_id: project.id, status: 'completed', request: payload, provider_summary: { bbox_wgs84: response.bbox_wgs84, preprocessing: response.preprocessing }, warnings: response.warnings || [], error_message: null }, ...current.filter((run) => run.id !== response.acquisition_run_id)])
    if (normalizedDatasets.length) setDatasets((current) => [...normalizedDatasets, ...current.filter((dataset) => !normalizedDatasets.some((item) => item.id === dataset.id))])
    // Immediately reconcile with persisted state so the map/layers and the setup panel
    // update without requiring a browser refresh or a second dam selection.
    await refreshProjectData(project.id)
    // Final same-run state reconciliation: refreshProjectData restores persisted records,
    // then this reapplies the authoritative acquisition response so the workspace stays
    // visibly ready without a browser refresh or a second dam selection.
    setAutoAcquisition((current) => current?.acquisition_run_id === response.acquisition_run_id ? { ...current, ...normalizedResponse, request: payload, datasets: normalizedDatasets, preprocessing: response.preprocessing } : current)
    return normalizedResponse
  }, [project?.id, refreshProjectData, withError])
  const getDatasetPreview = useCallback((datasetId, logicalType = null) => { if (!project?.id) throw new Error('Project is not ready yet.'); return withError(() => api.getDatasetPreview(project.id, datasetId, logicalType)) }, [project?.id, withError])
  const uploadDataset = useCallback(async (datasetType, file) => {
    if (!project?.id) throw new Error('Project is not ready yet.')
    const record = await withError(() => api.uploadDataset(project.id, datasetType, file))
    setDatasets((current) => [...current, record]); return record
  }, [project?.id, withError])
  const preprocess = useCallback((demFile, riverFile, config) => withError(() => api.preprocess(demFile, riverFile, config)), [withError])
  const createScenario = useCallback(async (payload) => {
    if (!project?.id) throw new Error('Project is not ready yet.')
    const scenario = await withError(() => api.createScenario(project.id, payload)); setScenarios((current) => [...current, scenario]); return scenario
  }, [project?.id, withError])
  const generateVariants = useCallback(async (scenarioId, payload) => {
    if (!project?.id) throw new Error('Project is not ready yet.')
    await withError(() => api.generateVariants(project.id, scenarioId, payload))
    const variants = await api.listVariants(project.id, scenarioId)
    setVariantsByScenario((current) => ({ ...current, [scenarioId]: variants })); return variants
  }, [project?.id, withError])
  const uploadModelInputs = useCallback((model, file) => { if (!project?.id) throw new Error('Project is not ready yet.'); return withError(() => api.uploadModelInputs(project.id, model, file)) }, [project?.id, withError])
  const prepareModel = useCallback((scenarioId, variantId, model, payload) => { if (!project?.id) throw new Error('Project is not ready yet.'); return withError(() => api.prepareModel(project.id, scenarioId, variantId, model, payload)) }, [project?.id, withError])
  const createSimulation = useCallback(async (payload) => { const job = await withError(() => api.createSimulation(payload)); setJobs((current) => [job, ...current]); return job }, [withError])
  const refreshJob = useCallback(async (jobId) => {
    const job = await api.getSimulation(jobId)
    setJobs((current) => {
      const exists = current.some((item) => item.id === job.id)
      const next = exists ? current.map((item) => item.id === job.id ? job : item) : [job, ...current]
      return [...next].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    })
    if (job.status === 'completed') {
      try {
        const results = await api.listResults(job.id)
        setAnalyses((current) => {
          const filtered = current.filter((item) => item.simulation_job_id !== job.id)
          return [...filtered, ...results.map((result) => ({ ...result, job }))]
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        })
      } catch {
        // A completed simulation remains visible even when it has no analysis result yet.
      }
    }
    return job
  }, [])
  const cancelSimulation = useCallback(async (jobId) => { const job = await withError(() => api.cancelSimulation(jobId)); setJobs((current) => current.map((item) => item.id === job.id ? job : item)); return job }, [withError])
  const uploadAnalysisInputs = useCallback((jobId, files) => withError(() => api.uploadAnalysisInputs(jobId, files)), [withError])
  const processNativeResult = useCallback(async (jobId, payload = {}) => {
    const result = await withError(() => api.processNativeResult(jobId, payload))
    const refreshedJob = await api.getSimulation(jobId).catch(() => jobsRef.current.find((item) => item.id === jobId) || null)
    if (refreshedJob) {
      setJobs((current) => {
        const exists = current.some((item) => item.id === refreshedJob.id)
        const next = exists ? current.map((item) => item.id === refreshedJob.id ? refreshedJob : item) : [refreshedJob, ...current]
        return [...next].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      })
    }
    const linkedJob = refreshedJob || jobsRef.current.find((item) => item.id === jobId)
    setAnalyses((current) => [...current.filter((item) => item.simulation_job_id !== jobId), { ...result, job: linkedJob }].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
    return result
  }, [withError])
  const analyzeSimulation = useCallback(async (jobId, payload) => {
    const result = await withError(() => api.analyzeSimulation(jobId, payload)); const job = jobs.find((item) => item.id === jobId)
    setAnalyses((current) => [...current.filter((item) => item.id !== result.id), { ...result, job }]); return result
  }, [jobs, withError])
  const compareResults = useCallback((payload) => withError(() => api.compareResults(payload)), [withError])
  const createComparisonDemo = useCallback(async (sourceAnalysisId, preferredPreset = null) => {
    const result = await withError(() => api.createComparisonDemo({ source_analysis_id: sourceAnalysisId, preferred_preset: preferredPreset || undefined }))
    if (project?.id) await refreshProjectData(project.id)
    return result
  }, [project?.id, refreshProjectData, withError])
  const validateSatellite = useCallback(async (payload) => { const result = await withError(() => api.validateSatellite(payload)); setSatelliteValidations((current) => [result, ...current]); return result }, [withError])
  const refreshSolverRuntime = useCallback(async () => { const result = await withError(() => api.solverPreflight()); setSolverRuntime(result); return result }, [withError])
  const clearError = useCallback(() => setError(''), [])

  const value = useMemo(() => ({ project, datasets, scenarios, variantsByScenario, jobs, analyses, satelliteValidations, damCandidates, acquisitionRuns, autoAcquisition, solverRuntime, apiStatus, error, busy, bootstrap, refreshProjectData, refreshSimulations, searchDams, runAutomaticAcquisition, getDatasetPreview, uploadDataset, preprocess, createScenario, generateVariants, uploadModelInputs, prepareModel, createSimulation, refreshJob, cancelSimulation, uploadAnalysisInputs, processNativeResult, analyzeSimulation, compareResults, createComparisonDemo, validateSatellite, refreshSolverRuntime, clearError }), [project, datasets, scenarios, variantsByScenario, jobs, analyses, satelliteValidations, damCandidates, acquisitionRuns, autoAcquisition, apiStatus, error, busy, bootstrap, refreshProjectData, refreshSimulations, searchDams, runAutomaticAcquisition, getDatasetPreview, uploadDataset, preprocess, createScenario, generateVariants, uploadModelInputs, prepareModel, createSimulation, refreshJob, cancelSimulation, uploadAnalysisInputs, processNativeResult, analyzeSimulation, compareResults, createComparisonDemo, validateSatellite, refreshSolverRuntime, clearError])
  return <HydroShieldContext.Provider value={value}>{children}</HydroShieldContext.Provider>
}
export function useHydroShield() {
  const value = useContext(HydroShieldContext)
  if (!value) throw new Error('useHydroShield must be used inside HydroShieldProvider')
  return value
}
