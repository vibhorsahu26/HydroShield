function Comparision() {
  return (
    <div className="rounded-[24px] border-2 border-sky-700/80 bg-sky-50/85 p-8 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <h1 className="text-3xl font-black tracking-[-0.05em] text-sky-700">Scenario Comparison</h1>
      <div className="mt-6 overflow-hidden rounded-2xl border border-sky-700/60 bg-white/40">
        <table className="min-w-full text-left text-sm text-slate-700">
          <thead className="bg-sky-100/80 text-sky-800">
            <tr>
              <th className="px-4 py-3 font-bold">Scenario</th>
              <th className="px-4 py-3 font-bold">Flood Area</th>
              <th className="px-4 py-3 font-bold">Max Depth</th>
              <th className="px-4 py-3 font-bold">Velocity</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Major Breach', '42.6 km²', '4.8 m', '6.2 m/s'],
              ['Partial Breach', '28.4 km²', '3.5 m', '4.8 m/s'],
              ['Controlled Release', '18.1 km²', '2.2 m', '3.2 m/s'],
            ].map(([scenario, area, depth, velocity]) => (
              <tr key={scenario} className="border-t border-sky-700/40">
                <td className="px-4 py-3 font-semibold text-slate-800">{scenario}</td>
                <td className="px-4 py-3">{area}</td>
                <td className="px-4 py-3">{depth}</td>
                <td className="px-4 py-3">{velocity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Comparision