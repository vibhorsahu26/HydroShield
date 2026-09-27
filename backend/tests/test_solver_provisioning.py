from __future__ import annotations

import http.server
import os
from pathlib import Path
import socketserver
import subprocess
import tarfile
import threading


REQUIRED_FILES = (
    "GenCase_linux64",
    "DualSPHysics5.4_linux64",
    "PartVTK_linux64",
    "libChronoEngine.so",
    "libdsphchrono.so",
    "VERSION_INFO.txt",
)
OPTIONAL_CPU = "DualSPHysics5.4CPU_linux64"


def _make_executable(path: Path, label: str) -> None:
    path.write_text(f"#!/bin/sh\necho fixture:{label}\n", encoding="utf-8")
    path.chmod(0o755)


def test_provision_script_extracts_official_package_archive(tmp_path):
    source_root = tmp_path / "source"
    archive_root = source_root / "dualsphysics" / "bin"
    dest = tmp_path / "dest"
    archive_root.mkdir(parents=True)

    for name in REQUIRED_FILES:
        target = archive_root / name
        if name == "VERSION_INFO.txt":
            target.write_text("GenCase                   v5.4.354.01         07-04-2025\nPartVTK                   v5.4.266.01         09-04-2025\n", encoding="utf-8")
        elif name.endswith(".so"):
            target.write_bytes(b"fixture shared library")
        else:
            _make_executable(target, name)

    archive = source_root / "dualsphysics.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(source_root / "dualsphysics", arcname="dualsphysics")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):  # pragma: no cover
            return

    handler = lambda *args, **kwargs: Handler(*args, directory=str(source_root), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ.copy()
        env.update({
            "HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR": str(dest),
            "HYDROSHIELD_DUALSPHYSICS_ARCHIVE_URL": f"http://127.0.0.1:{server.server_address[1]}/dualsphysics.tar.gz",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_COUNT": "1",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_DELAY": "0",
            "HYDROSHIELD_DUALSPHYSICS_SOURCE_BASE": f"http://127.0.0.1:{server.server_address[1]}/missing-direct",
        })
        subprocess.run(
            ["sh", "scripts/provision_dualsphysics.sh"],
            cwd=Path.cwd(), env=env, check=True, capture_output=True, text=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    for name in REQUIRED_FILES:
        assert (dest / name).is_file()
    for name in REQUIRED_FILES[:3]:
        assert os.access(dest / name, os.X_OK)
    assert not (dest / OPTIONAL_CPU).exists()


def test_provision_script_falls_back_to_individual_files_when_archive_is_unavailable(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    for name in REQUIRED_FILES:
        if name == "VERSION_INFO.txt":
            (source / name).write_text("GenCase                   v5.4.354.01\n", encoding="utf-8")
        elif name.endswith(".so"):
            (source / name).write_bytes(b"fixture shared library")
        else:
            _make_executable(source / name, name)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):  # pragma: no cover
            return

    handler = lambda *args, **kwargs: Handler(*args, directory=str(source), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ.copy()
        env.update({
            "HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR": str(dest),
            "HYDROSHIELD_DUALSPHYSICS_ARCHIVE_URL": f"http://127.0.0.1:{server.server_address[1]}/missing.tar.gz",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_COUNT": "1",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_DELAY": "0",
            "HYDROSHIELD_DUALSPHYSICS_SOURCE_BASE": f"http://127.0.0.1:{server.server_address[1]}",
        })
        subprocess.run(
            ["sh", "scripts/provision_dualsphysics.sh"],
            cwd=Path.cwd(), env=env, check=True, capture_output=True, text=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert all((dest / name).is_file() for name in REQUIRED_FILES)
    assert not (dest / OPTIONAL_CPU).exists()



def test_provision_script_builds_optional_cpu_fallback_from_source(tmp_path):
    source_root = tmp_path / "source"
    package_root = source_root / "dualsphysics"
    archive_root = package_root / "bin"
    source_dir = package_root / "src" / "source"
    dest = tmp_path / "dest"
    archive_root.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    (source_dir / "Makefile_cpu").write_text("all:\n", encoding="utf-8")

    for name in REQUIRED_FILES:
        target = archive_root / name
        if name == "VERSION_INFO.txt":
            target.write_text(
                "GenCase                   v5.4.354.01         07-04-2025\n"
                "PartVTK                   v5.4.266.01         09-04-2025\n",
                encoding="utf-8",
            )
        elif name.endswith(".so"):
            target.write_bytes(b"fixture shared library")
        else:
            _make_executable(target, name)

    archive = source_root / "dualsphysics.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(package_root, arcname="dualsphysics")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_make = fake_bin / "make"
    fake_make.write_text(
        "#!/bin/sh\n"
        "mkdir -p ../../bin/linux\n"
        "printf '#!/bin/sh\\necho fixture:cpu\\n' > ../../bin/linux/DualSPHysics5.4CPU_linux64\n"
        "chmod 755 ../../bin/linux/DualSPHysics5.4CPU_linux64\n",
        encoding="utf-8",
    )
    fake_make.chmod(0o755)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):  # pragma: no cover
            return

    handler = lambda *args, **kwargs: Handler(*args, directory=str(source_root), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ.copy()
        env.update({
            "HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR": str(dest),
            "HYDROSHIELD_DUALSPHYSICS_ARCHIVE_URL": f"http://127.0.0.1:{server.server_address[1]}/dualsphysics.tar.gz",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_COUNT": "1",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_DELAY": "0",
            "HYDROSHIELD_AUTO_BUILD_DUALSPHYSICS_CPU": "true",
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
        })
        subprocess.run(
            ["sh", "scripts/provision_dualsphysics.sh"],
            cwd=Path.cwd(), env=env, check=True, capture_output=True, text=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert (dest / OPTIONAL_CPU).is_file()
    assert os.access(dest / OPTIONAL_CPU, os.X_OK)


def test_provision_script_discovers_versioned_bin_linux_archive_layout(tmp_path):
    source_root = tmp_path / "source"
    package_root = source_root / "DualSPHysics_v5.4.3"
    archive_root = package_root / "bin" / "linux"
    dest = tmp_path / "dest"
    archive_root.mkdir(parents=True)

    for name in REQUIRED_FILES:
        target = archive_root / name
        if name == "VERSION_INFO.txt":
            target.write_text("GenCase                   v5.4.354.01\nPartVTK                   v5.4.266.01\n", encoding="utf-8")
        elif name.endswith(".so"):
            target.write_bytes(b"fixture shared library")
        else:
            _make_executable(target, name)

    archive = source_root / "dualsphysics.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(package_root, arcname="DualSPHysics_v5.4.3")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

    handler = lambda *args, **kwargs: Handler(*args, directory=str(source_root), **kwargs)
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        env = os.environ.copy()
        env.update({
            "HYDROSHIELD_DUAL_SPH_BIN_INSTALL_DIR": str(dest),
            "HYDROSHIELD_DUALSPHYSICS_ARCHIVE_URL": f"http://127.0.0.1:{server.server_address[1]}/dualsphysics.tar.gz",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_COUNT": "1",
            "HYDROSHIELD_DUALSPHYSICS_RETRY_DELAY": "0",
            "HYDROSHIELD_DUALSPHYSICS_SOURCE_BASE": f"http://127.0.0.1:{server.server_address[1]}/missing-direct",
            "HYDROSHIELD_AUTO_BUILD_DUALSPHYSICS_CPU": "false",
        })
        subprocess.run(
            ["sh", "scripts/provision_dualsphysics.sh"],
            cwd=Path.cwd(), env=env, check=True, capture_output=True, text=True,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert all((dest / name).is_file() for name in REQUIRED_FILES)

def test_provision_script_prefers_official_direct_binary_urls():
    script = Path("scripts/provision_dualsphysics.sh").read_text(encoding="utf-8")
    assert '"$BASE_URL/$file"' in script
    assert "Downloading DualSPHysics $VERSION Linux runtime" in script
    assert "DIRECT_FILES=" in script
    assert "Could not locate the required Linux binaries in the official package archive." in script
