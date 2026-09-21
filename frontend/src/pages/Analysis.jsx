function Analysis() {
  return (
    <div className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/85 p-8 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <h1 className="text-3xl font-black tracking-[-0.05em] text-sky-700">Analytics Overview</h1>
      <div className="mt-6 grid gap-4 md:grid-cols-4">
        {[
          ['Flood Area', '42.6 km²'],
          ['Max Depth', '4.8 m'],
          ['Max Velocity', '6.2 m/s'],
          ['Arrival Time', '38 min'],
        ].map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-sky-700/60 bg-white/40 p-5">
            <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">{label}</div>
            <div className="mt-3 text-2xl font-black text-slate-800">{value}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default Analysis