$ErrorActionPreference = "Stop"
$base = @("docker", "compose", "-f", "docker-compose.yml")
$gpu = $false
try {
  docker info | Out-Null
  nvidia-smi | Out-Null
  $gpu = $true
} catch { $gpu = $false }
if ($gpu) {
  Write-Host "Starting HydroShield with NVIDIA GPU support..."
  docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
} else {
  Write-Host "GPU not detected - starting HydroShield in CPU mode."
  Write-Host "restarting HydroShield in CPU mode"
  $env:HYDROSHIELD_DUAL_SPH_DEVICE = "cpu"
  docker compose -f docker-compose.yml up --build
}
