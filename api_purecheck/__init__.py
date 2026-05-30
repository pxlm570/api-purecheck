from __future__ import annotations

from pathlib import Path


_SRC_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "api_purecheck"

if _SRC_PACKAGE.is_dir():
    __path__.append(str(_SRC_PACKAGE))
    _src_init = _SRC_PACKAGE / "__init__.py"
    exec(compile(_src_init.read_text(encoding="utf-8"), str(_src_init), "exec"), globals())
else:
    __version__ = "0.0.0"
