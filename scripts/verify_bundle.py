"""校验 PyInstaller 产物完整性（release workflow 构建后执行）。

用法：python scripts/verify_bundle.py [dist/HainTag]

检查项：
- HainTag.exe 存在
- danbooru_all_2.csv 在 app 根或 _internal/（PyInstaller 6 datas 落点）
- PIL / numpy 以目录形式在 _internal/（带二进制扩展的包）
- huggingface_hub 在 exe 内嵌的 PYZ 归档里（纯 Python 包不落目录）
- onnxruntime 不在包里（spec 自 0.9.2 因 DLL 冲突排除，推理走托管子进程）
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def pyz_module_names(exe: Path) -> set[str]:
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

    pyz_data = CArchiveReader(str(exe)).extract("PYZ.pyz")
    tmp = Path(tempfile.gettempdir()) / "haintag_verify_pyz.pyz"
    tmp.write_bytes(pyz_data)
    return set(ZlibArchiveReader(str(tmp)).toc.keys())


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist/HainTag")
    exe = dist / "HainTag.exe"
    internal = dist / "_internal"

    if not exe.is_file():
        fail(f"{exe} missing")

    if not ((dist / "danbooru_all_2.csv").is_file()
            or (internal / "danbooru_all_2.csv").is_file()):
        fail("danbooru_all_2.csv missing from bundle")

    for pkg in ("PIL", "numpy"):
        if not (internal / pkg).is_dir():
            fail(f"{pkg} directory missing from _internal")

    modules = pyz_module_names(exe)
    if "huggingface_hub" not in modules:
        fail("huggingface_hub missing from PYZ archive")

    if "onnxruntime" in modules or (internal / "onnxruntime").is_dir():
        fail("onnxruntime must stay excluded (DLL conflict; inference uses the managed subprocess)")

    print(f"bundle ok: exe + csv + PIL/numpy dirs + huggingface_hub in PYZ "
          f"({len(modules)} modules), onnxruntime excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
