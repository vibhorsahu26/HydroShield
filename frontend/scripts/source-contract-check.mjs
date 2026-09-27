import fs from 'node:fs'
import path from 'node:path'

const root=path.resolve(new URL('..',import.meta.url).pathname),src=path.join(root,'src'),files=[]
function walk(dir){for(const e of fs.readdirSync(dir,{withFileTypes:true})){if(e.name==='node_modules'||e.name==='dist')continue;const f=path.join(dir,e.name);if(e.isDirectory())walk(f);else if(/\.(jsx?|mjs)$/.test(e.name))files.push(f)}}
function resolveRelative(from,s){const b=path.resolve(path.dirname(from),s);return [b,`${b}.js`,`${b}.jsx`,`${b}.mjs`,path.join(b,'index.js'),path.join(b,'index.jsx')].find(fs.existsSync)}
walk(src)
const missing=[]
const re=/(?:import|export)\s+(?:[^'"`]*?\sfrom\s*)?['"](\.{1,2}\/[^'"`]+)['"]/g
let source=''
for(const f of files){const content=fs.readFileSync(f,'utf8');source += `\n${content}`;for(const m of content.matchAll(re))if(!resolveRelative(f,m[1]))missing.push(`${path.relative(root,f)} -> ${m[1]}`)}
if(missing.length){console.error(missing.join('\n'));process.exit(1)}
const requiredTokens=['searchDams','runAutomaticAcquisition','getDatasetPreview','prepareModel','auto_generate']
for(const token of requiredTokens)if(!source.includes(token)){console.error(`Automatic acquisition token missing: ${token}`);process.exit(1)}
console.log(JSON.stringify({status:'ok',source_files:files.length,relative_imports:'resolved',automatic_acquisition:'wired'},null,2))

const sidebar=fs.readFileSync(path.join(src,'components','SimulationSidebar.jsx'),'utf8');
if(!sidebar.includes('onAutoAcquire')){console.error('Automatic solver generation UI is missing');process.exit(1)}

console.log(JSON.stringify({automatic_solver_generation:'enabled',run_mode:'hidden'},null,2))
const context=fs.readFileSync(path.join(src,'state','HydroShieldContext.jsx'),'utf8')
if(!context.includes('await refreshProjectData(project.id)')){console.error('Automatic acquisition does not reconcile persisted state immediately');process.exit(1)}
if(!context.includes('refreshSimulations')){console.error('Simulation reconciliation polling is missing');process.exit(1)}
if(!context.includes('processNativeResult')){console.error('Native result processing bridge is missing');process.exit(1)}
if(!context.includes('api.processNativeResult')){console.error('Native result API reconciliation is missing');process.exit(1)}
const simulation=fs.readFileSync(path.join(src,'pages','Simulation.jsx'),'utf8')
if(!simulation.includes('refreshSimulations')){console.error('Simulation queue refresh is missing');process.exit(1)}
const dashboard=fs.readFileSync(path.join(src,'pages','Dashboard.jsx'),'utf8')
if(!dashboard.includes('autoAcquisition={autoAcquisition}')){console.error('Automatic acquisition result is not rendered immediately in the dashboard');process.exit(1)}
if(!dashboard.includes('setForm((previous) => ({')){console.error('Automatic acquisition does not reconcile form state immediately');process.exit(1)}
if(!dashboard.includes('variants.find((item) => item.code === preset')){console.error('Scenario variant lookup must use the persisted variant code');process.exit(1)}

const mapPanel=fs.readFileSync(path.join(src,'components','MapPanel.jsx'),'utf8')
const mapView=fs.readFileSync(path.join(src,'components','MapView.jsx'),'utf8')
for(const token of ['DEM','Flood Extent','Water Depth','Velocity','Arrival Time','Roads','Buildings','Settlements','Critical Infrastructure','Satellite']){
  if(!mapPanel.includes(token) || !mapView.includes(token)){console.error(`Interactive map layer contract missing: ${token}`);process.exit(1)}
}
if(!mapView.includes('/raster-preview')){console.error('DEM raster preview wiring is missing');process.exit(1)}
if(!mapView.includes('/satellite/validations/')){console.error('Satellite map layer wiring is missing');process.exit(1)}
if(!mapView.includes('eventHandlers={{ click: (event) => handleRasterSample(event.latlng) }}')){console.error('Raster overlay click sampling interaction is missing');process.exit(1)}
if(mapView.includes('ClickSampler')){console.error('Map-level sampler can duplicate raster overlay click requests');process.exit(1)}
if(!mapView.includes('linear-gradient')){console.error('Result color ramps are missing');process.exit(1)}
if(!mapView.includes('Selected location')){console.error('Raster value inspection UI is missing');process.exit(1)}
if(mapView.includes("sample.value / 60")){console.error('Arrival Time sample is being divided twice; backend already returns minutes');process.exit(1)}
if(mapView.includes("metadata.min_value) / 60") || mapView.includes("metadata.max_value) / 60")){console.error('Arrival Time legend is being divided twice; backend already returns minutes');process.exit(1)}
const client=fs.readFileSync(path.join(src,'api','client.js'),'utf8')
if(!client.includes('getFloodZones')){console.error('Flood-zone polygon API client is missing');process.exit(1)}
if(!client.includes('sampleAnalysisRaster')){console.error('Raster sampling API client is missing');process.exit(1)}
if(!mapView.includes('hydroshield-dam-pin')){console.error('Visible dam marker styling is missing');process.exit(1)}
if(!mapView.includes('onEachFeature')){console.error('Flood polygon hover detail wiring is missing');process.exit(1)}
if(!mapPanel.includes('Map opacity')){console.error('Result overlay opacity control is missing');process.exit(1)}

const propagation=fs.readFileSync(path.join(src,'components','FloodPropagation.jsx'),'utf8')
if(!propagation.includes('getSimulationTimeline')){console.error('Flood propagation timeline API is missing');process.exit(1)}
if(!propagation.includes('aria-label="Flood propagation timeline"')){console.error('Flood propagation timeline control is missing');process.exit(1)}
if(!dashboard.includes('studyDataReady={autoReady}')){console.error('Study-data-ready map wiring is missing');process.exit(1)}
if(!mapPanel.includes('studyDataReady = false')){console.error('Map panel study readiness prop is missing');process.exit(1)}
if(!mapView.includes('timelineFrame = null')){console.error('Timeline map overlay wiring is missing');process.exit(1)}

console.log(JSON.stringify({map_layers:'implemented',dem_preview:'wired',satellite_observed_extent:'wired',flood_timeline:'wired'},null,2))

const impact = fs.readFileSync(path.join(src,'components','ImpactPanel.jsx'),'utf8')
for(const token of ['Settlements','Roads','Bridges','Critical infra','exposedAreaKm2','Exposure metrics']){
  if(!impact.includes(token)){console.error(`Impact/risk presentation contract missing: ${token}`);process.exit(1)}
}
if(!source.includes('createComparisonDemo')){console.error('Prototype comparison API wiring is missing');process.exit(1)}
if(!source.includes('Prepare comparison run')){console.error('Prototype scenario comparison UI is missing');process.exit(1)}
for(const token of ['Flood extent GeoJSON','Flood extent SHP','Flood extent KML','flood_mask','velocity','arrival_time','water_level','Complete analysis package'])if(!source.includes(token)){console.error(`Export contract missing: ${token}`);process.exit(1)}
if(!client.includes('getAnalysisPreview')){console.error('Analysis export preview API client is missing');process.exit(1)}
if(!source.includes('getAnalysisPreview')){console.error('Analysis export preview UI is missing');process.exit(1)}
