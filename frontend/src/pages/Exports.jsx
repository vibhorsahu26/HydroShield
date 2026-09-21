function Exports() {
  return (
    <div className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/85 p-8 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <h1 className="text-3xl font-black tracking-[-0.05em] text-sky-700">Export Center</h1>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {[
          ['Flood Extent (SHP)', 'Download'],
          ['Water Depth (GeoTIFF)', 'Download'],
          ['Simulation Report (PDF)', 'Download'],
          ['All Data (KML/GeoJSON)', 'Download'],
        ].map(([name, label]) => (
          <button key={name} type="button" className="flex items-center justify-between rounded-2xl border border-sky-700/60 bg-white/40 p-5 text-left text-slate-700 transition hover:bg-sky-100/50">
            <span className="font-bold text-slate-800">{name}</span>
            <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-bold text-sky-800">{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default Exports