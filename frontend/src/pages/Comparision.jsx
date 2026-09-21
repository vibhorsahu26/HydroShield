import { Check, ChevronRight, GitCompareArrows, Map, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'

const scenarios = [
  { name: 'Major Breach', tag: 'Planning case', area: 42.6, depth: 4.8, velocity: 6.2, arrival: 38, color: 'bg-rose-500' },
  { name: 'Partial Breach', tag: 'Moderate case', area: 28.4, depth: 3.5, velocity: 4.8, arrival: 46, color: 'bg-amber-500' },
  { name: 'Controlled Release', tag: 'Managed release', area: 18.1, depth: 2.2, velocity: 3.2, arrival: 58, color: 'bg-emerald-500' },
]

function Comparision() {
  const [selected, setSelected] = useState(['Major Breach', 'Partial Breach'])
  const selectedScenarios = scenarios.filter(({ name }) => selected.includes(name))

  const toggleScenario = (name) => {
    setSelected((current) => current.includes(name)
      ? current.filter((item) => item !== name)
      : current.length < 2 ? [...current, name] : [current[1], name])
  }

  return (
    <div className="space-y-4">
      <section className="rounded-3xl border-2 border-sky-700/80 bg-slate-950 p-6 text-white shadow-[0_6px_0_rgba(25,64,83,0.12)]">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-cyan-300"><GitCompareArrows size={15} /> What-if analysis</div>
            <h1 className="text-3xl font-black tracking-tighter">Scenario comparison</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-300">Compare two breach conditions on the same Kosi Dam study domain.</p>
          </div>
          <button type="button" className="inline-flex items-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-sm font-bold text-white hover:bg-white/15"><Map size={16} /> View on map</button>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/85 p-4 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
          <div className="mb-3 flex items-center gap-2 text-sm font-black text-slate-800"><SlidersHorizontal size={17} /> Select scenarios</div>
          <p className="mb-4 text-xs font-semibold leading-5 text-slate-500">Choose up to two scenarios to compare side by side.</p>
          <div className="space-y-2">
            {scenarios.map(({ name, tag, color }) => {
              const isSelected = selected.includes(name)
              return <button key={name} type="button" onClick={() => toggleScenario(name)} className={`flex w-full items-center gap-3 rounded-xl border-2 p-3 text-left transition ${isSelected ? 'border-sky-700 bg-white' : 'border-sky-700/30 bg-white/30 hover:bg-white/70'}`}>
                <span className={`flex h-5 w-5 items-center justify-center rounded-md ${isSelected ? 'bg-sky-700 text-white' : 'border-2 border-slate-300 bg-white text-transparent'}`}><Check size={13} /></span>
                <span><span className="block text-sm font-bold text-slate-800">{name}</span><span className="block text-xs font-semibold text-slate-500">{tag}</span></span>
                <span className={`ml-auto h-2.5 w-2.5 rounded-full ${color}`} />
              </button>
            })}
          </div>
          <div className="mt-5 rounded-xl border border-amber-300/70 bg-amber-50 p-3 text-xs font-semibold leading-5 text-amber-950">All values are scenario estimates based on the current terrain and breach assumptions.</div>
        </aside>

        <div className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/85 p-4 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
          <div className="mb-4 flex items-center justify-between gap-3"><div><h2 className="text-lg font-black text-slate-800">Impact comparison</h2><p className="text-xs font-semibold text-slate-500">Maximum values across the selected run</p></div><span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">Same study domain</span></div>
          <div className="overflow-x-auto rounded-xl border border-sky-700/40 bg-white/50">
            <table className="min-w-full text-left text-sm text-slate-700">
              <thead className="bg-sky-100/80 text-sky-800"><tr><th className="px-4 py-3 font-bold">Metric</th>{selectedScenarios.map(({ name }) => <th key={name} className="px-4 py-3 font-bold">{name}</th>)}</tr></thead>
              <tbody>{[['Flood area', 'area', 'km²'], ['Max depth', 'depth', 'm'], ['Max velocity', 'velocity', 'm/s'], ['Arrival time', 'arrival', 'min']].map(([label, key, unit]) => <tr key={key} className="border-t border-sky-700/30"><td className="px-4 py-3 font-bold text-slate-800">{label}</td>{selectedScenarios.map((scenario) => <td key={scenario.name} className="px-4 py-3 font-semibold">{scenario[key]} {unit}</td>)}</tr>)}</tbody>
            </table>
          </div>
          {selectedScenarios.length === 2 && <div className="mt-5 grid gap-3 md:grid-cols-2">{selectedScenarios.map(({ name, area, color }) => <div key={name} className="rounded-xl border border-sky-700/40 bg-white/50 p-3"><div className="mb-2 flex justify-between text-xs font-bold text-slate-600"><span>{name}</span><span>{area} km²</span></div><div className="h-3 overflow-hidden rounded-full bg-slate-200"><div className={`h-full rounded-full ${color}`} style={{ width: `${(area / 45) * 100}%` }} /></div></div>)}</div>}
          <button type="button" className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-sky-800">Open detailed analysis <ChevronRight size={16} /></button>
        </div>
      </section>
    </div>
  )
}

export default Comparision