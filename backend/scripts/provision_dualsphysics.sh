#!/bin/sh
set -eu

BIN_DIR="${HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR:-/opt/dualsphysics/bin}"
BASE_URL="${HYDROSHIELD_DUALSPHYSICS_SOURCE_BASE:-https://dual.sphysics.org/sphcourse/DualSPHysics-bin/dualsphysics/bin}"
ARCHIVE_URL="${HYDROSHIELD_DUALSPHYSICS_ARCHIVE_URL:-https://dual.sphysics.org/sphcourse/DualSPHysics-bin/dualsphysics.tar.gz}"
VERSION="5.4.3"

REQUIRED_FILES="GenCase_linux64 DualSPHysics5.4_linux64 PartVTK_linux64 libChronoEngine.so libdsphchrono.so VERSION_INFO.txt"
AUTO_BUILD_CPU="${HYDROSHIELD_AUTO_BUILD_DUALSPHYSICS_CPU:-true}"
RETRY_COUNT="${HYDROSHIELD_DUALSPHYSICS_RETRY_COUNT:-5}"
RETRY_DELAY="${HYDROSHIELD_DUALSPHYSICS_RETRY_DELAY:-2}"

mkdir -p "$BIN_DIR"

all_present=1
for file in $REQUIRED_FILES; do
  if [ ! -s "$BIN_DIR/$file" ]; then
    all_present=0
    break
  fi
done
if [ "$all_present" -eq 1 ]; then
  echo "DualSPHysics $VERSION required runtime already provisioned in $BIN_DIR"
  if [ -x "$BIN_DIR/DualSPHysics5.4CPU_linux64" ] || [ "$AUTO_BUILD_CPU" != "true" ]; then
    exit 0
  fi
fi

command -v curl >/dev/null 2>&1 || { echo "curl is required to provision DualSPHysics" >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo "tar is required to provision DualSPHysics" >&2; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT INT TERM

build_cpu_from_source() {
  if [ "$AUTO_BUILD_CPU" != "true" ]; then
    return 0
  fi
  if [ -x "$BIN_DIR/DualSPHysics5.4CPU_linux64" ]; then
    return 0
  fi
  if [ -z "${FOUND_PACKAGE_ROOT:-}" ]; then
    echo "DualSPHysics CPU fallback source is unavailable because the full package was not extracted." >&2
    return 0
  fi
  source_dir="$FOUND_PACKAGE_ROOT/src/source"
  makefile="$source_dir/Makefile_cpu"
  if [ ! -f "$makefile" ]; then
    echo "DualSPHysics CPU fallback source Makefile_cpu not found; CPU fallback remains unavailable." >&2
    return 0
  fi
  if ! command -v make >/dev/null 2>&1 || ! command -v g++ >/dev/null 2>&1; then
    echo "Build tools (make/g++) are unavailable; CPU fallback remains unavailable." >&2
    return 0
  fi
  echo "Building DualSPHysics CPU fallback from the bundled v5.4 source"
  if (
    cd "$source_dir" \
    && make -f Makefile_cpu COMPILE_CHRONO=NO COMPILE_WAVEGEN=NO COMPILE_MOORDYNPLUS=NO
  ); then
    built="$FOUND_PACKAGE_ROOT/bin/linux/DualSPHysics5.4CPU_linux64"
    if [ -x "$built" ]; then
      cp -f "$built" "$BIN_DIR/DualSPHysics5.4CPU_linux64"
      chmod 0755 "$BIN_DIR/DualSPHysics5.4CPU_linux64"
      echo "DualSPHysics CPU fallback built successfully"
      return 0
    fi
  fi
  echo "Could not build the DualSPHysics CPU fallback; GPU runtime remains available when an NVIDIA GPU is visible." >&2
}

# Prefer the official v5.4.3 public binary directory. The official download page
# identifies v5.4.3 as the current 5.4 package, and the public binary index exposes
# the Linux GenCase, GPU solver, PartVTK and supporting libraries individually.
# This is more robust than depending on an archive's top-level directory name.
echo "Downloading DualSPHysics $VERSION Linux runtime"
DIRECT_FILES="GenCase_linux64 DualSPHysics5.4_linux64 PartVTK_linux64 libChronoEngine.so libdsphchrono.so VERSION_INFO.txt"
DOWNLOAD_OK=1
for file in $DIRECT_FILES; do
  if [ -s "$BIN_DIR/$file" ]; then
    continue
  fi
  echo "Downloading DualSPHysics $VERSION: $file"
  if ! curl -fsSL --retry "$RETRY_COUNT" --retry-all-errors --retry-delay "$RETRY_DELAY" --connect-timeout 20 --max-time 900 \
      "$BASE_URL/$file" -o "$tmp/$file"; then
    DOWNLOAD_OK=0
    break
  fi
  [ -s "$tmp/$file" ] || { echo "Downloaded file is empty: $file" >&2; DOWNLOAD_OK=0; break; }
  cp -f "$tmp/$file" "$BIN_DIR/$file"
done

if [ "$DOWNLOAD_OK" -ne 1 ]; then
  echo "Individual DualSPHysics binary download failed; attempting the official package archive." >&2
  if ! curl -fsSL --retry "$RETRY_COUNT" --retry-all-errors --retry-delay "$RETRY_DELAY" --connect-timeout 20 --max-time 1800 \
      "$ARCHIVE_URL" -o "$tmp/dualsphysics.tar.gz"; then
    echo "Could not download the official DualSPHysics package archive." >&2
    exit 1
  fi

  mkdir -p "$tmp/extracted"
  tar -xzf "$tmp/dualsphysics.tar.gz" -C "$tmp/extracted"

  found_root=""
  while IFS= read -r candidate; do
    if [ -f "$candidate/GenCase_linux64" ] \
      && [ -f "$candidate/DualSPHysics5.4_linux64" ] \
      && [ -f "$candidate/PartVTK_linux64" ]; then
      found_root="$candidate"
      break
    fi
  done <<EOF
$(find "$tmp/extracted" -type d -path '*/bin/linux' 2>/dev/null)
EOF

  if [ -z "$found_root" ]; then
    while IFS= read -r candidate; do
      if [ -f "$candidate/GenCase_linux64" ] \
        && [ -f "$candidate/DualSPHysics5.4_linux64" ] \
        && [ -f "$candidate/PartVTK_linux64" ]; then
        found_root="$candidate"
        break
      fi
    done <<EOF
$(find "$tmp/extracted" -type f -name GenCase_linux64 -printf '%h\n' 2>/dev/null)
EOF
  fi

  if [ -z "$found_root" ]; then
    echo "Could not locate the required Linux binaries in the official package archive." >&2
    exit 1
  fi

  for file in $DIRECT_FILES; do
    if [ -f "$found_root/$file" ]; then
      cp -f "$found_root/$file" "$BIN_DIR/$file"
    else
      echo "Official DualSPHysics archive is missing required file: $file" >&2
      exit 1
    fi
  done

  # Preserve the root for an optional CPU source build when the archive contains source.
  case "$found_root" in
    */bin/linux) FOUND_PACKAGE_ROOT="$(dirname "$(dirname "$found_root")")" ;;
    */bin) FOUND_PACKAGE_ROOT="$(dirname "$found_root")" ;;
    *) FOUND_PACKAGE_ROOT="$found_root" ;;
  esac
fi

# The public v5.4.3 Linux binary index currently exposes the GPU solver, but not a
# CPU solver. CPU is therefore optional; GPU-capable hosts can still run normally.
if [ -f "$BIN_DIR/DualSPHysics5.4CPU_linux64" ]; then
  chmod 0755 "$BIN_DIR/DualSPHysics5.4CPU_linux64"
else
  build_cpu_from_source
fi

chmod 0755 "$BIN_DIR/GenCase_linux64" \
           "$BIN_DIR/DualSPHysics5.4_linux64" \
           "$BIN_DIR/PartVTK_linux64"
if [ -f "$BIN_DIR/DualSPHysics5.4CPU_linux64" ]; then
  chmod 0755 "$BIN_DIR/DualSPHysics5.4CPU_linux64"
fi
chmod 0644 "$BIN_DIR/libChronoEngine.so" "$BIN_DIR/libdsphchrono.so" "$BIN_DIR/VERSION_INFO.txt"

# Verify the required executable files are present and usable before reporting success.
for file in GenCase_linux64 DualSPHysics5.4_linux64 PartVTK_linux64; do
  [ -x "$BIN_DIR/$file" ] || { echo "Provisioning verification failed: $file is not executable" >&2; exit 1; }
done
if [ -e "$BIN_DIR/DualSPHysics5.4CPU_linux64" ] && [ ! -x "$BIN_DIR/DualSPHysics5.4CPU_linux64" ]; then
  echo "Provisioning verification failed: DualSPHysics5.4CPU_linux64 exists but is not executable" >&2
  exit 1
fi

# Check that the published version manifest identifies the expected v5.4.3 package lineage.
grep -Eq 'GenCase[[:space:]]+v5\.4\.' "$BIN_DIR/VERSION_INFO.txt" || {
  echo "Provisioning verification failed: VERSION_INFO.txt is not a v5.4 package" >&2
  exit 1
}

echo "Provisioned DualSPHysics $VERSION in $BIN_DIR"
