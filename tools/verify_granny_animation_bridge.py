#!/usr/bin/env python3
"""Build and exercise the bounded native x64 C ABI Granny curve bridge."""
from __future__ import annotations
import hashlib, json, os, pathlib, shutil, subprocess, sys, time
import ctypes
import re

P=pathlib.Path(__file__).resolve().parents[1]
SDK=pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\Nexus\x86")
EXPORT=P/"Build/StockUnitExports/20261005T072135Z"
VS=pathlib.Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat")
CL=pathlib.Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\HostX64\x64\cl.exe")
LIB=CL.with_name("lib.exe"); DUMPBIN=CL.with_name("dumpbin.exe")
ASSEMBLIES=("Firaxis.Framework.dll","Firaxis.Framework.Granny.dll","Firaxis.Framework.FirePlace.dll","Firaxis.Framework.Granny.Implx64.dll")
INPUTS=[P/"Source/Animation/GrannyAnimationBridge.h",P/"Source/Animation/GrannyAnimationBridge.cpp",P/"Tests/granny_animation_bridge.cpp",
        P/"tools/GrannyAnimationProbe.cs",P/"tools/probe_granny_animation_x64.py",P/"tools/verify_granny_animation_bridge.py",
        EXPORT/"unitmodels_stringdatabase.gsd",EXPORT/"Warrior_V2.gr2",EXPORT/"Warrior_IdleA.gr2",
        EXPORT/"ART_DEF_UNIT_MEMBER_WARRIOR_V2.json"]+[SDK/a for a in ASSEMBLIES]

def sha(p:pathlib.Path)->str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()
def run(args,cwd,timeout=60,env=None):
    return subprocess.run(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          timeout=timeout,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0),check=False)
def env_from_vcvars()->dict:
    short=ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetShortPathNameW(str(VS),short,len(short))
    if not short.value:raise RuntimeError("cannot resolve short vcvars path")
    r=run(["cmd.exe","/d","/c",f"call {short.value} >nul && set"],P,30)
    if r.returncode:raise RuntimeError("vcvars64 environment setup failed: "+r.stderr.decode(errors="replace")[-2000:])
    env=os.environ.copy()
    for line in r.stdout.decode(errors="replace").splitlines():
        if "=" in line:
            k,v=line.split("=",1);env[k]=v
    return env
def main()->int:
    if not CL.is_file() or not VS.is_file():raise RuntimeError("x64 MSVC compiler environment is unavailable")
    for p in INPUTS:
        if not p.is_file():raise RuntimeError("required immutable input missing: "+str(p))
    before={str(p):sha(p) for p in INPUTS}
    stamp=os.environ.get("ZS_BRIDGE_RUN_ID") or time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
    if not re.fullmatch(r"\d{8}T\d{6}Z",stamp):raise RuntimeError("run ID must be UTC YYYYMMDDTHHMMSSZ")
    build=P/"Build/GrannyAnimationBridge"/stamp; evidence=P/"evidence/granny_animation_bridge"/stamp
    build.mkdir(parents=True,exist_ok=False);evidence.mkdir(parents=True,exist_ok=False)
    frozen=evidence/"frozen_inputs";frozen.mkdir()
    frozen_sources=[]
    for p in (INPUTS[0],INPUTS[1],INPUTS[2],INPUTS[5]):
        dst=frozen/p.name;shutil.copy2(p,dst);frozen_sources.append({"source":str(p),"copy":str(dst),"sha256":sha(dst)})
    for name in ASSEMBLIES:shutil.copy2(SDK/name,build/name)
    copied={name:sha(build/name) for name in ASSEMBLIES}
    if any(copied[n]!=before[str(SDK/n)] for n in ASSEMBLIES):raise RuntimeError("private SDK assembly hash mismatch")
    env=env_from_vcvars(); src=P/"Source/Animation/GrannyAnimationBridge.cpp"; header=P/"Source/Animation/GrannyAnimationBridge.h"
    # This VS install lacks the x64 mscoree import library required by /clr.
    # Derive a private x64 import lib from the installed x64 runtime's exports.
    exports=run([str(DUMPBIN),"/nologo","/exports",r"C:\Windows\System32\mscoree.dll"],build,30,env)
    symbols=[]
    for line in exports.stdout.decode(errors="replace").splitlines():
        m=re.match(r"\s*\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(\S+)\s*$",line)
        if m and m.group(1) in ("_CorDllMain","_CorExeMain","_CorExeMain2"):symbols.append(m.group(1))
    if exports.returncode or "_CorDllMain" not in symbols:raise RuntimeError("cannot inspect x64 mscoree exports")
    deffile=build/"mscoree_x64.def";deffile.write_text("LIBRARY mscoree.dll\nEXPORTS\n"+"".join("  "+s+"\n" for s in symbols),encoding="ascii")
    ilib=run([str(LIB),"/nologo","/machine:x64",f"/def:{deffile}",f"/out:{build/'mscoree_x64.lib'}"],build,30,env)
    (evidence/"mscoree_importlib.stdout.txt").write_bytes(ilib.stdout);(evidence/"mscoree_importlib.stderr.txt").write_bytes(ilib.stderr)
    libcheck=run([str(DUMPBIN),"/nologo","/linkermember:2",str(build/"mscoree_x64.lib")],build,30,env)
    if not (build/"mscoree_x64.lib").is_file() or b"_CorDllMain" not in libcheck.stdout:
        raise RuntimeError("private x64 mscoree import library generation failed")
    bridge=build/"ZeroSisGrannyAnimationBridge.dll"; test=build/"GrannyAnimationBridgeTest.exe"
    cmd=[str(CL),"/nologo","/LD","/clr","/MD","/EHa","/O2","/W4","/WX","/wd4691",f"/I{header.parent}",
         f"/AI{build}","/AI",r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319",
         "/FU",r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Core.dll",
         f"/FU{build/'Firaxis.Framework.dll'}",f"/FU{build/'Firaxis.Framework.Granny.dll'}",
         str(src),f"/link",f"/OUT:{bridge}",f"/IMPLIB:{build/'ZeroSisGrannyAnimationBridge.lib'}","/NODEFAULTLIB:MSCOREE",str(build/"mscoree_x64.lib")]
    c=run(cmd,build,120,env); (evidence/"bridge_build.stdout.txt").write_bytes(c.stdout);(evidence/"bridge_build.stderr.txt").write_bytes(c.stderr)
    if c.returncode:raise RuntimeError("mixed-mode bridge compile failed (see evidence build log): "+c.stderr.decode(errors="replace")[-3000:])
    c=run([str(CL),"/nologo","/EHsc","/std:c++17","/W4","/WX",f"/I{header.parent}",str(P/"Tests/granny_animation_bridge.cpp"),"/link","/OUT:"+str(test)],build,120,env)
    (evidence/"native_test_build.stdout.txt").write_bytes(c.stdout);(evidence/"native_test_build.stderr.txt").write_bytes(c.stderr)
    if c.returncode:raise RuntimeError("native test compile failed: "+c.stderr.decode(errors="replace")[-3000:])
    binaries=[]
    for binary in (bridge,test):
        headers=run([str(DUMPBIN),"/nologo","/headers",str(binary)],build,30,env)
        dependents=run([str(DUMPBIN),"/nologo","/dependents",str(binary)],build,30,env)
        ht=headers.stdout.decode(errors="replace");dt=dependents.stdout.decode(errors="replace")
        if headers.returncode or "8664 machine (x64)" not in ht:raise RuntimeError("built bridge/test is not verified AMD64: "+str(binary))
        binaries.append({"path":str(binary),"architecture":"x64","dependents_text":dt})
        (evidence/(binary.stem+"_dependents.txt")).write_bytes(dependents.stdout)
    raw=json.loads((EXPORT/"ART_DEF_UNIT_MEMBER_WARRIOR_V2.json").read_text(encoding="utf-8"))
    tsv=build/"t0-reference.tsv"
    with tsv.open("w",encoding="ascii",newline="\n") as f:
        for track in raw["pose"]["sampled_tracks"]:
            vals=[track["name"],raw["pose"]["duration"],*track["position"],*track["orientation"],*track["scale_shear"]]
            f.write(str(vals[0])+"\t"+" ".join(format(float(v),".9g") for v in vals[1:])+"\n")
    config=(b'<?xml version="1.0"?><configuration><startup useLegacyV2RuntimeActivationPolicy="true">'
            b'<supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0"/></startup></configuration>')
    config_path=pathlib.Path(str(test)+".config");config_path.write_bytes(config)
    args=[str(test),str(bridge),str(EXPORT/"unitmodels_stringdatabase.gsd"),str(EXPORT/"Warrior_V2.gr2"),str(EXPORT/"Warrior_IdleA.gr2"),str(tsv)]
    r=run(args,build,45,env);(evidence/"runtime.stdout.txt").write_bytes(r.stdout);(evidence/"runtime.stderr.txt").write_bytes(r.stderr)
    after={str(p):sha(p) for p in INPUTS}
    result={"schema":1,"run_id":stamp,"status":"PASS_NATIVE_GRANNY_C_ABI_X64" if r.returncode==0 else "FAILED_NATIVE_GRANNY_C_ABI_X64",
            "source_input_hashes_before":before,"source_input_hashes_after":after,"source_inputs_unchanged":before==after,
            "frozen_sources":frozen_sources,"compiler":str(CL),"compiler_sha256":sha(CL),"librarian_sha256":sha(LIB),"dumpbin_sha256":sha(DUMPBIN),
            "bridge_build_exit":0,"native_test_build_exit":0,"runtime_exit":r.returncode,
            "runtime_stdout":r.stdout.decode(errors="replace"),"private_sdk_assemblies":[{"name":n,"path":str(build/n),"sha256":copied[n]} for n in ASSEMBLIES],
            "clr":{"config_path":str(config_path),"config_sha256":sha(config_path),"startup":".NETFramework,Version=v4.0","useLegacyV2RuntimeActivationPolicy":True},
            "clr_runtime_file":{"path":r"C:\Windows\System32\mscoree.dll","sha256":sha(pathlib.Path(r"C:\Windows\System32\mscoree.dll"))},
            "framework_core":{"path":r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Core.dll","sha256":sha(pathlib.Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Core.dll"))},
            "mscoree_x64_import_library":{"path":str(build/"mscoree_x64.lib"),"sha256":sha(build/"mscoree_x64.lib"),"runtime_exports_source":r"C:\Windows\System32\mscoree.dll"},
            "bridge":{"path":str(bridge),"sha256":sha(bridge)},"native_test":{"path":str(test),"sha256":sha(test)},
            "pe_binaries":binaries,
            "reference":{"path":str(tsv),"sha256":sha(tsv),"source_json":str(EXPORT/"ART_DEF_UNIT_MEMBER_WARRIOR_V2.json"),"tracks":len(raw["pose"]["sampled_tracks"])},
            "scope":"public Granny curve sampling through x64 native C ABI; not full engine animation"}
    (evidence/"report.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"status":result["status"],"build":str(build),"evidence":str(evidence)},indent=2))
    return 0 if r.returncode==0 and before==after else 1
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as e:print("BRIDGE_VERIFY_FAILED: "+str(e),file=sys.stderr);raise
