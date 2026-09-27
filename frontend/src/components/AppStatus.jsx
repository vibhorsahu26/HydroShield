import { AlertTriangle, CheckCircle2, LoaderCircle, X } from 'lucide-react'
import { useHydroShield } from '../state/HydroShieldContext'

function AppStatus() {
  const { apiStatus, error, clearError, busy } = useHydroShield()
  return (
    <div className="mx-auto w-[calc(100%-2rem)] max-w-[1700px] space-y-2 pt-2">
      {apiStatus === 'checking' && <div className="flex items-center gap-2 rounded-xl border border-slate-300 bg-white/80 px-3 py-2 text-xs font-bold text-slate-600"><LoaderCircle size={15} className="animate-spin" /> Connecting to HydroShield backend…</div>}
      {apiStatus === 'online' && !busy && <div className="flex items-center gap-2 rounded-xl border border-emerald-300/70 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-800"><CheckCircle2 size={15} /> Backend connected</div>}
      {apiStatus === 'offline' && <div className="flex items-center gap-2 rounded-xl border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-bold text-rose-900"><AlertTriangle size={15} /> Backend unavailable. Check API URL and backend readiness.</div>}
      {error && <div className="flex items-start gap-2 rounded-xl border border-rose-300 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-900"><AlertTriangle size={15} className="mt-0.5 shrink-0" /><span>{error}</span><button type="button" className="ml-auto" onClick={clearError} aria-label="Dismiss error"><X size={15} /></button></div>}
    </div>
  )
}
export default AppStatus
