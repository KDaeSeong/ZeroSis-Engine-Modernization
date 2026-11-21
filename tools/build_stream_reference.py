"""Build/run SDK memory-stream reference only; no game or GameCore load."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import run, checked_run

MODES = ("memory", "scalar0", "scalar1", "scalar2", "bulk1", "bulk2", "shortread", "pastskip", "pastseek", "fixedoverflow", "zero")

def build_reference():
    sdk = PROJECT / "Source/SDK_BNW_Original"
    snapshot = json.loads((PROJECT / "evidence/sdk_reference/snapshot_manifest.json").read_text(encoding="utf-8"))
    for row in snapshot:
        if Path(row["snapshot"]).is_relative_to(sdk / "FirePlace"):
            if digest(Path(row["snapshot"])) != row["sha256"] or digest(Path(row["source"])) != row["sha256"]:
                raise RuntimeError("Original stream reference changed")
    vc = Path(r"C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC")
    winsdk = Path(r"C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A")
    directory = PROJECT / "Build/Streams_reference/x86"
    evidence = PROJECT / "evidence/streams/reference"
    directory.mkdir(parents=True, exist_ok=True); evidence.mkdir(parents=True, exist_ok=True)
    env = {k.upper(): v for k, v in os.environ.items()}
    env["INCLUDE"] = f"{vc/'include'};{winsdk/'Include'}"
    env["LIB"] = f"{vc/'lib'};{winsdk/'Lib'}"
    env["PATH"] = f"{vc/'bin'};{vc.parent/'Common7/IDE'};{winsdk/'bin'};{env.get('PATH','')}"
    compiler = vc / "bin/cl.exe"
    executable = directory / "stream_reference.exe"
    source = PROJECT / "Tests/sdk_stream_trace.cpp"
    host = PROJECT / "Tests/sdk_stream_reference_host.cpp"
    library = sdk / "FirePlace/lib/FireWorksWin32.lib"
    flags = ["/nologo", "/EHsc", "/W3", "/O2", "/MD", "/fp:strict", "/D_CRT_SECURE_NO_WARNINGS",
             "/D_SECURE_SCL=0", "/D_HAS_ITERATOR_DEBUGGING=0", "/DFINAL_RELEASE", "/DSTREAM_LEGACY_REFERENCE",
             f'/I"{sdk / "FirePlace/include"}"', f'/I"{PROJECT / "Source/Providers/Streams"}"',
             f'"{source}"', f'"{host}"', f'/Fo"{directory}\\\\"', f'/Fe"{executable}"', f'"{library}"']
    link = ["/LTCG", "/OPT:REF", "/OPT:ICF", "/INCREMENTAL:NO", "/MACHINE:X86", f"/MAP:{directory/'stream_reference.map'}",
            "kernel32.lib", "user32.lib", "advapi32.lib", "psapi.lib", "dbghelp.lib", "ole32.lib", "shell32.lib", "winmm.lib"]
    rsp = directory / "compile.rsp"; rsp.write_text("\n".join(flags), encoding="ascii")
    result = run([compiler, f"@{rsp}", "/link", *link], cwd=directory, env=env, timeout=120)
    log = evidence / "build.log"; log.write_bytes(result.stdout+result.stderr)
    if result.returncode: raise RuntimeError(read_text(log)[:7000])
    manifest = executable.with_suffix(".exe.manifest")
    if manifest.exists():
        checked_run([winsdk/'bin/mt.exe', '-nologo', '-manifest', manifest, f'-outputresource:{executable};1'], cwd=directory, env=env)
    mapfile = directory / "stream_reference.map"
    proof = [line.strip() for line in read_text(mapfile).splitlines()
             if ("FDataStream@@" in line or "FMemoryStream@@" in line) and "FireWorksWin32:" in line]
    if not any("?ReadIt@FMemoryStream@@" in line for line in proof): raise RuntimeError("Reference provider missing from map")
    traces = []
    for mode in MODES:
        try:
            result = run([executable, mode], cwd=directory, env=env, timeout=5)
        except subprocess.TimeoutExpired as error:
            trace = evidence / f"{mode}.txt"
            trace.write_bytes((error.stdout or b'')+(error.stderr or b''))
            raise RuntimeError(f"Reference timed out: {mode}; partial trace: {read_text(trace)}") from error
        trace = evidence / f"{mode}.txt"; trace.write_bytes(result.stdout+result.stderr)
        traces.append({"mode":mode, "returncode":result.returncode, "path":str(trace), "sha256":digest(trace)})
    report = {"status":"REFERENCE_OBSERVATIONS_ONLY", "path":str(executable), "sha256":digest(executable),
        "pe":pe_header(executable), "library":{"path":str(library),"sha256":digest(library)},
        "source":{"path":str(source),"sha256":digest(source)}, "map":{"path":str(mapfile),"sha256":digest(mapfile)},
        "host_adapter":{"path":str(host),"sha256":digest(host),"scope":"Only fixed empty-string storage exports required at archive startup"},
        "compiler":{"path":str(compiler),"sha256":digest(compiler)},
        "warning_codes":re.findall(r'\bwarning\s+([A-Z]+\d+)',read_text(log)),
        "map_proof":proof, "log":{"path":str(log),"sha256":digest(log)}, "traces":traces,
        "flags":flags+["/link"]+link, "game_launched":False, "game_runtime_verified":False}
    (evidence/'build_result.json').write_text(json.dumps(report,indent=2)+"\n",encoding='utf-8')
    return report

if __name__ == '__main__':
    report = build_reference()
    print(json.dumps({"status":report['status'], "traces":[(r['mode'],r['returncode']) for r in report['traces']]}))
