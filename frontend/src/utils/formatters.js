export function formatModelName(model) {
  if (model === 'sph') return 'SPH'
  if (model === 'delft3d') return 'Delft3D'
  if (model === 'both') return 'SPH + Delft3D'
  return model || 'Model'
}

export function formatStatus(value) {
  return String(value || 'Ready').replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function formatStep(value) {
  const labels = {
    queued: 'Queued',
    preparing: 'Preparing inputs',
    running: 'Running model',
    postprocessing: 'Processing results',
    complete: 'Complete',
    completed: 'Complete',
    failed: 'Failed',
    cancelled: 'Cancelled',
  }
  return labels[value] || formatStatus(value)
}

export function formatDatasetType(value) {
  const labels = {
    dem: 'DEM',
    river: 'River',
    dam: 'Dam',
    settlement: 'Settlements',
    infrastructure: 'Infrastructure',
    building: 'Buildings',
    road: 'Roads',
    bridge: 'Bridges',
    critical_infrastructure: 'Critical infrastructure',
    hydrology: 'Hydrology',
    rainfall: 'Rainfall',
    landcover: 'Land cover',
  }
  return labels[value] || formatStatus(value)
}

export function formatMetricName(value) {
  const labels = {
    iou: 'IoU',
    f1: 'F1 score',
    rmse: 'RMSE',
    mae: 'MAE',
    max_water_depth_m: 'Maximum water depth',
    max_velocity_mps: 'Maximum velocity',
    inundated_area_m2: 'Inundated area',
    inundated_area_km2: 'Inundated area',
    first_arrival_time_s: 'First arrival time',
    observed_area_m2: 'Observed area',
    model_area_m2: 'Model area',
    intersection_area_m2: 'Overlap area',
  }
  if (labels[value]) return labels[value]
  return formatStatus(value).replace(/\bm2\b/gi, 'm²').replace(/\bmp?s\b/gi, 'm/s')
}
