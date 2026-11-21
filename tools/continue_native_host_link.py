"""Continue one terminal UUID-library link failure without recompiling its units."""
from __future__ import annotations
import argparse
import ctypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import relink_native_save_host as h
from native_build import environment_for

PRODUCER_SHA = "d71804ab30e4cd60f41c16e95dbf24b9f134666a0a9d63f56ee68510eaab3ee1"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failure",type=Path,required=True)
    args=parser.parse_args()
    p=h.PROJECT;stage=args.failure.parent;h.ordinary(args.failure,p/"evidence/native_save_archive/host_relink")
    failure_ref=h.artifact(args.failure);failure=h.document(args.failure)
    assert failure["error_type"]=="AssertionError" and len(failure["commands"])==7
    assert failure["commands"][-1]["returncode"]==1104 and "uuid.lib" in failure["error"].lower()
    assert not failure["forbidden_access_attempts"] and sys.dont_write_bytecode and not sys.flags.optimize
    start=h.document(stage/"started.json");identifier=start["build_id"]
    build=p/"Build/UiWindowHost"/identifier;output=p/"evidence/ui_window_host"/identifier/"build_result.json"
    retry=stage/"link_retry01";assert not retry.exists() and not output.exists() and not (stage/"run.json").exists()
    producer=h.artifact(h.__file__);assert producer["sha256"]==PRODUCER_SHA
    baseline=h.sealed(start["baseline_build"]);base=h.document(baseline["path"])
    component_ref=h.sealed(start["component"]);component=h.document(component_ref["path"])
    component_inputs={h.key(r["path"]):r for r in component["inputs"]}
    archive=p/"Source/Host/NativeSaveArchive.h";envelope=p/"Source/Host/NativeSaveEnvelope.h"
    codec=[h.sealed(component_inputs[h.key(f)]) for f in (archive,envelope)]
    oldroot=p/"Build/UiWindowHost"/base["build_id"]
    relocate=lambda f:build/Path(f).relative_to(oldroot)
    live,donors,materialized={},{},{}
    def mapped(row):
        donor=h.sealed(row);donors[h.key(row["path"])]=donor
        original=row.get("original_path",row.get("original_source"))
        if original:
            current=h.artifact(original);live[h.key(original)]=current
            expected=codec[0] if h.key(original)==h.key(archive) else row
            assert all(current[k]==expected[k] for k in ("bytes","sha256")),original
        target=relocate(row["path"]);h.ordinary(target,build)
        new={**row,**h.artifact(target)}
        expected=codec[0] if original and h.key(original)==h.key(archive) else row
        assert all(new[k]==expected[k] for k in ("bytes","sha256")),str(target)
        if original and h.key(original)==h.key(archive):
            assert new["file_identity"]!=current["file_identity"] and new["file_identity"]!=donor["file_identity"]
            new["materialization"]="copy_changed_live_source";new.pop("reused_from_path",None)
        else:
            assert new["file_identity"]==donor["file_identity"]
            new.update(materialization="hardlink",reused_from_path=row["path"])
        materialized[h.key(target)]=new
        return new
    compiler_inputs=[mapped(r) for r in base["compiler_inputs"]]
    template=next(r for r in base["compiler_inputs"] if h.key(r["original_path"])==h.key(archive))
    envelope_path=relocate(template["path"]).with_name(envelope.name)
    envelope_row={**template,**h.artifact(envelope_path),"original_path":str(envelope),"relative_path":str(Path(template["relative_path"]).with_name(envelope.name)),"materialization":"copy_changed_live_source"}
    envelope_row.pop("reused_from_path",None);assert envelope_row["sha256"]==codec[1]["sha256"]
    assert envelope_row["file_identity"]!=codec[1]["file_identity"]
    compiler_inputs.append(envelope_row);materialized[h.key(envelope_path)]=envelope_row;live[h.key(envelope)]=codec[1]
    sources=[mapped(r) for r in base["sources"]]+[{**envelope_row,"original_source":str(envelope)}]
    providers=[mapped(r) for r in base["provider_inputs"]];systems=[mapped(r) for r in base["system_libraries"]]
    tools=[mapped(r) for r in base["build_tools"]];provider_reports={k:mapped(r) for k,r in base["provider_reports"].items()};assets=mapped(base["ui_assets"])
    for name in ("compiler","linker","dumpbin","executable","map","link_response","link_log"):
        live[h.key(base[name]["path"])]=h.sealed(base[name])
    records=[h.document(stage/("compiled_"+name+".json")) for name in h.UNITS]
    objects=[]
    for record in records:
        for field in ("response","log","dependency_report","object"):h.sealed(record[field])
        old=next(r for r in base["final_compilation"]["translation_units"] if r["translation_unit"]==record["translation_unit"])
        expected={h.key(relocate(f)) for f in h.dependencies(old["dependency_report"]["path"])}
        if h.key(template["path"]) in h.dependencies(old["dependency_report"]["path"]):expected.add(h.key(envelope_path))
        assert h.dependencies(record["dependency_report"]["path"])==expected
        assert record["returncode"]==0 and len(record["command"])==2
        assert h.key(record["command"][0])==h.key(base["compiler"]["path"])
        assert record["command"][1]=="@"+record["response"]["path"]
        objects.append(record["object"])
    postpath=p/"evidence/native_save_archive/portable_envelope/publication/post_checks.json";post=h.document(postpath)
    protected={h.key(r["path"]):h.sealed(r) for k in ("protected_files","source_contract_inputs","source_and_proof_files") for r in post[k]}
    for c in post["component_input_revisions"]:protected[h.key(c["after"]["path"])]=h.sealed(c["after"])
    live[h.key(postpath)]=h.artifact(postpath)
    for row in [*live.values(),*donors.values(),producer,h.artifact(__file__),baseline,component_ref,failure_ref,h.artifact(stage/"started.json"),h.artifact(p/"evidence/native_save_archive/host_relink/storage_before.json")]:protected[h.key(row["path"])]=row
    failed_rsp=h.artifact(build/"final/link.rsp");failed_log=h.artifact(stage/"link.log")
    um=Path(base["system_libraries"][0]["original_path"]).parent;vc=Path(base["compiler"]["path"]).parents[3]/"lib/x64"
    implicit_origins=[(vc,n) for n in ("msvcrt.lib","msvcprt.lib","vcruntime.lib","oldnames.lib")]+[(um,"bcrypt.lib"),(um,"kernel32.lib"),(um.parents[1]/"ucrt/x64","ucrt.lib"),(um,"uuid.lib")]
    implicit_before=[h.artifact(root/name)|{"name":name} for root,name in implicit_origins]
    implicit_folder=build/"frozen/implicit_libraries"
    implicit=[h.artifact(implicit_folder/r["name"])|{"original_path":r["path"],"name":r["name"],"materialization":"copied_system_input" if r["name"]=="bcrypt.lib" else "attested_snapshot_hardlink"} for r in implicit_before[:-1]]
    assert all(r["sha256"]==q["sha256"] for r,q in zip(implicit,implicit_before))
    donor_root=p/"evidence/found_value_shared_bridge/20261002T152931Z_bbc131426b";donor_report=h.artifact(donor_root/"conformance.json")
    assert donor_report["sha256"]=="da2f1d5d9e759cbff7618ea280a3878177f16dc1f59d945d57e67be4a01d43df"
    donor_rows=h.document(donor_report["path"])["configurations"][0]["selected_link_libraries"]
    uuid_donor=next(r for r in donor_rows if Path(r["path"]).name.casefold()=="uuid.lib")
    uuid_pin=h.sealed({**uuid_donor,"bytes":uuid_donor["size"]});assert uuid_pin["sha256"]==implicit_before[-1]["sha256"]
    for row in [donor_report,*[h.sealed({**r,"bytes":r["size"]}) for r in donor_rows]]:protected[h.key(row["path"])]=row
    kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.GetCurrentProcess.restype=ctypes.c_void_p;kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_uint32];assert kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000)
    denied,commands,pending=[],[],{}
    write_paths={h.key(output),h.key(build/"final/link_retry01.rsp"),h.key(build/"final/ZeroSisHost_x64.exe"),h.key(build/"final/ZeroSisHost_x64.map"),h.key(implicit_folder/"uuid.lib"),h.key(stage/"run.json")}
    def guard(event,values):
        def deny():denied.append(dict(event=event,target=str(values[0])[:200]));raise PermissionError("Link continuation scope: "+event)
        if event=="subprocess.Popen":
            exe,words,cwd,_=values;expected=pending.get("command")
            if not expected or h.key(cwd)!=h.key(pending["cwd"]):deny()
            if isinstance(words,(tuple,list)):
                if list(words)!=expected:deny()
            elif str(words)!=subprocess.list2cmdline(expected):deny()
            if exe is not None and h.key(exe)!=h.key(expected[0]):deny()
            commands.append(dict(executable=expected[0],command=expected,cwd=str(cwd)))
        elif event=="open" and isinstance(values[0],(str,bytes,os.PathLike)):
            name,mode,flags=values;k=h.key(os.fsdecode(name))
            if any(s in k for s in ("\\my games\\","\\.codex\\","\\steamapps\\common\\")):deny()
            if flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND) and k not in write_paths and not k.startswith(h.key(retry)+os.sep):deny()
        elif event in ("os.mkdir","os.link"):
            target=values[1] if event=="os.link" else values[0];k=h.key(target)
            if k not in write_paths and k!=h.key(retry) and not k.startswith(h.key(retry)+os.sep):deny()
        elif event.startswith(("socket.","ctypes.dlopen")) or event in ("os.remove","os.rmdir","os.rename","os.chmod","os.utime","os.system","os.startfile","os.exec","os.posix_spawn","os.symlink"):deny()
    gzip.compress(b"warm",mtime=0);sys.addaudithook(guard);retry.mkdir()
    packed=retry/"compile_producer.py.gz";packed.write_bytes(gzip.compress(Path(h.__file__).read_bytes(),mtime=0));assert hashlib.sha256(gzip.decompress(packed.read_bytes())).hexdigest()==PRODUCER_SHA
    authority=retry/"authority.json";h.write(authority,dict(schema="zerosis.native_save.link_continuation.v1",utc=datetime.now(timezone.utc).isoformat(),failure=failure_ref,baseline=baseline,objects_before=objects,failed_link_response=failed_rsp,failed_link_log=failed_log,added_implicit_library=implicit_before[-1],uuid_donor=uuid_pin,recompile_allowed=False,host_gamecore_hwnd_execution_allowed=False,full_engine_goal_complete=False))
    try:
        os.link(uuid_pin["path"],implicit_folder/"uuid.lib")
        implicit.append(h.artifact(implicit_folder/"uuid.lib")|{"original_path":implicit_before[-1]["path"],"name":"uuid.lib","materialization":"attested_snapshot_hardlink"})
        pending.update(command=["cmd.exe","/d","/c",str(retry/"read_build_environment.cmd")],cwd=str(retry))
        env,compiler=environment_for(Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"),"x64",retry);commands[-1]["returncode"]=0;pending.clear()
        assert h.key(compiler)==h.key(base["compiler"]["path"]) and not any(env.get(k) for k in ("CL","_CL_","LINK"))
        env["INCLUDE"]=";".join(str(build/"frozen/include_roots"/("system_%02d"%i)) for i in range(len(base["system_include_roots"])))
        env["LIB"]=str(implicit_folder);env["TMP"]=env["TEMP"]=str(build/"tmp");env["VSLANG"]="1033"
        def execute(command,cwd,log):
            pending.update(command=[str(v) for v in command],cwd=str(cwd));r=subprocess.run(pending["command"],cwd=cwd,env=env,capture_output=True,timeout=300,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS);commands[-1]["returncode"]=r.returncode;pending.clear();log.write_bytes(r.stdout+r.stderr)
            assert r.returncode==0 and not re.search(rb"\bwarning\s+(?:C|LNK)\d+",r.stdout+r.stderr,re.I),(r.returncode,(r.stdout+r.stderr)[-2000:])
            return r
        response=build/"final/link_retry01.rsp";response.write_bytes(Path(failed_rsp["path"]).read_bytes())
        link_log=retry/"link.log";execute([base["linker"]["path"],"@"+str(response)],response.parent,link_log)
        exe=build/"final/ZeroSisHost_x64.exe";mapfile=build/"final/ZeroSisHost_x64.map";imports_log=retry/"imports.log";r=execute([base["dumpbin"]["path"],"/dependents",str(exe)],exe.parent,imports_log)
        imports=re.findall(r"^\s+([\w.-]+\.dll)\s*$",r.stdout.decode("ascii",errors="replace"),re.M|re.I)
        assert {n.casefold() for n in imports}=={n.casefold() for n in base["imports"]["dependencies"]}
        pe=h.pe_header(exe);assert pe["architecture"]=="x64" and pe["pe_format"]=="PE32+"
        implicit_after=[h.sealed(row)|{"name":row["name"]} for row in implicit_before];assert implicit_after==implicit_before
        for rows in (implicit,materialized.values(),protected.values(),live.values(),objects):
            for row in rows:h.sealed(row)
        maptext=mapfile.read_text(encoding="mbcs",errors="replace");names={m.casefold().removesuffix(".lib")+".lib" for m in re.findall(r"\s([\w.-]+):\S+\.(?:obj|dll)\s*$",maptext,re.I|re.M)}
        actual=sorted(names&{r["name"] for r in implicit});assert len(actual)==6
        continuation=dict(tool=h.artifact(__file__),authority=h.artifact(authority),failed_link_response=failed_rsp,failed_link_log=failed_log,environment_response=h.artifact(retry/"read_build_environment.cmd"),added_implicit_libraries=[implicit[-1]],commands_before=failure["commands"],commands_after=commands)
        report={**base,"build_id":identifier,"status":"UI_WINDOW_HOST_CANDIDATE_BUILT","baseline_build":baseline,"native_save_component":component_ref,"relink_builder":producer,"compile_producer":{"source_gzip":h.artifact(packed),"source_sha256":PRODUCER_SHA,"failure":failure_ref},"link_continuation":continuation,"compiler_inputs":compiler_inputs,"compiler_dependency_count":len(compiler_inputs),"sources":sources,"provider_inputs":providers,"system_libraries":systems,"libraries":providers+systems,"provider_reports":provider_reports,"ui_assets":assets,"build_tools":tools,"ui_asset_preparation":{"status":"UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED","executed":False},"dependency_discovery":{"executed":False,"reason":"Attested baseline closure plus the approved new envelope; every final dependency set checked."},"final_compilation":{"translation_units":records},"final_dependency_reports":{r["translation_unit"]:r["dependency_report"] for r in records},"response":records[0]["response"],"dependency_report":records[0]["dependency_report"],"link_response":h.artifact(response),"link_log":h.artifact(link_log),"link_snapshot":{"response":h.artifact(response),"objects_before":objects,"objects_after":[h.sealed(r) for r in objects],"returncode":0},"map":h.artifact(mapfile),"executable":h.artifact(exe)|{"pe":pe},"imports":{"dependencies":imports,"log":h.artifact(imports_log)},"current_source_inputs":list(live.values()),"protected_artifacts":list(protected.values()),"implicit_libraries_before":implicit_before,"implicit_libraries_after":implicit_after,"implicit_libraries":implicit,"actual_implicit_library_namesfrommap":actual,"compiler":h.sealed(base["compiler"]),"linker":h.sealed(base["linker"]),"dumpbin":h.sealed(base["dumpbin"]),"source_inputs_unchanged":True,"provider_inputs_unchanged":True,"sources_changed_from_baseline":codec[:1],"new_source_inputs":codec[1:],"final_environment":{n:env.get(n,"") for n in ("INCLUDE","LIB","TMP","TEMP","VSLANG","CL","_CL_","LINK")},"frozen_input_reuse":{"hardlinked_files":sum(r["materialization"]=="hardlink" for r in materialized.values()),"hardlinked_logical_bytes":sum(r["bytes"] for r in materialized.values() if r["materialization"]=="hardlink"),"copied_source_bytes":sum(r["bytes"] for r in materialized.values() if r["materialization"]!="hardlink"),"donor_content_and_metadata_preserved":True},"host_runtime_executed":False,"gamecore_loaded":False,"sdk_linked":False,"mods_updated":False,"stage_updated":False,"default_promoted":False,"full_engine_goal_complete":False,"forbidden_access_attempts":denied,"scope":"Five full current Host units and link-only continuation after frozen UUID input repair; no Host/GameCore/HWND execution, catalog regeneration or default promotion."}
        for field in ("dependency_discovery_reports","compile_log","source_hashes_before","source_hashes_after","compiler_dependency_live_hashes_after"):report.pop(field,None)
        assert len(compiler_inputs)==545 and len(sources)==81 and len(commands)==3 and not denied
        h.write(output,report)
        run=dict(schema="zerosis.native_save.host_relink_run.v1",status="PASS_CURRENT_NATIVE_SAVE_HOST_LINK_ONLY",utc=datetime.now(timezone.utc).isoformat(),build_id=identifier,build_result=h.artifact(output),commands=failure["commands"]+commands,actual_objects=objects,link_snapshot=report["link_snapshot"],link_continuation=continuation,protected_unchanged=True,current_inputs_unchanged=True,forbidden_access_attempts=denied,host_runtime_executed=False,gamecore_loaded=False,hwnd_created=False,default_promoted=False,full_engine_goal_complete=False)
        h.write(stage/"run.json",run);print(json.dumps(dict(status=run["status"],build_id=identifier,build_result=h.artifact(output),run=h.artifact(stage/"run.json"),commands=len(run["commands"]),executable=report["executable"])))
        return 0
    except BaseException as error:
        h.write(retry/"failure.json",dict(status="FAILED_DO_NOT_REPLAY",error_type=type(error).__name__,error=str(error)[:4000],commands=commands,forbidden_access_attempts=denied));raise


if __name__=="__main__":raise SystemExit(main())
