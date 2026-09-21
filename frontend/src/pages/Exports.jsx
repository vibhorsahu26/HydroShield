import { CheckCircle2, Download, FileArchive, FileJson, FileSpreadsheet, ImageDown } from 'lucide-react'

function Exports() {
  const exportItems = [['Flood extent', 'GeoJSON boundary for web maps', 'GeoJSON', FileJson, 'Ready'], ['Water depth raster', 'Georeferenced depth surface', 'GeoTIFF', ImageDown, 'Ready'], ['Simulation report', 'Assumptions, methods and results', 'PDF', FileArchive, 'Ready'], ['Impact inventory', 'Settlements, roads and facilities', 'CSV', FileSpreadsheet, 'Ready']]

  const download = (name, format) => {
    const content = JSON.stringify({ file: name, format, study: 'Kosi Dam / Major Breach', generatedAt: new Date().toISOString() }, null, 2)
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([content], { type: 'application/json' }))
    link.download = `${name.toLowerCase().replaceAll(' ', '-')}.${format.toLowerCase()}.json`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="space-y-4"><section className="rounded-3xl border-2 border-sky-700/80 bg-slate-950 p-6 text-white shadow-[0_6px_0_rgba(25,64,83,0.12)]"><div className="mb-2 text-xs font-bold uppercase tracking-[0.14em] text-cyan-300">GIS-ready outputs</div><h1 className="text-3xl font-black tracking-tighter">Export center</h1><p className="mt-2 text-sm text-slate-300">Download outputs generated from Kosi Dam / Major Breach / Run HS-2026-0921-01.</p></section><section className="grid gap-3 md:grid-cols-2">{exportItems.map(([name, detail, format, Icon, status]) => <div key={name} className="flex items-center gap-4 rounded-[20px] border-2 border-sky-700/70 bg-sky-50/85 p-4 shadow-[0_5px_0_rgba(25,64,83,0.1)]"><div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-sky-100 text-sky-700"><Icon size={20} /></div><div className="min-w-0 flex-1"><div className="text-sm font-black text-slate-800">{name}</div><div className="mt-1 text-xs font-semibold text-slate-500">{detail}</div><div className="mt-2 flex items-center gap-2"><span className="rounded-md bg-slate-200 px-2 py-1 text-[0.65rem] font-black text-slate-600">{format}</span><span className="inline-flex items-center gap-1 text-[0.68rem] font-bold text-emerald-700"><CheckCircle2 size={13} /> {status}</span></div></div><button type="button" onClick={() => download(name, format)} aria-label={`Download ${name}`} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-700 text-white transition hover:bg-sky-800"><Download size={17} /></button></div>)}</section><div className="flex items-start gap-3 rounded-2xl border border-amber-300/70 bg-amber-50 px-4 py-3 text-xs font-semibold leading-5 text-amber-950"><FileArchive size={17} className="mt-0.5 shrink-0 text-amber-600" /> Prototype downloads currently contain run metadata. Connect the backend exporters to generate production SHP, KML, GeoJSON and GeoTIFF files.</div>
    </div>
  )
}

export default Exports