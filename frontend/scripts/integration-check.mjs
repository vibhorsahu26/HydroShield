import fs from 'node:fs'
import path from 'node:path'

const baseUrl = (process.env.HYDROSHIELD_API_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '')
const frontendRoot = path.resolve(new URL('..', import.meta.url).pathname)
const assert = (condition, message) => { if (!condition) throw new Error(message) }
async function json(url) { const res = await fetch(url); const type=res.headers.get('content-type')||''; const body=type.includes('json')?await res.json():await res.text(); return {res,body} }
const health=await json(`${baseUrl}/health`); assert(health.res.ok && health.body?.status==='ok', `Backend health failed: ${health.res.status}`)
const origin=baseUrl.replace(/\/api\/v1$/,''); const openapi=await json(`${origin}/openapi.json`)
const requiredPaths=['/projects','/acquisition/search','/acquisition/projects/{project_id}/run','/acquisition/projects/{project_id}/runs','/projects/{project_id}/datasets/upload','/projects/{project_id}/datasets/{dataset_id}/preview','/projects/{project_id}/model-inputs','/geospatial/preprocess','/projects/{project_id}/scenarios','/projects/{project_id}/scenarios/{scenario_id}/variants/generate','/simulations','/simulations/{job_id}','/results/simulations/{job_id}/analysis-inputs','/results/simulations/{job_id}/analyze','/results/simulations/{job_id}/process-native','/results/compare','/results/comparison-demo','/satellite/validate','/exports/analysis/{result_id}','/exports/analysis/{result_id}/preview','/exports/analysis/{result_id}/flood-zones','/results/simulations/{job_id}/timeline','/results/simulations/{job_id}/timeline/image']
if(openapi.res.ok){for(const route of requiredPaths) assert(`${baseUrl.replace(origin,'')}${route}` in openapi.body.paths,`Missing backend route: ${route}`)} else {const ready=await json(`${baseUrl}/health/ready`);assert(ready.res.ok,`Backend readiness failed while OpenAPI is disabled: ${ready.res.status}`)}
const sourceFiles=[];function walk(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){if(['node_modules','dist'].includes(entry.name))continue;const full=path.join(dir,entry.name);if(entry.isDirectory())walk(full);else if(full.endsWith('.jsx')||full.endsWith('.js'))sourceFiles.push(full)}}walk(path.join(frontendRoot,'src'));const source=sourceFiles.map((file)=>fs.readFileSync(file,'utf8')).join('\n')
for(const token of ['createSimulation','uploadDataset','searchDams','runAutomaticAcquisition','getDatasetPreview','analyzeSimulation','processNativeResult','validateSatellite','downloadExport'])assert(source.includes(token),`Frontend integration token missing: ${token}`)
assert(!source.includes("floodArea: (42.6"),'Fabricated dashboard statistics remain')
assert(!source.includes("Simulation complete.'"),'Fake simulation completion timer remains')
for(const relative of ['Dockerfile','vercel.json','nginx.conf','.env.example'])assert(fs.existsSync(path.join(frontendRoot,relative)),`Missing deployment file: ${relative}`)
console.log(JSON.stringify({status:'ok',backend:baseUrl,required_routes:requiredPaths.length,source_files_checked:sourceFiles.length},null,2))
