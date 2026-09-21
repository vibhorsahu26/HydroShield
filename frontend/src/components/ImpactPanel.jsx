import { Building2, Landmark, MapPinned, Route } from 'lucide-react'

function ImpactPanel({ stats }) {
  const impactItems = [
    { label: 'Settlements', value: stats.settlements, detail: 'innundated', tone: 'bg-rose-200', icon: <MapPinned size={18} /> },
    { label: 'Roads', value: `${stats.roads} km`, detail: 'affected', tone: 'bg-amber-200', icon: <Route size={18} /> },
    { label: 'Bridges', value: stats.bridges, detail: 'affected', tone: 'bg-violet-200', icon: <Landmark size={18} /> },
    { label: 'Hospitals', value: stats.hospitals, detail: 'affected', tone: 'bg-sky-200', icon: <Building2 size={18} /> },
  ]

  return (
    <div className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="flex items-center gap-3 border-b-2 border-sky-700/60 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/80 bg-sky-100 text-sky-700">
          <MapPinned size={18} />
        </div>
        <h2 className="text-[1.05rem] font-bold tracking-[-0.03em] text-slate-800">Impact Analysis</h2>
      </div>

      <div className="grid grid-cols-2 gap-3 p-4">
        {impactItems.map(({ label, value, detail, tone, icon }) => (
          <div key={label} className={`flex min-h-[110px] flex-col items-start justify-center gap-2 rounded-[18px] border-2 border-sky-700/80 p-3 ${tone}`}>
            <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-sky-700/50 bg-white/35 text-slate-700">{icon}</div>
            <div className="text-[1.5rem] font-black tracking-[-0.04em] text-slate-800">{value}</div>
            <div className="text-[0.72rem] font-bold lowercase text-slate-700">{detail}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default ImpactPanel
