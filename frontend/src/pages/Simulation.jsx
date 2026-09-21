function Simulation() {
  return (
    <div className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/85 p-8 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <h1 className="text-3xl font-black tracking-[-0.05em] text-sky-700">Simulation Queue</h1>
      <div className="mt-6 grid gap-4 md:grid-cols-3">
        {[
          ['Active Run', 'Kosi Dam / Major Breach', 'Completed'],
          ['Queued', 'Tehri / Partial Breach', 'Waiting'],
          ['Archive', 'Sardar Sarovar / Controlled', 'Ready'],
        ].map(([title, detail, status]) => (
          <div key={title} className="rounded-2xl border border-sky-700/60 bg-white/40 p-5">
            <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">{title}</div>
            <div className="mt-3 text-xl font-bold text-slate-800">{detail}</div>
            <div className="mt-4 inline-flex rounded-full bg-sky-100 px-3 py-1 text-xs font-bold text-sky-800">{status}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default Simulation