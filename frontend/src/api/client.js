const DEFAULT_API_BASE_URL = '/api/v1'

function getApiBaseUrl() {
  const runtime = globalThis.__HYDROSHIELD_CONFIG__?.apiBaseUrl
  const buildTime = import.meta.env.VITE_API_BASE_URL
  return String(runtime || buildTime || DEFAULT_API_BASE_URL).replace(/\/$/, '')
}

export const API_BASE_URL = getApiBaseUrl()

export class ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  } catch (error) {
    throw new ApiError(error?.message || 'Unable to reach HydroShield backend.', 0)
  }
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const message = payload?.error?.message || payload?.detail || payload?.message || `Request failed with HTTP ${response.status}`
    throw new ApiError(message, response.status, payload)
  }
  return payload
}

export const api = {
  health: () => request('/health'),
  readiness: () => request('/health/ready'),
  createProject: (payload) => request('/projects', { method: 'POST', body: JSON.stringify(payload) }),
  getProject: (projectId) => request(`/projects/${projectId}`),
  listDatasets: (projectId) => request(`/projects/${projectId}/datasets`),
  getDatasetPreview: (projectId, datasetId, logicalType = null) => {
    const suffix = logicalType ? `?logical_type=${encodeURIComponent(logicalType)}` : ''
    return request(`/projects/${projectId}/datasets/${datasetId}/preview${suffix}`)
  },
  listScenarios: (projectId) => request(`/projects/${projectId}/scenarios`),
  listVariants: (projectId, scenarioId) => request(`/projects/${projectId}/scenarios/${scenarioId}/variants`),
  createScenario: (projectId, payload) => request(`/projects/${projectId}/scenarios`, { method: 'POST', body: JSON.stringify(payload) }),
  generateVariants: (projectId, scenarioId, payload) => request(`/projects/${projectId}/scenarios/${scenarioId}/variants/generate`, { method: 'POST', body: JSON.stringify(payload) }),
  searchDams: (payload) => request('/acquisition/search', { method: 'POST', body: JSON.stringify(payload) }),
  runAutomaticAcquisition: (projectId, payload) => request(`/acquisition/projects/${projectId}/run`, { method: 'POST', body: JSON.stringify(payload) }),
  listAcquisitionRuns: (projectId) => request(`/acquisition/projects/${projectId}/runs`),
  uploadDataset: (projectId, datasetType, file) => {
    const form = new FormData()
    form.append('dataset_type', datasetType)
    form.append('file', file)
    return request(`/projects/${projectId}/datasets/upload`, { method: 'POST', body: form })
  },
  validateDataset: (datasetType, file) => {
    const form = new FormData()
    form.append('dataset_type', datasetType)
    form.append('file', file)
    return request('/datasets/validate', { method: 'POST', body: form })
  },
  preprocess: (demFile, riverFile, config = {}) => {
    const form = new FormData()
    form.append('dem', demFile)
    form.append('river', riverFile)
    if (config.target_crs) form.append('target_crs', config.target_crs)
    form.append('resolution_m', String(config.resolution_m ?? 30))
    form.append('river_buffer_m', String(config.river_buffer_m ?? 1000))
    form.append('min_domain_area_m2', String(config.min_domain_area_m2 ?? 1))
    return request('/geospatial/preprocess', { method: 'POST', body: form })
  },
  uploadModelInputs: (projectId, model, file) => {
    const form = new FormData()
    form.append('model', model)
    form.append('file', file)
    return request(`/projects/${projectId}/model-inputs`, { method: 'POST', body: form })
  },
  prepareModel: (projectId, scenarioId, variantId, model, payload) => request(`/modelling/projects/${projectId}/scenarios/${scenarioId}/variants/${variantId}/prepare/${model}`, { method: 'POST', body: JSON.stringify(payload) }),
  createSimulation: (payload) => request('/simulations', { method: 'POST', body: JSON.stringify(payload) }),
  getSimulation: (jobId) => request(`/simulations/${jobId}`),
  listSimulations: (projectId) => request(`/simulations/projects/${projectId}`),
  cancelSimulation: (jobId) => request(`/simulations/${jobId}/cancel`, { method: 'POST' }),
  uploadAnalysisInputs: (jobId, files) => {
    const form = new FormData()
    form.append('water_depth_raster', files.water_depth_raster)
    for (const field of ['velocity_raster', 'arrival_time_raster', 'water_level_raster', 'dem_raster', 'discharge_csv']) if (files[field]) form.append(field, files[field])
    return request(`/results/simulations/${jobId}/analysis-inputs`, { method: 'POST', body: form })
  },
  analyzeSimulation: (jobId, payload) => request(`/results/simulations/${jobId}/analyze`, { method: 'POST', body: JSON.stringify(payload) }),
  processNativeResult: (jobId, payload = {}) => request(`/results/simulations/${jobId}/process-native`, { method: 'POST', body: JSON.stringify(payload) }),
  sampleAnalysisRaster: (resultId, artifact, latitude, longitude) => request(`/exports/analysis/${resultId}/sample?artifact=${encodeURIComponent(artifact)}&latitude=${encodeURIComponent(latitude)}&longitude=${encodeURIComponent(longitude)}`),
  listResults: (jobId) => request(`/results/simulations/${jobId}`),
  getSimulationTimeline: (jobId, maxFrames = 24) => request(`/results/simulations/${jobId}/timeline?max_frames=${encodeURIComponent(maxFrames)}`),
  getResult: (resultId) => request(`/results/${resultId}`),
  compareResults: (payload) => request('/results/compare', { method: 'POST', body: JSON.stringify(payload) }),
  createComparisonDemo: (payload) => request('/results/comparison-demo', { method: 'POST', body: JSON.stringify(payload) }),
  getAnalysisPreview: (resultId, artifact) => request(`/exports/analysis/${resultId}/preview?artifact=${encodeURIComponent(artifact)}`),
  getFloodZones: (resultId) => request(`/exports/analysis/${resultId}/flood-zones`),
  getComparison: (comparisonId) => request(`/results/comparisons/${comparisonId}`),
  validateSatellite: (payload) => request('/satellite/validate', { method: 'POST', body: JSON.stringify(payload) }),
  solverPreflight: () => request('/modelling/preflight'),
  getSatelliteValidation: (validationId) => request(`/satellite/validations/${validationId}`),
  listSatelliteValidations: (analysisId) => request(`/satellite/analyses/${analysisId}/validations`),
  getSatelliteObservedExtent: (validationId) => request(`/satellite/validations/${validationId}/observed-extent`),
  getSatelliteDifferencePreview: (validationId) => request(`/satellite/validations/${validationId}/difference-preview`),
}

export async function downloadExport(path, filename) {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) {
    const payload = (response.headers.get('content-type') || '').includes('application/json') ? await response.json() : null
    throw new ApiError(payload?.detail || `Download failed with HTTP ${response.status}`, response.status, payload)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^";]+)"?/i)
  const resolvedFilename = filename || match?.[1] || 'hydroshield-export'
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = resolvedFilename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export async function fetchExportJson(path) {
  const response = await fetch(`${API_BASE_URL}${path}`)
  if (!response.ok) throw new ApiError(`Request failed with HTTP ${response.status}`, response.status)
  return response.json()
}
