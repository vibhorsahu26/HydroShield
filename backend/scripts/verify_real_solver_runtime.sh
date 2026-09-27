#!/bin/sh
set -eu

ROOT="${HYDROSHIELD_DUAL_SPH_BIN_DIR:-/opt/dualsphysics/bin}"
for tool in GenCase_linux64 DualSPHysics5.4_linux64 PartVTK_linux64; do
  path="$ROOT/$tool"
  test -x "$path" || { echo "Missing/non-executable: $path" >&2; exit 1; }
  echo "Found: $path"
  if command -v ldd >/dev/null 2>&1; then
    if ldd "$path" 2>/dev/null | grep -q 'not found'; then
      echo "Unresolved shared library dependency in $path" >&2
      ldd "$path" >&2 || true
      exit 1
    fi
  fi
done
if [ -x "$ROOT/DualSPHysics5.4CPU_linux64" ]; then
  echo "Found optional CPU fallback: $ROOT/DualSPHysics5.4CPU_linux64"
else
  echo "CPU fallback binary not installed; GPU-capable deployments remain supported." >&2
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi -L || true
fi

echo "DualSPHysics runtime smoke check: required runtime files are OK"
