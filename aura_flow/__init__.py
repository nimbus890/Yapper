"""yapper_ core package."""

import os
from pathlib import Path
import sys

# CTranslate2 loads CUDA math libraries lazily on the first transcription.
# PyTorch ships the matching CUDA 12 DLLs, but Windows does not search
# ``torch/lib`` automatically for another extension module. Keep the directory
# handles alive for the process and also update PATH for child/native loaders.
_dll_directories: list[object] = []
if sys.platform == "win32":
    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    candidates = [site_packages / "torch" / "lib"]
    candidates.extend(site_packages.glob("nvidia/*/bin"))
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        value = str(candidate.resolve())
        if hasattr(os, "add_dll_directory"):
            try:
                _dll_directories.append(os.add_dll_directory(value))
            except OSError:
                pass
        path_parts = os.environ.get("PATH", "").split(os.pathsep)
        if value.lower() not in {part.lower() for part in path_parts if part}:
            os.environ["PATH"] = value + os.pathsep + os.environ.get("PATH", "")


from .version import VERSION as __version__
