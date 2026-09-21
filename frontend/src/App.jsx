import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Header from './components/Header'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import Analysis from './pages/Analysis'
import Comparision from './pages/Comparision'
import Simulation from './pages/Simulation'
import Exports from './pages/Exports'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-100 text-slate-800">
        <Header />

        <main className="mx-auto w-full max-w-[1700px] px-4 py-5 md:px-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/landing" element={<Landing />} />
            <Route path="/simulations" element={<Simulation />} />
            <Route path="/scenarios" element={<Comparision />} />
            <Route path="/analysis" element={<Analysis />} />
            <Route path="/exports" element={<Exports />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
