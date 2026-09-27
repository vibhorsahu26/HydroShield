import { Building2, Landmark, MapPinned, Route } from 'lucide-react'

function displayCount(value) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString() : '—'
}

function displayRoads(value) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(2)} km` : '—'
}

function ImpactPanel({ stats }) {
  const items = [
    ['Settlements', stats.settlements, 'affected', 'bg-rose-200', MapPinned],
    ['Roads', stats.roads, 'intersected', 'bg-amber-200', Route],
    ['Bridges', stats.bridges, 'affected', 'bg-violet-200', Landmark],
    ['Critical infrastructure', stats.hospitals, 'affected', 'bg-sky-200', Building2],
  ]
  const hasExposure = items.some(([, value]) => value !== '—' && value !== null && value !== undefined)
  const area = Number.isFinite(Number(stats.exposedAreaKm2)) ? `${Number(stats.exposedAreaKm2).toFixed(2)} km²` : '—'

  return <section className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 shadow-sm">
    <div className="flex items-center justify-between border-b-2 border-sky-700/60 px-4 py-4">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/80 bg-sky-100 text-sky-700"><MapPinned size={18}/></div>
        <div><h2 className="text-[1.05rem] font-bold">Impact Analysis</h2><p className="text-[0.68rem] font-semibold text-slate-500">Exposure inside the mapped flood extent</p></div>
      </div>
      <div className="rounded-full border border-sky-700/25 bg-white/70 px-2.5 py-1 text-[0.67rem] font-extrabold text-sky-800">{area} flooded</div>
    </div>
    <div className="grid grid-cols-2 gap-3 p-4">
      {items.map(([label, value, detail, tone, Icon]) => {
        const rendered = label === 'Roads' ? displayRoads(value) : displayCount(value)
        return <div key={label} className={`flex min-h-[110px] flex-col items-start justify-center gap-2 rounded-[18px] border-2 border-sky-700/80 p-3 ${tone}`}>
          <Icon size={19}/><div className="text-[1.5rem] font-black">{rendered}</div><div className="text-[0.72rem] font-bold">{detail}</div>
        </div>
      })}
    </div>
    <div className="mx-4 mb-4 rounded-xl border border-sky-700/20 bg-white/55 px-3 py-2 text-[0.68rem] font-semibold leading-4 text-slate-500">
      {hasExposure ? 'Exposure metrics are linked to the current flood result and update with each completed analysis.' : 'Run a simulation and complete result processing to populate exposure metrics.'}
    </div>
  </section>
}

export default ImpactPanel
