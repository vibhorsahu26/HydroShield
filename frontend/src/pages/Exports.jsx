import { useEffect, useMemo, useState } from 'react'
import { Archive, Download, Eye, FileJson2, Map, Table2, Waves } from 'lucide-react'
import { API_BASE_URL, api, downloadExport } from '../api/client'
import { useHydroShield } from '../state/HydroShieldContext'
import { formatModelName } from '../utils/formatters'

const rasterExports = [
  ['water_depth', 'Water depth', 'water_depth_raster'],
  ['flood_mask', 'Flood mask', 'flood_mask_raster'],
  ['velocity', 'Velocity', 'velocity_raster'],
  ['arrival_time', 'Arrival time', 'arrival_time_raster'],
  ['water_level', 'Water level', 'water_level_raster'],
]

function Exports() {
  const { analyses } = useHydroShield()
  const latest = analyses[0]
  const [analysisId, setAnalysisId] = useState('')
  const [comparisonId, setComparisonId] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [status, setStatus] = useState('')
  const selected = useMemo(() => analyses.find((item) => item.id === analysisId), [analyses, analysisId])

  useEffect(() => {
    if (!analysisId && latest?.id) setAnalysisId(latest.id)
  }, [analysisId, latest?.id])

  useEffect(() => {
    try { setComparisonId(sessionStorage.getItem('hydroshield.lastComparison.id') || '') } catch { /* optional */ }
  }, [])

  async function download(path, label) {
    setStatus(`Preparing ${label}…`)
    try {
      await downloadExport(path)
      setStatus(`${label} downloaded.`)
    } catch (error) {
      setStatus(error.message || `${label} failed.`)
    }
  }

  async function showPreview(artifact, label) {
    if (!selected) return
    setPreviewBusy(true)
    setStatus(`Preparing ${label} preview…`)
    try {
      const value = await api.getAnalysisPreview(selected.id, artifact)
      setPreview({ ...value, label })
      setStatus(`${label} preview ready.`)
    } catch (error) {
      setPreview(null)
      setStatus(error.message || 'Preview unavailable.')
    } finally {
      setPreviewBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/90 p-6">
        <div className="text-xs font-bold uppercase tracking-[0.14em] text-sky-700">Outputs</div>
        <h1 className="text-3xl font-black">Export Center</h1>
        <p className="mt-2 text-sm font-medium text-slate-600">Download the analysis package or inspect individual GIS layers.</p>
      </section>

      <section className="rounded-[20px] border-2 border-sky-700/70 bg-white/60 p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <label><span className="field-label">Analysis result</span><select value={analysisId} onChange={(e) => { setAnalysisId(e.target.value); setPreview(null) }} className="field"><option value="">Select analysis</option>{analyses.map((item) => <option key={item.id} value={item.id}>{formatModelName(item.job?.model)} · Analysis {item.id.slice(0, 8)}</option>)}</select></label>
          <label><span className="field-label">Comparison ID</span><input value={comparisonId} onChange={(e) => setComparisonId(e.target.value)} className="field" placeholder="Created from Comparison" /></label>
        </div>
        {selected && <div className="mt-3 flex flex-wrap items-center gap-2 text-xs font-bold text-slate-500"><span className="rounded-full bg-sky-50 px-3 py-1.5">Analysis {selected.id.slice(0, 8)}</span><span className="rounded-full bg-sky-50 px-3 py-1.5">{formatModelName(selected.job?.model)}</span><span className="rounded-full bg-sky-50 px-3 py-1.5">Ready for export</span></div>}
        {status && <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-semibold text-sky-800">{status}</div>}

        {selected ? (
          <>
            <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <button type="button" className="export-card" onClick={() => download(`/exports/analysis/${selected.id}?format=geojson`, 'Flood extent GeoJSON')}><Map size={18} /> Flood extent GeoJSON <Download size={15} /></button>
              <button type="button" className="export-card" onClick={() => download(`/exports/analysis/${selected.id}?format=shp`, 'Flood extent SHP')}><Map size={18} /> Flood extent SHP <Download size={15} /></button>
              <button type="button" className="export-card" onClick={() => download(`/exports/analysis/${selected.id}?format=kml`, 'Flood extent KML')}><Map size={18} /> Flood extent KML <Download size={15} /></button>
              {rasterExports.map(([artifact, label]) => (
                <div key={artifact} className="export-card flex-col items-stretch gap-2 text-left">
                  <div className="flex items-center gap-2"><Waves size={18} /> <span>{label} GeoTIFF</span></div>
                  <div className="flex gap-2">
                    <button type="button" className="export-button flex-1" onClick={() => download(`/exports/analysis/${selected.id}?format=geotiff&artifact=${artifact}`, `${label} GeoTIFF`)}><Download size={14} /> Download</button>
                    <button type="button" className="export-button" disabled={previewBusy} onClick={() => showPreview(`${artifact}_raster`, label)}><Eye size={14} /> Preview</button>
                  </div>
                </div>
              ))}
              <button type="button" className="export-card" onClick={() => download(`/exports/analysis/${selected.id}?format=csv`, 'Analysis CSV')}><Table2 size={18} /> Analysis CSV <Download size={15} /></button>
              <button type="button" className="export-card" onClick={() => download(`/exports/analysis/${selected.id}?format=json`, 'Analysis JSON')}><FileJson2 size={18} /> Analysis JSON <Download size={15} /></button>
              <button type="button" className="export-card sm:col-span-2 lg:col-span-3" onClick={() => download(`/exports/analysis/${selected.id}/package`, 'Complete analysis package')}><Archive size={18} /> Complete analysis package <Download size={15} /></button>
            </div>

            {preview && (
              <div className="mt-5 overflow-hidden rounded-2xl border-2 border-sky-700/40 bg-slate-950 p-4 text-white">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div><div className="text-sm font-black">{preview.label} preview</div><div className="mt-1 text-xs font-medium text-slate-300">{preview.metadata?.width} × {preview.metadata?.height} cells · {preview.metadata?.crs || 'Projected grid'}</div></div>
                  <button type="button" className="rounded-lg border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-bold" onClick={() => setPreview(null)}>Close</button>
                </div>
                <div className="mt-3 overflow-auto rounded-xl bg-white p-2"><img src={`${API_BASE_URL}${preview.image_path}`} alt={`${preview.label} preview`} className="mx-auto max-h-[520px] w-full object-contain" /></div>
              </div>
            )}
          </>
        ) : (
          <div className="mt-5 rounded-xl border border-dashed border-sky-700/40 p-6 text-sm font-semibold text-slate-500">Create an analysis result first.</div>
        )}

        {comparisonId && (
          <div className="mt-5 rounded-2xl border-2 border-cyan-300 bg-cyan-50 p-4">
            <div className="text-sm font-black text-slate-900">Latest comparison</div>
            <div className="mt-1 text-xs font-medium text-slate-600">Comparison {comparisonId.slice(0, 8)}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="export-button" onClick={() => download(`/exports/comparisons/${comparisonId}?format=json`, 'Comparison JSON')}><FileJson2 size={15} /> JSON</button>
              <button type="button" className="export-button" onClick={() => download(`/exports/comparisons/${comparisonId}?format=csv`, 'Comparison CSV')}><Table2 size={15} /> CSV</button>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

export default Exports
