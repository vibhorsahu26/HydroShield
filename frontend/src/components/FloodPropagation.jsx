import { Cloud } from 'lucide-react'

const timeSteps = ['0 min', '30 min', '60 min', '120 min']

function FloodPropagation() {
  return (
    <div className="rounded-[20px] border-2 border-sky-700/80 bg-sky-50/80 pb-4 shadow-[0_6px_0_rgba(25,64,83,0.12)]">
      <div className="flex items-center gap-3 border-b-2 border-sky-700/60 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-sky-700/80 bg-sky-100 text-sky-700">
          <Cloud size={18} />
        </div>
        <h2 className="text-[1.05rem] font-bold tracking-[-0.03em] text-slate-800">Flood Propagation</h2>
      </div>

      <div className="grid grid-cols-4 gap-3 px-4 pb-1 pt-4">
        {timeSteps.map((label, index) => (
          <div key={label} className="flex flex-col items-center gap-2">
            <div className="relative h-[100px] w-full overflow-hidden rounded-xl border-2 border-sky-700/70 bg-gradient-to-br from-emerald-200 to-green-300">
              <div className="absolute inset-0 bg-gradient-to-r from-sky-300/70 to-sky-500/80 [clip-path:polygon(10%_60%,35%_54%,56%_62%,70%_50%,75%_25%,100%_18%,100%_100%,0_100%)]" />
              <div className={`absolute left-[44%] top-[33%] h-10 w-12 rotate-[12deg] rounded-[50%_50%_55%_45%/58%_42%_58%_42%] border-2 border-sky-700/60 ${index === 0 ? 'bg-sky-300/70' : 'bg-sky-400/80'}`} />
            </div>
            <span className="text-xs font-bold text-slate-500">{label}</span>
          </div>
        ))}
      </div>

      <div className="relative mx-auto mt-4 h-[18px] w-[calc(100%-36px)]">
        <div className="absolute inset-x-0 top-2 h-2 rounded-full border border-sky-700/60 bg-sky-200/60" />
        <div className="absolute left-[72%] top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-sky-700 bg-white" />
      </div>
    </div>
  )
}

export default FloodPropagation
