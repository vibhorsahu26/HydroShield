import { useEffect, useMemo, useState } from 'react'
import { ChevronRight, Layers3, LocateFixed, Search, SlidersHorizontal } from 'lucide-react'
import MapView from './MapView'

const contextLayers = [
  ['DEM', 'Terrain'],
  ['River', 'Hydrology'],
  ['Dam', 'Scenario'],
  ['Roads', 'Exposure'],
  ['Buildings', 'Exposure'],
  ['Settlements', 'Exposure'],
  ['Critical Infrastructure', 'Exposure'],
  ['Satellite', 'Validation'],
]
const resultLayers = ['Water Depth', 'Velocity', 'Arrival Time']

function MapPanel({ activeLayer, setActiveLayer, scenario, riverFile, damFile, analysisId, projectId, datasetIds, satelliteValidationId, studyDataReady = false, timelineFrame = null }) {
  const [visibleLayers, setVisibleLayers] = useState({
    DEM: studyDataReady,
    River: true,
    Dam: true,
    'Flood Extent': true,
    'Water Depth': true,
    Velocity: false,
    'Arrival Time': false,
    Roads: studyDataReady,
    Buildings: studyDataReady,
    Settlements: studyDataReady,
    'Critical Infrastructure': studyDataReady,
    Satellite: false,
  })

  useEffect(() => {
    if (satelliteValidationId) setVisibleLayers((current) => ({ ...current, Satellite: true }))
  }, [satelliteValidationId])

  useEffect(() => {
    if (!studyDataReady) return
    setVisibleLayers((current) => ({
      ...current,
      DEM: true, River: true, Dam: true, Roads: true, Buildings: true,
      Settlements: true, 'Critical Infrastructure': true,
    }))
  }, [studyDataReady])
  const [rasterOpacity, setRasterOpacity] = useState(78)
  const [resetToken, setResetToken] = useState(0)
  const [layersCollapsed, setLayersCollapsed] = useState(false)

  const hasAnalysis = Boolean(analysisId)
  const effectiveLayer = hasAnalysis && resultLayers.includes(activeLayer) ? activeLayer : 'Water Depth'
  const activeLabel = hasAnalysis ? effectiveLayer : 'Flood Extent'

  const toggle = (layer) => setVisibleLayers((current) => ({ ...current, [layer]: !current[layer] }))
  const setResultLayer = (layer) => {
    setActiveLayer(layer)
    setVisibleLayers((current) => ({
      ...current,
      'Flood Extent': true,
      'Water Depth': layer === 'Water Depth',
      Velocity: layer === 'Velocity',
      'Arrival Time': layer === 'Arrival Time',
    }))
  }

  const layerHint = useMemo(() => {
    if (!hasAnalysis) return 'Run a simulation and finish result processing to activate quantitative flood layers.'
    if (effectiveLayer === 'Water Depth') return 'Colors show maximum water depth; the flood boundary remains visible.'
    if (effectiveLayer === 'Velocity') return 'Colors show maximum reconstructed flow velocity; click the map to inspect a cell.'
    return 'Colors show flood arrival time; early arrival is shown at the low end of the scale.'
  }, [effectiveLayer, hasAnalysis])

  return <section className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80">
    <div className="relative m-[10px_10px_0] h-[600px] overflow-hidden rounded-[18px] border-2 border-sky-700/70 bg-slate-200">
      <div className="absolute left-4 top-4 z-[500] flex w-[300px] items-center gap-2 rounded-xl border-2 border-sky-700/80 bg-white/92 px-3 py-2 text-sm text-slate-600 shadow-lg">
        <Search size={16} className="text-sky-700"/><div><div className="font-bold text-slate-800">Interactive flood map</div><div className="text-[0.65rem] font-semibold text-slate-500">Click a result cell to inspect values</div></div>
      </div>

      <div className="absolute bottom-4 left-4 z-[500] max-w-[320px] rounded-xl border-2 border-sky-700/80 bg-slate-950/92 px-3 py-2 text-white shadow-lg">
        <div className="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-cyan-300">Active scenario</div>
        <div className="mt-0.5 text-sm font-black">{scenario || 'Dam-break scenario'} <span className="font-normal text-slate-400">/ {activeLabel}</span></div>
      </div>

      <div className="absolute right-4 top-4 z-[500] max-h-[calc(100dvh-2rem)] w-[min(272px,calc(100%-2rem))] overflow-y-auto rounded-2xl border-2 border-sky-700/80 bg-white/96 p-3 shadow-xl backdrop-blur">
        <div className="mb-2 flex items-center justify-between gap-2 text-[0.9rem] font-bold text-slate-800">
          <span className="flex items-center gap-2"><Layers3 size={16} className="text-sky-700"/>Map layers</span>
          <button type="button" onClick={() => setLayersCollapsed((collapsed) => !collapsed)} aria-label={layersCollapsed ? 'Expand map layers' : 'Collapse map layers'} aria-expanded={!layersCollapsed} className="flex h-7 w-7 shrink-0 items-center justify-center rounded border border-sky-700/20 text-slate-600 hover:bg-sky-50">
            <ChevronRight size={16} className={`transition-transform ${layersCollapsed ? '' : 'rotate-90'}`}/>
          </button>
        </div>
        {!layersCollapsed && <>
        <div className="rounded-xl border border-sky-700/20 bg-sky-50/80 p-2.5">
          <div className="mb-1.5 text-[0.67rem] font-black uppercase tracking-[0.12em] text-slate-500">Flood result</div>
          <button type="button" onClick={() => setVisibleLayers((current) => ({ ...current, 'Flood Extent': !current['Flood Extent'] }))} className="flex w-full items-center justify-between rounded-lg border border-sky-700/20 bg-white px-2.5 py-2 text-xs font-bold text-slate-700">
            <span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-sky-500"/>Flood Extent</span><span>{visibleLayers['Flood Extent'] ? 'Visible' : 'Hidden'}</span>
          </button>
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            {resultLayers.map((layer) => <button key={layer} type="button" disabled={!hasAnalysis} onClick={() => setResultLayer(layer)} className={`rounded-lg border px-2 py-2 text-[0.68rem] font-extrabold ${effectiveLayer === layer && hasAnalysis ? 'border-sky-700 bg-sky-100 text-sky-800' : 'border-slate-200 bg-white text-slate-600'} disabled:cursor-not-allowed disabled:opacity-45`}>{layer === 'Water Depth' ? 'Depth' : layer}</button>)}
          </div>
          <div className="mt-2 flex items-center gap-2 text-[0.67rem] font-semibold text-slate-500"><SlidersHorizontal size={13}/><span>Map opacity</span><input aria-label="Flood result opacity" type="range" min="35" max="90" value={rasterOpacity} onChange={(event) => setRasterOpacity(Number(event.target.value))} className="w-full accent-sky-600"/><span className="w-9 text-right">{rasterOpacity}%</span></div>
        </div>
        <div className="mt-2 grid gap-1">
          <div className="text-[0.67rem] font-black uppercase tracking-[0.12em] text-slate-500">Context</div>
          <div className="max-h-36 overflow-y-auto pr-1">
            {contextLayers.map(([layer, category]) => <label key={layer} className="flex items-center justify-between gap-2 rounded-lg px-1 py-1 text-[0.75rem] text-slate-700 hover:bg-sky-50"><span className="flex min-w-0 items-center gap-2"><input type="checkbox" checked={visibleLayers[layer] ?? false} onChange={() => toggle(layer)} className="h-3.5 w-3.5 shrink-0 accent-sky-600"/><span className="truncate">{layer}</span></span><span className="shrink-0 text-[0.58rem] font-bold uppercase text-slate-400">{category}</span></label>)}
          </div>
        </div>
        <div className="mt-2 border-t border-sky-700/15 pt-2 text-[0.68rem] font-semibold leading-4 text-slate-500">{layerHint}</div>
        <button type="button" onClick={() => setResetToken((token) => token + 1)} className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-sky-700/30 bg-white px-2.5 py-2 text-xs font-extrabold text-slate-700"><LocateFixed size={14}/>Reset map view</button>
        </>}
      </div>

      <MapView projectId={projectId} datasetIds={datasetIds} visibleLayers={visibleLayers} activeLayer={activeLabel} riverFile={visibleLayers.River ? riverFile : null} damFile={visibleLayers.Dam ? damFile : null} analysisId={analysisId} satelliteValidationId={satelliteValidationId} rasterOpacity={rasterOpacity / 100} floodZoneOpacity={rasterOpacity / 100} resetToken={resetToken} timelineFrame={timelineFrame}/>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-4 px-4 pb-4 pt-3">
      <div><div className="text-base font-bold">Flood visualization</div><div className="mt-0.5 text-xs font-semibold text-slate-500">{hasAnalysis ? `${effectiveLayer} · flood boundary always available` : 'Flood extent appears after result processing'}</div></div>
      <div className="flex flex-wrap gap-2.5">{resultLayers.map((layer) => <button key={layer} type="button" disabled={!hasAnalysis} className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${effectiveLayer === layer && hasAnalysis ? 'border-sky-700/70 bg-sky-100 text-sky-800' : 'border-sky-700/50 bg-white/20 text-slate-700'} disabled:cursor-not-allowed disabled:opacity-45`} onClick={() => setResultLayer(layer)}><span className={`h-2.5 w-2.5 rounded-full ${effectiveLayer === layer && hasAnalysis ? 'bg-sky-500' : 'bg-slate-400'}`}/>{layer}</button>)}</div>
    </div>
  </section>
}
export default MapPanel
