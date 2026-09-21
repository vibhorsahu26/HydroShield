import { ArrowRight, BarChart3, Download, Gauge, MapPinned, TimerReset, Waves } from 'lucide-react'

const exportItems = [
  'Flood Extent (SHP)',
  'Water Depth (GeoTIFF)',
  'Simulation Report (PDF)',
  'All Data (KML/GeoJSON)',
]

function ResultsSidebar({ stats, onExport }) {
  return (
    <aside className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 p-0 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="flex items-center gap-3 border-b-2 border-sky-700/60 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/80 bg-sky-100 text-sky-700">
          <BarChart3 size={18} />
        </div>
        <h2 className="text-[1.05rem] font-bold tracking-[-0.03em] text-slate-800">Simulation Results</h2>
      </div>

      <div className="grid grid-cols-2 gap-3 p-4">
        <div className="min-h-[118px] rounded-2xl border-2 border-sky-700/70 bg-white/25 p-3">
          <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/70 bg-sky-100 text-sky-700"><MapPinned size={18} /></div>
          <div className="text-[1.15rem] font-black tracking-[-0.04em] text-slate-800">{stats.floodArea} km²</div>
          <div className="text-xs font-bold text-slate-600">Flood Area</div>
        </div>
        <div className="min-h-[118px] rounded-2xl border-2 border-sky-700/70 bg-white/25 p-3">
          <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/70 bg-sky-100 text-sky-700"><Waves size={18} /></div>
          <div className="text-[1.15rem] font-black tracking-[-0.04em] text-slate-800">{stats.maxDepth} m</div>
          <div className="text-xs font-bold text-slate-600">Max Depth</div>
        </div>
        <div className="min-h-[118px] rounded-2xl border-2 border-sky-700/70 bg-white/25 p-3">
          <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/70 bg-emerald-100 text-emerald-700"><Gauge size={18} /></div>
          <div className="text-[1.15rem] font-black tracking-[-0.04em] text-slate-800">{stats.maxVelocity} m/s</div>
          <div className="text-xs font-bold text-slate-600">Max Velocity</div>
        </div>
        <div className="min-h-[118px] rounded-2xl border-2 border-sky-700/70 bg-white/25 p-3">
          <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/70 bg-amber-100 text-amber-700"><TimerReset size={18} /></div>
          <div className="text-[1.15rem] font-black tracking-[-0.04em] text-slate-800">{stats.arrivalTime} min</div>
          <div className="text-xs font-bold text-slate-600">Arrival Time</div>
        </div>
      </div>

      <div className="px-4 pb-0 pt-2">
        <div className="mb-2 flex justify-between text-[0.7rem] font-bold text-slate-500">
          <span>0 min</span>
          <span>60 min</span>
        </div>
        <div className="relative h-2 overflow-hidden rounded-full border border-sky-700/60 bg-sky-200/60">
          <div className="absolute inset-y-0 left-[12%] w-[52%] rounded-full bg-gradient-to-r from-sky-500 to-sky-700" />
          <div className="absolute left-[56%] top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-sky-700 bg-white" />
        </div>
      </div>

      <div className="mx-4 mt-5 rounded-2xl border-2 border-sky-700/70 bg-white/25 p-3">
        <div className="mb-3 text-[0.98rem] font-extrabold text-slate-800">Model Comparison</div>
        <div className="grid grid-cols-2 gap-2.5">
          <div className="rounded-xl border-2 border-sky-700/70 bg-sky-100/70 p-2.5">
            <div className="mb-2 text-xs font-extrabold text-slate-800">SPH</div>
            <div className="mb-1 flex justify-between gap-2 text-[0.68rem] text-slate-600"><span>Flood Area</span><strong className="text-slate-800">{stats.floodArea} km²</strong></div>
            <div className="mb-1 flex justify-between gap-2 text-[0.68rem] text-slate-600"><span>Max Depth</span><strong className="text-slate-800">{stats.maxDepth} m</strong></div>
            <div className="flex justify-between gap-2 text-[0.68rem] text-slate-600"><span>Max Velocity</span><strong className="text-slate-800">{stats.maxVelocity} m/s</strong></div>
          </div>
          <div className="rounded-xl border-2 border-emerald-700/70 bg-emerald-100/70 p-2.5">
            <div className="mb-2 text-xs font-extrabold text-slate-800">Delft3D</div>
            <div className="mb-1 flex justify-between gap-2 text-[0.68rem] text-slate-600"><span>Flood Area</span><strong className="text-slate-800">{(Number(stats.floodArea) * 0.96).toFixed(1)} km²</strong></div>
            <div className="mb-1 flex justify-between gap-2 text-[0.68rem] text-slate-600"><span>Max Depth</span><strong className="text-slate-800">{(Number(stats.maxDepth) * 0.96).toFixed(1)} m</strong></div>
            <div className="flex justify-between gap-2 text-[0.68rem] text-slate-600"><span>Max Velocity</span><strong className="text-slate-800">{(Number(stats.maxVelocity) * 0.95).toFixed(1)} m/s</strong></div>
          </div>
        </div>
        <button type="button" className="mt-3 inline-flex items-center gap-2 text-sm font-bold text-slate-700">
          View Detailed Comparison <ArrowRight size={16} />
        </button>
      </div>

      <div className="mx-4 mt-5 mb-4 rounded-2xl border-2 border-sky-700/70 bg-white/25 p-3">
        <div className="mb-2 text-[0.98rem] font-extrabold text-slate-800">Export Results</div>
        {exportItems.map((item) => (
          <button key={item} type="button" className="mt-2 flex w-full items-center gap-3 rounded-xl border-2 border-sky-700/70 bg-white/30 px-3 py-2.5 text-left text-sm font-semibold text-slate-700 transition hover:bg-sky-100" onClick={() => onExport(item)}>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-sky-700/70 bg-sky-100 text-sky-700"><Download size={15} /></span>
            <span>{item}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}

export default ResultsSidebar
