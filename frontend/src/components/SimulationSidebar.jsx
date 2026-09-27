import { CheckCircle2, ChevronDown, CirclePlay, Gauge, LoaderCircle, Search, UploadCloud } from 'lucide-react'
import { formatDatasetType } from '../utils/formatters'

function FileField({ label, accept, value, onChange, required = false }) {
  return (
    <label className="mt-3 block">
      <span className="mb-2 block text-sm font-semibold text-slate-600">{label}{required ? ' *' : ''}</span>
      <span className="flex cursor-pointer items-center gap-2 rounded-xl border-2 border-dashed border-sky-700/60 bg-white/60 px-3 py-2 text-sm text-slate-600 hover:bg-sky-100/60">
        <UploadCloud size={16} className="shrink-0 text-sky-700" />
        <span className="min-w-0 flex-1 truncate">{value?.name || 'Choose file'}</span>
        <input className="sr-only" type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0] || null)} />
      </span>
    </label>
  )
}

function SimulationSidebar({
  form,
  riverLoading = false,
  onFieldChange,
  onRunSimulation,
  isRunning,
  simulationMessage,
  damCandidates,
  selectedDam,
  onSelectDam,
  onSearchDam,
  onAutoAcquire,
  autoAcquisition,
  acquisitionLoading,
}) {
  return (
    <aside className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 p-0 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="flex items-center gap-3 border-b-2 border-sky-700/60 bg-white/10 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/80 bg-sky-100 text-sky-700"><Gauge size={18} /></div>
        <h2 className="text-[1.05rem] font-bold tracking-[-0.03em] text-slate-800">Simulation Setup</h2>
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800"><span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">1</span><span>Select Region</span><ChevronDown size={16} className="ml-auto text-slate-600" /></div>
        <label className="mb-2 block text-sm font-semibold text-slate-600">Dam / reservoir</label>
        <div className="flex gap-2">
          <input name="dam" value={form.dam} onChange={onFieldChange} className="h-10 min-w-0 flex-1 rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none" placeholder="Search dam..." />
          <button type="button" onClick={() => onSearchDam(form.dam)} disabled={acquisitionLoading} className="inline-flex h-10 shrink-0 items-center gap-1 rounded-xl bg-sky-700 px-3 text-xs font-black text-white disabled:opacity-50"><Search size={14} /> Find</button>
        </div>
        {!!damCandidates.length && <div className="mt-3 max-h-44 space-y-2 overflow-y-auto">{damCandidates.map((candidate) => <button type="button" key={`${candidate.osm_type || 'place'}-${candidate.osm_id || candidate.latitude}-${candidate.longitude}`} onClick={() => onSelectDam(candidate)} className={`w-full rounded-xl border-2 px-3 py-2 text-left ${selectedDam?.latitude === candidate.latitude && selectedDam?.longitude === candidate.longitude ? 'border-cyan-500 bg-cyan-50' : 'border-sky-700/30 bg-white/70'}`}><div className="text-xs font-black text-slate-800">{candidate.name}</div><div className="mt-1 text-[0.68rem] font-semibold text-slate-500">{candidate.display_name}</div>{candidate.river_name && <div className="mt-1 text-[0.66rem] font-bold text-cyan-700">River · {candidate.river_name}</div>}</button>)}</div>}
        <label className="mb-2 mt-4 block text-sm font-semibold text-slate-600">River</label>
        {riverLoading && <div className="mb-1 flex items-center gap-2 text-[0.68rem] font-bold text-sky-700"><LoaderCircle size={12} className="animate-spin" /> Fetching river network…</div>}
        <input name="river" value={form.river} onChange={onFieldChange} disabled={riverLoading || isRunning} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none disabled:cursor-wait disabled:opacity-70" placeholder={riverLoading ? 'Detecting river…' : 'Auto-detected from study area'} />
        <div className="mt-4 grid grid-cols-2 gap-2">
          <label><span className="mb-2 block text-sm font-semibold text-slate-600">Study radius (km)</span><input name="studyRadiusKm" type="number" min="1" max="25" value={form.studyRadiusKm} onChange={onFieldChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none" /></label>
          <div className="flex items-end"><button type="button" onClick={onAutoAcquire} disabled={acquisitionLoading || !selectedDam} className="flex h-10 w-full items-center justify-center gap-1 rounded-xl px-2 text-xs font-black text-white bg-sky-700">{acquisitionLoading ? <LoaderCircle size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} {acquisitionLoading ? 'Preparing…' : 'Auto Prepare'}</button></div>
        </div>
        <div className={`mt-3 rounded-xl border px-3 py-2 ${autoAcquisition ? 'border-emerald-300 bg-emerald-50' : 'border-sky-700/30 bg-white/50'}`}>
          {autoAcquisition ? <>
            <div className="flex items-center gap-2 text-xs font-black text-emerald-900"><CheckCircle2 size={15} /> Study data loaded automatically</div>
            <div className="mt-2 grid grid-cols-2 gap-1.5">{(autoAcquisition.datasets || []).map((dataset) => <div key={dataset.dataset_id || dataset.id} className="rounded-lg border border-emerald-200 bg-white/70 px-2 py-1 text-[0.68rem] font-bold text-emerald-950">✓ {formatDatasetType(dataset.logical_type || dataset.dataset_type)}</div>)}</div>
            <div className="mt-2 text-[0.68rem] font-semibold text-emerald-800">{autoAcquisition.datasets?.length || 0} datasets ready · preprocessing complete</div>
          </> : <div className="text-xs font-semibold text-blue-700">Auto Prepare will load the core study datasets for this dam.</div>}
        </div>
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800"><span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">2</span><span>Hydrodynamic models</span></div>
        <div className="grid grid-cols-2 gap-2">
          {[['sph', 'SPH'], ['delft3d', 'Delft3D']].map(([value, label]) => (
            <label key={value} className="flex cursor-pointer items-center gap-2 rounded-xl border-2 border-sky-700/30 bg-white/60 px-3 py-2 text-sm font-bold text-slate-700 hover:bg-sky-100/70">
              <input type="checkbox" name={`model:${value}`} checked={(form.models || []).includes(value)} onChange={onFieldChange} className="h-4 w-4 accent-sky-700" />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <div className="mt-2 text-[0.68rem] font-semibold text-slate-500">Select one or both models for this scenario.</div>
      </div>

      <details className="border-b border-sky-700/40 px-4 py-4">
        <summary className="cursor-pointer text-sm font-bold text-slate-800">Manual data fallback</summary>
        <p className="mb-2 mt-2 text-xs font-semibold text-slate-500">Use this only when an automatic provider cannot supply a required dataset.</p>
        <FileField label="DEM GeoTIFF" accept=".tif,.tiff" value={form.demFile} onChange={(value) => onFieldChange({ target: { name: 'demFile', value } })} />
        <FileField label="River GeoJSON / GPKG" accept=".geojson,.json,.gpkg" value={form.riverFile} onChange={(value) => onFieldChange({ target: { name: 'riverFile', value } })} />
        <FileField label="Dam / reservoir GeoJSON" accept=".geojson,.json,.gpkg" value={form.damFile} onChange={(value) => onFieldChange({ target: { name: 'damFile', value } })} />
        <FileField label="Hydrology CSV" accept=".csv" value={form.hydrologyFile} onChange={(value) => onFieldChange({ target: { name: 'hydrologyFile', value } })} />
        <FileField label="Rainfall CSV" accept=".csv" value={form.rainfallFile} onChange={(value) => onFieldChange({ target: { name: 'rainfallFile', value } })} />
        <FileField label="Land-use / land-cover" accept=".tif,.tiff,.geojson,.json,.gpkg" value={form.landcoverFile} onChange={(value) => onFieldChange({ target: { name: 'landcoverFile', value } })} />
        <FileField label="Settlement layer" accept=".geojson,.json,.gpkg" value={form.settlementFile} onChange={(value) => onFieldChange({ target: { name: 'settlementFile', value } })} />
        <FileField label="Infrastructure layer" accept=".geojson,.json,.gpkg" value={form.infrastructureFile} onChange={(value) => onFieldChange({ target: { name: 'infrastructureFile', value } })} />
      </details>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800"><span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">3</span><span>Scenario</span><ChevronDown size={16} className="ml-auto text-slate-600" /></div>
        <select name="scenario" value={form.scenario} onChange={onFieldChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none"><option value="Major Breach">Major Breach</option><option value="Partial Breach">Partial Breach</option><option value="Extreme Breach">Extreme Breach</option><option value="Controlled Release">Controlled Release</option></select>
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800"><span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">4</span><span>Breach Parameters</span></div>
        {[['breachWidth', 'Breach Width (m)'], ['breachDepth', 'Breach Depth (m)'], ['breachTimeMin', 'Breach Formation Time (min)'], ['waterLevel', 'Initial Water Level (m)'], ['reservoirVolume', 'Reservoir Volume (m³)'], ['initialDischarge', 'Initial Discharge (m³/s)'], ['simulationDurationMin', 'Simulation Duration (min)']].map(([name, label]) => <label key={name} className="mb-3 block"><span className="mb-2 block text-sm font-semibold text-slate-600">{label}</span><input type="number" min="0" step="any" name={name} value={form[name]} onChange={onFieldChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/50 px-3 text-slate-700 outline-none" /></label>)}
        {form.scenario === 'Controlled Release' && <label className="block"><span className="mb-2 block text-sm font-semibold text-slate-600">Controlled Release Discharge (m³/s)</span><input type="number" min="0" step="any" name="controlledReleaseDischarge" value={form.controlledReleaseDischarge} onChange={onFieldChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/50 px-3 text-slate-700 outline-none" /></label>}
      </div>

      <button type="button" disabled={isRunning || (!autoAcquisition && !(form.demFile && form.riverFile))} className="mx-auto mt-5 flex w-[calc(100%-28px)] items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-sky-500 to-sky-700 px-4 py-3.5 text-base font-bold text-white shadow-[0_6px_0_rgba(16,64,114,0.22)] transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50" onClick={onRunSimulation}><CirclePlay size={18} /> {isRunning ? 'Running...' : 'Run Simulation'}</button>
      <div className="mx-4 mb-4 mt-3 flex items-center gap-2 rounded-xl border border-sky-700/40 bg-sky-100/70 px-3 py-2 text-xs font-bold text-slate-600"><span className={`h-2.5 w-2.5 rounded-full ${isRunning ? 'bg-amber-400' : 'bg-emerald-500'}`} />{simulationMessage}</div>
    </aside>
  )
}
export default SimulationSidebar
