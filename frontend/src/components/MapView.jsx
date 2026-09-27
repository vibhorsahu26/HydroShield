import { useCallback, useEffect, useMemo, useState } from 'react'
import { GeoJSON, ImageOverlay, MapContainer, TileLayer, useMap } from 'react-leaflet'
import { circleMarker, divIcon, geoJSON, marker } from 'leaflet'
import { API_BASE_URL, api } from '../api/client'

function FitBounds({ bounds, geometry, resetToken }) {
  const map = useMap()
  useEffect(() => {
    try {
      if (bounds?.length === 2) {
        map.fitBounds(bounds, { padding: [34, 34], maxZoom: 14 })
        return
      }
      if (!geometry) return
      const layer = geoJSON(geometry)
      if (layer?.getBounds?.().isValid()) map.fitBounds(layer.getBounds(), { padding: [34, 34], maxZoom: 14 })
    } catch {}
  }, [bounds, geometry, map, resetToken])
  return null
}


async function readGeoJSONFile(file, label) {
  if (!file) return null
  const ext = `.${(file.name.split('.').pop() || '').toLowerCase()}`
  if (!['.geojson', '.json'].includes(ext)) throw new Error(`${label} preview requires GeoJSON; the uploaded dataset may still be stored as GeoPackage.`)
  const parsed = JSON.parse(await file.text())
  if (!parsed || !['FeatureCollection', 'Feature'].includes(parsed.type)) throw new Error(`Selected ${label.toLowerCase()} file is not valid GeoJSON.`)
  return parsed
}

const rasterArtifact = {
  'Water Depth': 'water_depth_raster',
  Velocity: 'velocity_raster',
  'Arrival Time': 'arrival_time_raster',
}

const rasterUnits = { 'Water Depth': 'm', Velocity: 'm/s', 'Arrival Time': 'min' }
const rasterDescriptions = {
  'Water Depth': 'Maximum water depth',
  Velocity: 'Maximum flow velocity',
  'Arrival Time': 'First arrival above flood threshold',
}
const palette = {
  'Water Depth': 'linear-gradient(90deg, #e1f7fa 0%, #7dd3fc 30%, #0ea5e9 58%, #2563eb 78%, #1e40af 100%)',
  Velocity: 'linear-gradient(90deg, #fef9c3 0%, #fde047 30%, #fb923c 58%, #dc2626 80%, #7f1d1d 100%)',
  'Arrival Time': 'linear-gradient(90deg, #dcfce7 0%, #86efac 30%, #facc15 58%, #f97316 80%, #dc2626 100%)',
}

const zoneColors = {
  Shallow: '#38bdf8',
  Moderate: '#22c55e',
  Deep: '#f59e0b',
  'Very deep': '#dc2626',
}

const damIcon = divIcon({
  className: 'hydroshield-dam-marker',
  html: '<span class="hydroshield-dam-pin"><span></span></span>',
  iconSize: [34, 42],
  iconAnchor: [17, 42],
  tooltipAnchor: [0, -36],
})

function floodZoneStyle(feature, opacity = 0.58) {
  const color = feature?.properties?.color || zoneColors[feature?.properties?.zone] || zoneColors.Shallow
  return { color, weight: 1.5, fillColor: color, fillOpacity: Math.max(0.25, Math.min(0.9, opacity)) }
}

function floodZoneTooltip(feature) {
  const p = feature?.properties || {}
  const min = Number(p.depth_min_m)
  const max = Number(p.depth_max_m)
  const area = Number(p.area_km2)
  const depth = Number.isFinite(min) && Number.isFinite(max)
    ? `${min.toFixed(2)}–${max.toFixed(2)} m`
    : 'Flooded area'
  return `<div class="hydroshield-zone-tooltip"><strong>${p.zone || 'Flood zone'}</strong><br/>Depth band: ${depth}<br/>Area: ${Number.isFinite(area) ? area.toFixed(3) : '—'} km²<br/>Cells: ${Number(p.cell_count || 0).toLocaleString()}</div>`
}

function FloodZoneLegend({ zones = [] }) {
  const items = zones.length ? zones : Object.entries(zoneColors).map(([label, color]) => ({ label, color }))
  return <div className="absolute bottom-4 right-4 z-[500] w-[230px] rounded-2xl border-2 border-sky-700/80 bg-white/95 p-3 shadow-xl backdrop-blur">
    <div className="text-xs font-black uppercase tracking-[0.1em] text-slate-800">Flood depth zones</div>
    <div className="mt-2 space-y-1.5">
      {items.map((item) => <div key={item.label} className="flex items-center justify-between gap-3 text-[0.68rem] font-bold text-slate-600">
        <span className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm border border-black/10" style={{ background: item.color || zoneColors[item.label] }} />{item.label}</span>
        <span>{item.max_m == null ? `${Number(item.min_m || 0).toFixed(2)}+ m` : `${Number(item.min_m || 0).toFixed(2)}–${Number(item.max_m).toFixed(2)} m`}</span>
      </div>)}
    </div>
    <div className="mt-2 border-t border-sky-700/15 pt-2 text-[0.64rem] font-semibold text-slate-500">Hover a polygon for area and cell details.</div>
  </div>
}

const vectorConfig = {
  river: ['River', 'river'],
  dam: ['Dam', 'dam'],
  roads: ['Roads', 'road'],
  buildings: ['Buildings', 'building'],
  settlements: ['Settlements', 'settlement'],
  bridges: ['Critical Infrastructure', 'bridge'],
  criticalInfrastructure: ['Critical Infrastructure', 'critical_infrastructure'],
}

function Legend({ activeLayer, metadata, sample }) {
  if (!rasterArtifact[activeLayer] || !metadata) return null
  const unit = rasterUnits[activeLayer]
  const toDisplay = (value) => value == null || !Number.isFinite(Number(value)) ? null : Number(value)
  const min = toDisplay(metadata.min_value)
  const max = toDisplay(metadata.max_value)
  return <div className="absolute bottom-4 right-4 z-[500] w-[250px] rounded-2xl border-2 border-sky-700/80 bg-white/95 p-3 shadow-xl backdrop-blur">
    <div className="text-xs font-black uppercase tracking-[0.1em] text-slate-800">{activeLayer}</div>
    <div className="mt-0.5 text-[0.68rem] font-semibold text-slate-500">{rasterDescriptions[activeLayer]}</div>
    <div className="mt-3 h-3 rounded-full" style={{ background: palette[activeLayer] }}/>
    <div className="mt-1 flex justify-between text-[0.64rem] font-bold text-slate-600"><span>{min == null ? '—' : min.toFixed(1)} {unit}</span><span>{max == null ? '—' : max.toFixed(1)} {unit}</span></div>
    {sample && <div className="mt-3 rounded-xl border border-sky-700/20 bg-sky-50 px-2.5 py-2 text-[0.68rem]">
      <div className="font-black text-slate-800">Selected location</div>
      {sample.value == null ? <div className="mt-1 font-semibold text-slate-500">No flood-result value at this location.</div> : <div className="mt-1 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1 font-semibold text-slate-600"><span>{activeLayer}</span><span className="font-black text-slate-900">{Number(sample.value).toFixed(2)} {unit}</span><span>Lat / Lon</span><span className="font-mono text-[0.61rem] text-slate-500">{sample.latitude.toFixed(4)}, {sample.longitude.toFixed(4)}</span></div>}
    </div>}
  </div>
}

function MapView({ riverFile, damFile, analysisId, activeLayer, visibleLayers = {}, projectId, datasetIds = {}, satelliteValidationId, rasterOpacity = .78, floodZoneOpacity = .58, resetToken = 0, timelineFrame = null }) {
  const [features, setFeatures] = useState({})
  const [flood, setFlood] = useState(null)
  const [floodZones, setFloodZones] = useState(null)
  const [demPreview, setDemPreview] = useState(null)
  const [satelliteObserved, setSatelliteObserved] = useState(null)
  const [satelliteDifference, setSatelliteDifference] = useState(null)
  const [preview, setPreview] = useState(null)
  const [sample, setSample] = useState(null)
  const [mapError, setMapError] = useState('')
  const [sampling, setSampling] = useState(false)

  useEffect(() => { setMapError('') }, [analysisId, activeLayer, visibleLayers])

  useEffect(() => {
    let alive = true
    const load = async (key, file, label, id, logical) => {
      if (!visibleLayers[label] && key !== 'river' && key !== 'dam') { if (alive) setFeatures((x) => ({ ...x, [key]: null })); return }
      if (file) {
        try { const value = await readGeoJSONFile(file, label); if (alive) setFeatures((x) => ({ ...x, [key]: value })) } catch (e) { if (alive) setMapError(e.message) }
        return
      }
      if (!projectId || !id) { if (alive) setFeatures((x) => ({ ...x, [key]: null })); return }
      try {
        const suffix = logical ? `?logical_type=${encodeURIComponent(logical)}` : ''
        const response = await fetch(`${API_BASE_URL}/projects/${projectId}/datasets/${id}/preview${suffix}`)
        if (!response.ok) throw new Error(`${label} preview request failed (${response.status}).`)
        const value = await response.json()
        if (alive) setFeatures((x) => ({ ...x, [key]: value }))
      } catch (e) { if (alive) setMapError(e.message) }
    }
    Promise.all(Object.entries(vectorConfig).map(([key, [label, logical]]) => load(key, key === 'river' ? riverFile : key === 'dam' ? damFile : null, label, datasetIds[key], logical)))
    return () => { alive = false }
  }, [projectId, datasetIds, riverFile, damFile, visibleLayers])

  useEffect(() => {
    let alive = true
    if (!analysisId) { setFlood(null); setFloodZones(null); setPreview(null); setSample(null); return () => { alive = false } }
    Promise.all([
      fetch(`${API_BASE_URL}/exports/analysis/${analysisId}?format=geojson`).then(async (response) => { if (!response.ok) throw new Error(`Flood extent request failed (${response.status}).`); return response.json() }),
      api.getFloodZones(analysisId),
    ]).then(([extent, zones]) => { if (!alive) return; setFlood(extent); setFloodZones(zones) }).catch((e) => alive && setMapError(e.message))
    return () => { alive = false }
  }, [analysisId])

  useEffect(() => {
    let alive = true
    if (!projectId || !datasetIds.dem) { setDemPreview(null); return () => { alive = false } }
    fetch(`${API_BASE_URL}/projects/${projectId}/datasets/${datasetIds.dem}/raster-preview`).then(async (response) => { if (!response.ok) throw new Error(`DEM preview request failed (${response.status}).`); return response.json() }).then((value) => alive && setDemPreview(value)).catch((e) => alive && setMapError(e.message))
    return () => { alive = false }
  }, [projectId, datasetIds.dem])

  useEffect(() => {
    let alive = true
    if (!satelliteValidationId || !visibleLayers.Satellite) { setSatelliteObserved(null); setSatelliteDifference(null); return () => { alive = false } }
    Promise.all([
      fetch(`${API_BASE_URL}/satellite/validations/${satelliteValidationId}/observed-extent`).then(async (response) => { if (!response.ok) throw new Error(`Satellite extent request failed (${response.status}).`); return response.json() }),
      fetch(`${API_BASE_URL}/satellite/validations/${satelliteValidationId}/difference-preview`).then(async (response) => { if (!response.ok) throw new Error(`Satellite difference preview request failed (${response.status}).`); return response.json() }),
    ]).then(([extent, difference]) => { if (!alive) return; setSatelliteObserved(extent); setSatelliteDifference(difference) }).catch((e) => alive && setMapError(e.message))
    return () => { alive = false }
  }, [satelliteValidationId, visibleLayers.Satellite])

  useEffect(() => {
    let alive = true
    const artifact = rasterArtifact[activeLayer]
    if (!analysisId || !artifact || !visibleLayers[activeLayer]) { setPreview(null); setSample(null); return () => { alive = false } }
    fetch(`${API_BASE_URL}/exports/analysis/${analysisId}/preview?artifact=${encodeURIComponent(artifact)}`).then(async (response) => { if (!response.ok) throw new Error(`Raster preview request failed (${response.status}).`); return response.json() }).then((value) => alive && setPreview(value)).catch((e) => alive && setMapError(e.message))
    setSample(null)
    return () => { alive = false }
  }, [analysisId, activeLayer, visibleLayers])

  const handleRasterSample = useCallback(async ({ lat, lng }) => {
    const artifact = rasterArtifact[activeLayer]
    if (!analysisId || !artifact) return
    setSampling(true)
    try {
      const response = await fetch(`${API_BASE_URL}/exports/analysis/${analysisId}/sample?artifact=${encodeURIComponent(artifact)}&latitude=${lat}&longitude=${lng}`)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload?.detail || `Raster sample failed (${response.status}).`)
      setSample(payload)
    } catch (error) { setMapError(error.message || 'Unable to sample flood result.') } finally { setSampling(false) }
  }, [activeLayer, analysisId])

  const rasterUrl = preview ? `${API_BASE_URL}${preview.image_path}` : null
  const timelineUrl = timelineFrame?.image_path ? `${API_BASE_URL}${timelineFrame.image_path}${String(timelineFrame.image_path).includes('?') ? '&' : '?'}frame=${timelineFrame.index ?? 0}` : null
  const timelineBounds = timelineFrame?.bounds || null
  const demUrl = demPreview ? `${API_BASE_URL}${demPreview.image_path}` : null
  const satelliteDifferenceUrl = satelliteDifference ? `${API_BASE_URL}${satelliteDifference.image_path}` : null
  const infrastructure = [features.bridges, features.criticalInfrastructure].filter(Boolean)
  const combinedBounds = floodZones?.bbox || timelineBounds || preview?.bounds || satelliteDifference?.bounds || flood?.bbox || demPreview?.bounds || null
  const mapGeometry = floodZones || flood || satelliteObserved || features.river || features.dam
  const floodStyle = useMemo(() => ({ color: '#0f6f8f', weight: 2, dashArray: '8 5', fillColor: '#38bdf8', fillOpacity: .05 }), [])
  const satelliteStyle = useMemo(() => ({ color: '#16a34a', weight: 2, dashArray: '5 4', fillColor: '#22c55e', fillOpacity: .10 }), [])

  return <MapContainer center={[23.5, 79.5]} zoom={5} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
    <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"/>
    {demUrl && visibleLayers.DEM && demPreview?.bounds && <ImageOverlay url={demUrl} bounds={demPreview.bounds} opacity={.32} interactive={false}/>} 
    {visibleLayers.River && features.river && <GeoJSON data={features.river} style={{ color: '#0f6f8f', weight: 4, opacity: .95 }} />}
    {visibleLayers.Dam && features.dam && <GeoJSON data={features.dam} style={{ color: '#b91c1c', weight: 2, fillColor: '#ef4444', fillOpacity: .25 }} pointToLayer={(feature, latlng) => marker(latlng, { icon: damIcon }).bindTooltip(feature?.properties?.name ? `Dam: ${feature.properties.name}` : 'Selected dam', { direction: 'top', opacity: 0.96 })}/>} 
    {visibleLayers.Roads && features.roads && <GeoJSON data={features.roads} style={{ color: '#475569', weight: 2, opacity: .85 }}/>} 
    {visibleLayers.Buildings && features.buildings && <GeoJSON data={features.buildings} style={{ color: '#ea580c', weight: 1, fillColor: '#fb923c', fillOpacity: .24 }} pointToLayer={(_feature, latlng) => circleMarker(latlng, { radius: 3, color: '#ea580c', fillColor: '#fb923c', fillOpacity: .65, weight: 1 })}/>} 
    {visibleLayers.Settlements && features.settlements && <GeoJSON data={features.settlements} style={{ color: '#7c3aed', weight: 1, fillColor: '#a78bfa', fillOpacity: .16 }} pointToLayer={(_feature, latlng) => circleMarker(latlng, { radius: 4, color: '#7c3aed', fillColor: '#a78bfa', fillOpacity: .5, weight: 1 })}/>} 
    {visibleLayers['Critical Infrastructure'] && infrastructure.map((layer, index) => <GeoJSON key={index} data={layer} style={{ color: '#f59e0b', weight: 2, fillColor: '#fbbf24', fillOpacity: .17 }} pointToLayer={(_feature, latlng) => circleMarker(latlng, { radius: 4, color: '#f59e0b', fillColor: '#fbbf24', fillOpacity: .65, weight: 1 })}/>)}
    {visibleLayers.Satellite && satelliteDifferenceUrl && satelliteDifference?.bounds && <ImageOverlay url={satelliteDifferenceUrl} bounds={satelliteDifference.bounds} opacity={0.48} interactive={false}/>}
    {visibleLayers.Satellite && satelliteObserved && <GeoJSON data={satelliteObserved} style={satelliteStyle}/>} 
    {visibleLayers['Flood Extent'] && floodZones?.features?.length > 0 && <GeoJSON
      data={floodZones}
      style={(feature) => floodZoneStyle(feature, floodZoneOpacity)}
      onEachFeature={(feature, layer) => {
        layer.bindTooltip(floodZoneTooltip(feature), { sticky: true, direction: 'top', opacity: 0.97, className: 'hydroshield-zone-tooltip-container' })
        layer.on({
          mouseover: () => { layer.setStyle({ weight: 3, fillOpacity: 0.78 }); layer.bringToFront() },
          mouseout: () => layer.setStyle(floodZoneStyle(feature, floodZoneOpacity)),
        })
      }}
    />}
    {flood && visibleLayers['Flood Extent'] && !floodZones?.features?.length && <GeoJSON data={flood} style={floodStyle}/>} 
    {timelineUrl && timelineBounds && <ImageOverlay url={timelineUrl} bounds={timelineBounds} opacity={rasterOpacity} interactive={false}/>}
    {!timelineUrl && rasterUrl && preview?.bounds && rasterArtifact[activeLayer] && visibleLayers[activeLayer] && !(activeLayer === 'Water Depth' && floodZones?.features?.length) && <ImageOverlay url={rasterUrl} bounds={preview.bounds} opacity={rasterOpacity} interactive eventHandlers={{ click: (event) => handleRasterSample(event.latlng) }}/>} 
    <FitBounds bounds={combinedBounds} geometry={mapGeometry} resetToken={resetToken}/>
    {activeLayer === 'Water Depth' && floodZones?.features?.length > 0 ? <FloodZoneLegend zones={floodZones.zones}/> : <Legend activeLayer={activeLayer} metadata={preview?.metadata} sample={sample}/>}
    {timelineFrame && <div className="absolute top-4 left-1/2 z-[500] -translate-x-1/2 rounded-full border border-cyan-700/30 bg-slate-950/90 px-3 py-1.5 text-[0.67rem] font-black uppercase tracking-[0.1em] text-cyan-200 shadow-lg">Propagation frame · {Math.round(Number(timelineFrame.time_s || 0) / 60)} min</div>}
    {sampling && <div className="absolute bottom-4 left-1/2 z-[500] -translate-x-1/2 rounded-full border border-sky-700/30 bg-white/95 px-3 py-2 text-xs font-extrabold text-slate-700 shadow-lg">Reading result value…</div>}
    {mapError && <div className="absolute bottom-4 left-4 z-[500] max-w-[380px] rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-950 shadow-lg">{mapError}</div>}
  </MapContainer>
}
export default MapView
