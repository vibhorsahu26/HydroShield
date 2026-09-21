import { ChevronDown, CirclePlay, Gauge } from 'lucide-react'

function SimulationSidebar({ form, onInputChange, onRunSimulation, isRunning, simulationMessage }) {
  return (
    <aside className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 p-0 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="flex items-center gap-3 border-b-2 border-sky-700/60 bg-white/10 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/80 bg-sky-100 text-sky-700">
          <Gauge size={18} />
        </div>
        <h2 className="text-[1.05rem] font-bold tracking-[-0.03em] text-slate-800">Simulation Setup</h2>
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">1</span>
          <span>Select Region</span>
          <ChevronDown size={16} className="ml-auto text-slate-600" />
        </div>

        <label className="mb-2 block text-sm font-semibold text-slate-600">River</label>
        <select name="river" value={form.river} onChange={onInputChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none">
          <option value="Kosi">Kosi</option>
          <option value="Ganga">Ganga</option>
          <option value="Yamuna">Yamuna</option>
        </select>

        <label className="mb-2 mt-4 block text-sm font-semibold text-slate-600">Dam</label>
        <select name="dam" value={form.dam} onChange={onInputChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none">
          <option value="Kosi Dam">Kosi Dam</option>
          <option value="Tehri Dam">Tehri Dam</option>
          <option value="Sardar Sarovar">Sardar Sarovar</option>
        </select>
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">2</span>
          <span>Scenario</span>
          <ChevronDown size={16} className="ml-auto text-slate-600" />
        </div>
        <select name="scenario" value={form.scenario} onChange={onInputChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/60 px-3 text-slate-700 outline-none">
          <option value="Major Breach">Major Breach</option>
          <option value="Partial Breach">Partial Breach</option>
          <option value="Controlled Release">Controlled Release</option>
        </select>
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">3</span>
          <span>Breach Parameters</span>
        </div>

        <label className="mb-2 block text-sm font-semibold text-slate-600">Breach Width (m)</label>
        <input type="number" name="breachWidth" value={form.breachWidth} onChange={onInputChange} className="mb-3 h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/50 px-3 text-slate-700 outline-none" />

        <label className="mb-2 block text-sm font-semibold text-slate-600">Breach Formation Time (min)</label>
        <input type="number" name="breachTime" value={form.breachTime} onChange={onInputChange} className="mb-3 h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/50 px-3 text-slate-700 outline-none" />

        <label className="mb-2 block text-sm font-semibold text-slate-600">Initial Water Level (m)</label>
        <input type="number" name="waterLevel" value={form.waterLevel} onChange={onInputChange} className="h-10 w-full rounded-xl border-2 border-sky-700/80 bg-white/50 px-3 text-slate-700 outline-none" />
      </div>

      <div className="border-b border-sky-700/40 px-4 py-4">
        <div className="mb-3 flex items-center gap-2 font-bold text-slate-800">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg border border-sky-700/80 bg-sky-100 text-xs">4</span>
          <span>Model</span>
        </div>
        <div className="flex items-center gap-3 py-1 font-semibold text-slate-700">
          <input type="checkbox" name="sph" checked={form.sph} onChange={onInputChange} className="h-4 w-4 accent-sky-600" />
          <span>SPH</span>
        </div>
        <div className="mt-2 flex items-center gap-3 py-1 font-semibold text-slate-700">
          <input type="checkbox" name="delft" checked={form.delft} onChange={onInputChange} className="h-4 w-4 accent-sky-600" />
          <span>Delft3D</span>
        </div>
      </div>

      <button type="button" className="mx-auto mt-5 flex w-[calc(100%-28px)] items-center justify-center gap-2 rounded-xl bg-gradient-to-b from-sky-500 to-sky-700 px-4 py-3.5 text-base font-bold text-white shadow-[0_6px_0_rgba(16,64,114,0.22)] transition hover:brightness-105" onClick={onRunSimulation}>
        <CirclePlay size={18} />
        {isRunning ? 'Running...' : 'Run Simulation'}
      </button>

      <div className="mx-4 mb-4 mt-3 flex items-center gap-2 rounded-xl border border-sky-700/40 bg-sky-100/70 px-3 py-2 text-xs font-bold text-slate-600">
        <span className={`h-2.5 w-2.5 rounded-full ${isRunning ? 'bg-amber-400' : 'bg-emerald-500'}`} />
        {simulationMessage}
      </div>
    </aside>
  )
}

export default SimulationSidebar
