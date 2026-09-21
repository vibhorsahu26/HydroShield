import { CheckCircle2, Cloud, Layers3, Satellite, Target } from 'lucide-react'

function Analysis() {
  return (
    <div className="space-y-4">
      <section className="rounded-3xl border-2 border-sky-700/80 bg-slate-950 p-6 text-white shadow-[0_6px_0_rgba(25,64,83,0.12)]">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div><div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em] text-cyan-300"><Satellite size={15} /> Earth observation validation</div><h1 className="text-3xl font-black tracking-tighter">Model versus satellite</h1><p className="mt-2 text-sm text-slate-300">Kosi Dam / Major Breach / Sentinel-1 surface-water extent</p></div>
          <div className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-right"><div className="text-xs font-bold uppercase tracking-wider text-emerald-300">Agreement score</div><div className="mt-1 text-2xl font-black text-white">84.6%</div></div>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_0.8fr]">
        <section className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/85 p-4 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
          <div className="mb-4 flex items-center justify-between"><div><h2 className="text-lg font-black text-slate-800">Extent agreement</h2><p className="text-xs font-semibold text-slate-500">Common grid comparison at 30 m resolution</p></div><Layers3 size={19} className="text-sky-700" /></div>
          <div className="relative h-70 overflow-hidden rounded-xl border-2 border-sky-700/50 bg-linear-to-br from-emerald-200 via-green-300 to-lime-200">
            <div className="absolute left-[13%] top-[18%] h-[73%] w-[69%] rotate-[-8deg] rounded-[48%_42%_55%_38%] bg-sky-400/70" />
            <div className="absolute left-[22%] top-[25%] h-[57%] w-[52%] rotate-[-8deg] rounded-[48%_42%_55%_38%] border-4 border-dashed border-yellow-300 bg-yellow-300/30" />
            <div className="absolute bottom-3 left-3 flex flex-wrap gap-2 text-[0.68rem] font-bold"><span className="rounded-md bg-sky-700 px-2 py-1 text-white">Modelled only</span><span className="rounded-md bg-yellow-400 px-2 py-1 text-slate-950">Observed only</span><span className="rounded-md bg-emerald-700 px-2 py-1 text-white">Overlap</span></div>
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2 text-center"><div className="rounded-lg bg-sky-100 p-2"><div className="text-lg font-black text-sky-800">6.6</div><div className="text-[0.68rem] font-bold text-slate-500">Model only km²</div></div><div className="rounded-lg bg-emerald-100 p-2"><div className="text-lg font-black text-emerald-800">36.0</div><div className="text-[0.68rem] font-bold text-slate-500">Overlap km²</div></div><div className="rounded-lg bg-yellow-100 p-2"><div className="text-lg font-black text-amber-800">4.8</div><div className="text-[0.68rem] font-bold text-slate-500">Observed only km²</div></div></div>
        </section>

        <section className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/85 p-4 shadow-[0_6px_0_rgba(25,64,83,0.12)]"><h2 className="text-lg font-black text-slate-800">Validation inputs</h2><div className="mt-4 space-y-3">{[['Model extent', 'Major Breach simulation', '42.6 km²', CheckCircle2], ['Observed extent', 'OPERA DSWx-S1', '40.8 km²', Satellite], ['Common grid', 'EPSG:4326 / 30 m', 'Ready', Target]].map(([label, detail, value, Icon]) => <div key={label} className="flex items-center gap-3 rounded-xl border border-sky-700/30 bg-white/50 p-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-100 text-sky-700"><Icon size={17} /></div><div className="min-w-0 flex-1"><div className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</div><div className="truncate text-sm font-bold text-slate-800">{detail}</div></div><div className="text-right text-xs font-black text-slate-700">{value}</div></div>)}</div><div className="mt-4 flex items-start gap-2 rounded-xl border border-sky-700/30 bg-white/50 p-3 text-xs font-semibold leading-5 text-slate-600"><Cloud size={16} className="mt-0.5 shrink-0 text-sky-700" /> Observation is radar-derived and can include permanent water, vegetation and terrain classification uncertainty.</div></section>
      </div>

      <section className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/85 p-4 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
        <h2 className="text-lg font-black text-slate-800">Hydrodynamic outputs</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
        {[
          ['Flood Area', '42.6 km²'],
          ['Max Depth', '4.8 m'],
          ['Max Velocity', '6.2 m/s'],
          ['Arrival Time', '38 min'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-sky-700/40 bg-white/50 p-4">
            <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">{label}</div>
            <div className="mt-3 text-2xl font-black text-slate-800">{value}</div>
          </div>
        ))}
        </div>
        </section>
    </div>
  )
}

export default Analysis