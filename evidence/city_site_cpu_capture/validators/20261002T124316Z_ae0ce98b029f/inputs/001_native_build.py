"""Isolated native component builds. Does not load any Civilization V module."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

from collect_baseline import digest, pe_header


def run(command, *, cwd: Path, env=None, timeout=60):
    return subprocess.run([str(item) for item in command], cwd=cwd, env=env, capture_output=True,
                          timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)


def checked_run(command, *, cwd: Path, env=None, timeout=60):
    result = run(command, cwd=cwd, env=env, timeout=timeout)
    if result.returncode:
        output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
        raise RuntimeError(f"Command failed ({result.returncode}): {command[0]}\n{output[:7000]}")
    return result


def environment_for(vs: Path, architecture: str, directory: Path) -> tuple[dict, str]:
    if architecture not in {"x86", "x64"}:
        raise ValueError("Unsupported architecture")
    directory.mkdir(parents=True, exist_ok=True)
    vcvars = vs / "VC/Auxiliary/Build" / ("vcvars32.bat" if architecture == "x86" else "vcvars64.bat")
    if not vcvars.is_file():
        raise RuntimeError(f"Build environment missing: {vcvars}")
    setup = directory / "read_build_environment.cmd"
    setup.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\nset\n', encoding="utf-8")
    env = {key.upper(): value for key, value in os.environ.items()}
    initialized = checked_run(["cmd.exe", "/d", "/c", setup], cwd=directory, env=env)
    paths = []
    for line in initialized.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            env[key.upper()] = value
            if key.upper() == "PATH":
                paths.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for value in paths for part in value.split(";")))
    compiler = shutil.which("cl.exe", path=env.get("PATH"))
    if compiler is None:
        raise RuntimeError("Compiler missing from initialized environment")
    # Never write or print this environment; unrelated variables can contain secrets.
    return env, compiler


def build_program(*, name: str, architecture: str, vs: Path, directory: Path,
                  evidence: Path, source: Path, includes=(), defines=(), objects=(), extra_link=(), runtime="/MT") -> dict:
    if runtime not in {"/MT", "/MD"}:
        raise ValueError("Unsupported CRT runtime")
    environment, compiler = environment_for(vs, architecture, directory)
    evidence.mkdir(parents=True, exist_ok=True)
    executable = directory / f"{name}.exe"
    flags = ["/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/O2", "/fp:strict", runtime]
    flags += [f"/D{value}" for value in defines]
    flags += [f'/I"{path}"' for path in includes]
    flags += [f'"{source}"', f'/Fo"{directory / (name + ".obj")}"', f'/Fe"{executable}"']
    flags += [f'"{path}"' for path in objects]
    link_flags = ["/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF",
                  f"/MACHINE:{architecture.upper()}", f"/MAP:{directory / (name + '.map')}", *extra_link]
    response = directory / "compile.rsp"
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    result = run([compiler, f"@{response}", "/link", *link_flags], cwd=directory, env=environment, timeout=180)
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    log = evidence / f"compile_{name}_{architecture}.txt"
    log.write_text(output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+", output, re.I):
        raise RuntimeError(f"Native build failed or emitted warnings; see {log}\n{output[:6000]}")
    pe = pe_header(executable)
    if pe["architecture"] != architecture:
        raise RuntimeError(f"Wrong native architecture: {pe}")
    return {"path": str(executable), "sha256": digest(executable), "pe": pe,
            "compiler": compiler, "compiler_sha256": digest(Path(compiler)),
            "flags": flags + ["/link"] + list(link_flags), "log": str(log),
            "log_sha256": digest(log), "compiler_and_linker_warnings": 0,
            "map": str(directory / (name + ".map"))}
