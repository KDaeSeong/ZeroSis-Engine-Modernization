"""Build a CRC-only entry harness with original v90-compatible SDK library code."""
from __future__ import annotations

import os
from pathlib import Path
import re

from collect_baseline import PROJECT, digest, pe_header
from native_build import run, checked_run


def build_reference(sdk: Path, evidence: Path) -> dict:
    vc = Path(r"C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC")
    windows_sdk = Path(r"C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A")
    directory = PROJECT / "Build/CRC/x86"
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / "crc_trace.exe"
    compiler = vc / "bin/cl.exe"
    source = PROJECT / "Tests/sdk_crc_reference.cpp"
    library = sdk / "FirePlace/lib/FireWorksWin32.lib"
    environment = {key.upper(): value for key, value in os.environ.items()}
    environment["INCLUDE"] = f"{vc / 'include'};{windows_sdk / 'Include'}"
    environment["LIB"] = f"{vc / 'lib'};{windows_sdk / 'Lib'}"
    environment["PATH"] = f"{vc / 'bin'};{vc.parent / 'Common7/IDE'};{windows_sdk / 'bin'};{environment.get('PATH', '')}"
    flags = ["/nologo", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/D_CRT_SECURE_NO_WARNINGS",
             f'/I"{sdk / "FirePlace/include/FireWorks"}"', f'"{source}"',
             f'/Fo"{directory / "sdk_crc_reference.obj"}"', f'/Fe"{executable}"', f'"{library}"']
    response = directory / "compile_legacy.rsp"
    response.write_text("\n".join(flags) + "\n", encoding="ascii")
    link_flags = ["/LTCG", "/OPT:REF", "/OPT:ICF", "/INCREMENTAL:NO", "/MACHINE:X86", "/WX",
                  f"/MAP:{directory / 'crc_trace.map'}", "kernel32.lib", "user32.lib", "advapi32.lib",
                  "psapi.lib", "dbghelp.lib", "ole32.lib", "shell32.lib", "winmm.lib"]
    result = run([compiler, f"@{response}", "/link", *link_flags], cwd=directory, env=environment, timeout=120)
    log = evidence / "compile_crc_trace_x86_v90.txt"
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    log.write_text(output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+", output, re.I):
        raise RuntimeError(f"Legacy CRC reference failed: {log}\n{output[:6000]}")
    manifest = executable.with_suffix(".exe.manifest")
    if manifest.is_file():
        checked_run([windows_sdk / "bin/mt.exe", "-nologo", f"-manifest", manifest,
                     f"-outputresource:{executable};1"], cwd=directory, env=environment)
    return {"path": str(executable), "sha256": digest(executable), "pe": pe_header(executable),
            "compiler": str(compiler), "compiler_sha256": digest(compiler),
            "flags": flags + ["/link"] + link_flags, "log": str(log), "log_sha256": digest(log),
            "compiler_and_linker_warnings": 0, "map": str(directory / "crc_trace.map")}
