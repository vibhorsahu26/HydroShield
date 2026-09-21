import { useMemo, useState } from 'react'
import SimulationSidebar from '../components/SimulationSidebar'
import MapPanel from '../components/MapPanel'
import ResultsSidebar from '../components/ResultsSidebar'
import ImpactPanel from '../components/ImpactPanel'
import FloodPropagation from '../components/FloodPropagation'
import { Activity, AlertTriangle, CalendarDays, MapPinned } from 'lucide-react'

const baseScenario = {
  river: 'Kosi',
  dam: 'Kosi Dam',
  scenario: 'Major Breach',
  breachWidth: 50,
  breachTime: 30,
  waterLevel: 120,
  sph: true,
  delft: true,
}

function Dashboard() {
  const [form, setForm] = useState(baseScenario)
  const [activeLayer, setActiveLayer] = useState('Flood Extent')
  const [isRunning, setIsRunning] = useState(false)
  const [simulationMessage, setSimulationMessage] = useState('Ready for scenario run')

  const stats = useMemo(() => {
    const widthFactor = Number(form.breachWidth) / 50
    const depthFactor = Number(form.waterLevel) / 120

    return {
      floodArea: (42.6 * widthFactor).toFixed(1),
      maxDepth: (4.8 * depthFactor).toFixed(1),
      maxVelocity: (6.2 * (0.8 + widthFactor / 2)).toFixed(1),
      arrivalTime: Math.max(18, Math.round(38 - widthFactor * 8)).toString(),
      settlements: Math.max(8, Math.round(12 * (0.8 + widthFactor / 2))),
      roads: Math.max(32, Math.round(48 * (0.7 + widthFactor / 2))),
      bridges: Math.max(4, Math.round(7 * (0.8 + widthFactor / 3))),
      hospitals: Math.max(1, Math.round(2 * (0.7 + depthFactor / 3))),
    }
  }, [form])

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target
    setForm((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value,
    }))
  }

  const handleRunSimulation = () => {
    setIsRunning(true)
    setSimulationMessage('Preparing terrain and model inputs...')

    window.setTimeout(() => {
      setSimulationMessage('Simulation complete. Flood map updated.')
      setIsRunning(false)
    }, 1200)
  }

  const handleExport = (filename, content) => {
    const blob = new Blob([content], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-4">
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-[20px] border-2 border-sky-700/80 bg-cyan-250 px-5 py-4 text-blue-900 font-serif">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-b-md bg-cyan-400 text-slate-950">
            <MapPinned size={20} />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-bold uppercase tracking-[0.12em] text-blue-900">
              <span>{form.river} River Basin</span>
              <span className="text-slate-500">/</span>
              <span>{form.dam}</span>
            </div>
            <h1 className="truncate text-xl font-black tracking-[-0.04em]">Dam-break inundation study</h1>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
          <span className="inline-flex items-center gap-2 rounded-full border border-blue-300 bg-emerald-400/10 px-3 py-2 text-blue-900">
            <Activity size={14} /> Scenario ready
          </span>
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-2 text-blue-900">
            <CalendarDays size={14} /> 21 Sep 2026
          </span>
        </div>
      </section>

      <div className="flex items-start gap-3 rounded-2xl border border-amber-300/70 bg-amber-50 px-4 py-3 text-sm text-amber-950 shadow-sm">
        <AlertTriangle className="mt-0.5 shrink-0 text-amber-600" size={18} />
        <p><strong>Scenario-based decision support:</strong> outputs depend on terrain, breach and boundary assumptions. This view is not an official emergency warning.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1.7fr)_360px] xl:grid-cols-[300px_minmax(0,1.8fr)_360px]">
      <SimulationSidebar
        form={form}
        onInputChange={handleInputChange}
        onRunSimulation={handleRunSimulation}
        isRunning={isRunning}
        simulationMessage={simulationMessage}
      />

      <MapPanel activeLayer={activeLayer} setActiveLayer={setActiveLayer} scenario={form.scenario} />

      <ResultsSidebar
        stats={stats}
        onExport={(label) => {
          const payload = {
            label,
            river: form.river,
            dam: form.dam,
            scenario: form.scenario,
            stats,
          }
          handleExport(`${label.replace(/\s+/g, '_').toLowerCase()}.json`, JSON.stringify(payload, null, 2))
        }}
      />

      <div className="grid gap-4 lg:col-span-3 lg:grid-cols-[0.9fr_1.35fr]">
        <ImpactPanel stats={stats} />
        <FloodPropagation />
      </div>
      </div>
    </div>
  )
}

export default Dashboard