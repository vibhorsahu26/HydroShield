function Landing() {
  return (
    <div className="rounded-3xl border-2 border-sky-700/80 bg-sky-50/85 p-8 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="mb-6 text-4xl font-black tracking-[-0.06em] text-sky-700">HydroShield</div>
      <p className="max-w-2xl text-lg text-slate-700">
        Short-term flood risk modeling, dam breach simulation, and impact analysis for critical infrastructure planning.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <div className="rounded-2xl border border-sky-700/60 bg-white/40 p-5">
          <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">Scenario</div>
          <div className="mt-3 text-2xl font-black text-slate-800">Major Breach</div>
        </div>
        <div className="rounded-2xl border border-sky-700/60 bg-white/40 p-5">
          <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">Flood Area</div>
          <div className="mt-3 text-2xl font-black text-slate-800">42.6 km²</div>
        </div>
        <div className="rounded-2xl border border-sky-700/60 bg-white/40 p-5">
          <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">Risk Level</div>
          <div className="mt-3 text-2xl font-black text-slate-800">High</div>
        </div>
      </div>
    </div>
  )
}

export default Landing