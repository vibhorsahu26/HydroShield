import { useState } from 'react'
import { Layers3, Search } from 'lucide-react'
import MapView from './MapView'

const defaultLayerItems = [
  'River',
  'Dam',
  'Flood Extent',
  'Water Depth',
  'Velocity',
  'Arrival Time',
  'Roads',
  'Settlements',
  'Infrastructure',
  'Satellite',
]

function MapPanel({ activeLayer, setActiveLayer, scenario }) {
  const [visibleLayers, setVisibleLayers] = useState({
    River: true,
    Dam: true,
    'Flood Extent': true,
    Settlements: true,
  })

  const toggleLayer = (layer) => {
    setVisibleLayers((current) => ({ ...current, [layer]: !current[layer] }))
  }

  return (
    <section className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="relative h-[560px] overflow-hidden rounded-[18px] border-2 border-sky-700/70 bg-[linear-gradient(120deg,rgba(147,196,114,0.9),rgba(90,136,75,0.86))] m-[10px_10px_0]">
        <div className="absolute left-4 top-4 z-[500] flex w-[260px] items-center gap-2 rounded-xl border-2 border-sky-700/80 bg-white/85 px-3 py-2 text-sm text-slate-500 shadow-lg backdrop-blur-sm">
          <Search size={16} />
          <span>Search location...</span>
        </div>

        <div className="absolute bottom-4 left-4 z-[500] rounded-xl border-2 border-sky-700/80 bg-slate-950/90 px-3 py-2 text-white shadow-lg backdrop-blur-sm">
          <div className="text-[0.65rem] font-bold uppercase tracking-[0.12em] text-cyan-300">Active scenario</div>
          <div className="mt-0.5 text-sm font-black">{scenario} <span className="font-normal text-slate-400">/ {activeLayer}</span></div>
        </div>

        <div className="absolute right-4 top-4 z-[500] w-[220px] rounded-xl border-2 border-sky-700/80 bg-slate-50/90 p-2 shadow-xl backdrop-blur-sm">
          <div className="mb-1.5 flex items-center gap-2 text-[0.85rem] font-bold text-slate-800">
            <Layers3 size={15} />
            <span>Layers</span>
          </div>
          <div className="grid gap-1">
            {defaultLayerItems.map((item) => (
              <label key={item} className="flex items-center gap-2 text-[0.8rem] text-slate-700">
                <input type="checkbox" checked={visibleLayers[item] ?? false} onChange={() => toggleLayer(item)} className="h-3.5 w-3.5 accent-sky-600" />
                <span>{item}</span>
              </label>
            ))}
          </div>
        </div>

        <MapView visibleLayers={visibleLayers} activeLayer={activeLayer} />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 bg-sky-50/80 px-4 pb-4 pt-3">
        <div>
          <div className="text-base font-bold text-slate-800">Visualization</div>
          <div className="mt-0.5 text-xs font-semibold text-slate-500">Showing {activeLayer.toLowerCase()} layer</div>
        </div>
        <div className="flex flex-wrap gap-2.5">
          {['Flood Extent', 'Water Depth', 'Velocity', 'Arrival Time'].map((label) => (
            <button
              key={label}
              type="button"
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${
                activeLayer === label
                  ? 'border-sky-700/70 bg-sky-100 text-sky-800'
                  : 'border-sky-700/50 bg-white/20 text-slate-700'
              }`}
              onClick={() => setActiveLayer(label)}
            >
              <span className={`h-2.5 w-2.5 rounded-full ${activeLayer === label ? 'bg-sky-500' : 'bg-slate-400'}`} />
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

export default MapPanel