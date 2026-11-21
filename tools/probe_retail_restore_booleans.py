"""Compare canonical SDK bool gating on the two already-framed public inputs.

Reuse one frozen headless executable, never execute SDK code or retain saves.
This checks the inflated wire reader; Pregame bools and SDK restore are separate.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
BASE = PROJECT / "evidence/retail_save_container/map_trace"
STAGE = BASE / "restore_booleans"


def main():
    assert len(sys.argv)==1 and os.name=="nt" and not sys.flags.optimize
    helper=PROJECT/"tools/probe_public_retail_save.py"
    assert hashlib.sha256(helper.read_bytes()).hexdigest()=="f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962"
    import probe_public_retail_save as g
    assert Path(g.__file__).absolute()==helper
    def load(path,digest):
        row=g.artifact(path); assert row["sha256"]==digest
        return row,g.read_json(path)
    public_pin,public=load(BASE/"chunk_frames_component/public_result.json","9219e7b264e4190127a29f7d81f6bdfb403637221e1fd0d7ef275559dc7b614d")
    budget_pin,budget=load(BASE/"record_budget/result.json","c00a7e6c07179e2df7d049e36df42e6484eda51a4a47111086ab63b327a242e1")
    post_pin,post=load(BASE/"record_budget/publication/post_checks.json","c107eea36e90b03eed7cf154d8c756af7c217be1c04e805bfc4c9209646f4a9b")
    build_pin,build=load(Path(budget["build_report"]["path"]),"1c02c404ef3216ad40018ef21d42950d85f863fdb844613f174ed34c6b122c8f")
    assert build["imports"]==["kernel32.dll"]
    g.unchanged(build["inputs"]+list(build["artifacts"].values())+post["protected_files"])
    root=Path(build["build_root"]); exe=Path(build["artifacts"]["executable"]["path"])
    assert exe.parent==root and exe.name=="RetailPublicProbe.exe"
    assert {path.name for path in root.iterdir()}=={"RetailPublicProbe.exe","compile.rsp","dependencies.json"}
    inputs=[g.artifact(path) for path in (Path(__file__).absolute(),helper,
        PROJECT/"Source/Providers/Streams/SdkDataStream.cpp",PROJECT/"Source/Host/RetailSaveStateWire.h")]
    inputs += [public_pin,budget_pin,post_pin,build_pin]+build["inputs"]+list(build["artifacts"].values())
    STAGE.mkdir(exist_ok=True)
    result_path,start_path=STAGE/"result.json",STAGE/"started.json"
    assert not result_path.exists() and not start_path.exists(),"Inspect the exact previous attempt"
    context=ssl.create_default_context()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    buffers=[]
    for case in public["cases"]:
        fixture=case["fixture"]; url=fixture["raw_url"]
        assert url.startswith("https://raw.githubusercontent.com/")
        with opener.open(urllib.request.Request(url,headers={"User-Agent":"ZeroSis-canonical-bool-diagnostic"}),timeout=20) as response:
            assert response.geturl()==url
            raw=response.read(fixture["bytes"]+1)
        assert len(raw)==fixture["bytes"] and hashlib.sha256(raw).hexdigest()==case["raw_sha256"]
        assert hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw).hexdigest()==fixture["git_blob_sha1"]
        frames=case["header"]["observation"]["chunk_frames"]
        cursor,total=frames["container_span"]["offset"],0
        assert frames["container_span"]["bytes"]==len(raw)-cursor and len(frames["frames"])==11
        decoder,body=zlib.decompressobj(),bytearray()
        for frame in frames["frames"]:
            assert frame["header"]=={"offset":cursor,"bytes":4}
            begin,size=frame["payload"]["offset"],frame["payload"]["bytes"]
            assert begin==cursor+4 and 0<size<=65536 and size<=len(raw)-begin
            assert int.from_bytes(raw[cursor:cursor+4],"little")==size
            remaining=64*1024*1024-len(body); assert remaining>0
            body.extend(decoder.decompress(raw[begin:begin+size],remaining))
            assert not decoder.unconsumed_tail and not decoder.unused_data
            cursor,total=begin+size,total+size
        assert cursor==len(raw) and total==frames["total_payload_bytes"] and decoder.eof is False
        assert len(body)==case["inflated_bytes"] and hashlib.sha256(body).hexdigest()==case["inflated_sha256"]
        buffers.append((case,bytes(body)))
    assert len(buffers)==2
    limits=[2097152,1048576]
    commands=[(str(exe),"--inflated","--awards","5","--grand","4","--projects","6","--boolean-encoding","canonical",
        "--max-input",str(len(data)),"--max-records",str(limit)) for (_case,data),limit in zip(buffers,limits)]
    assert len(set(commands))==2
    outputs=[result_path,start_path,STAGE/"failed_attempt.json"]
    for index in range(2):
        outputs += [STAGE/("probe_"+str(index)+suffix) for suffix in (".stdout.log",".stderr.log",".process.json")]
    guard=g.OfflineGuard(commands=commands,directory=root,
        readable=[Path(row["path"]) for row in inputs+post["protected_files"]],writable=outputs,directories=[])
    environment=g.native_environment(root)
    sys.addaudithook(guard.audit)
    try:
        g.write_json(start_path,{"inputs":inputs,"commands":commands,"new_compilation":False,"sdk_executed":False})
        observations=[]
        for index,((case,data),limit) in enumerate(zip(buffers,limits)):
            run=subprocess.run(commands[index],cwd=root,env=environment,input=data,capture_output=True,timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            assert len(run.stdout)<=64*1024 and len(run.stderr)<=16*1024
            stdout,stderr,process=[STAGE/("probe_"+str(index)+suffix) for suffix in (".stdout.log",".stderr.log",".process.json")]
            g.write_text(stdout,run.stdout.decode("utf-8-sig",errors="replace"),64*1024)
            g.write_text(stderr,run.stderr.decode("utf-8",errors="replace"),32*1024)
            g.write_json(process,{"returncode":run.returncode,"stdout_bytes":len(run.stdout),"stderr_bytes":len(run.stderr)})
            assert run.returncode in (0,1)
            native=g.small_native_json(run.stdout)
            assert native["mode"]=="inflated" and native["stdin_read_complete"] and native["input_bytes"]==len(data)
            assert native["profiles"]["boolean_encoding"]=="canonical" and native["profiles"]["boolean_encoding_explicit"]
            assert native["maximum_total_records"]==limit and native["profiles"]["record_budget_explicit"]
            assert [native["profiles"][key] for key in ("awards","grand","projects")]==[5,4,6]
            assert native["retail_outer_sequence_verified"] is False
            witness=None
            if native["error"]["message"]=="Invalid serialized bool":
                offset=native["error"]["offset"]-1
                assert 0<=offset<len(data) and data[offset]>1 and run.returncode==1
                witness={"inflated_byte_offset":offset,"value":data[offset]}
            if run.returncode==0:
                assert native["status"]=="DIAGNOSTIC_SEQUENCE_OBSERVED" and native["declared_sequence_has_zero_remainder"]
                assert native["teams_completed"]==native["players_completed"]==64
                assert native["array_records_completed"]==[1805777,713024][index]
            observations.append({"fixture":case["fixture"],"inflated_bytes":len(data),"inflated_sha256":case["inflated_sha256"],
                "returncode":run.returncode,"observation":native,"noncanonical_bool_witness":witness,
                "stdout":g.artifact(stdout),"stderr":g.artifact(stderr),"process":g.artifact(process)})
        g.unchanged(inputs+post["protected_files"])
        assert not guard.denied and len(guard.calls)==2
        result={"schema":"zerosis.retail.restore_boolean_comparison.v1","status":"OBSERVED_CANONICAL_INFLATED_WIRE_BOOL_GATE",
            "utc":datetime.now(timezone.utc).isoformat(),"inputs":inputs,"cases":observations,
            "child_commands":guard.calls,"forbidden_access_attempts":guard.denied,"new_compilation":False,
            "sdk_boolean_provider_executed":False,"pregame_booleans_validated":False,"producer_contract_verified":False,
            "raw_inflated_or_database_saved":False,"sdk_host_hwnd_or_original_game_executed":False,
            "user_game_files_accessed":False,"complete_save_verified":False,"restore_approved":False,"full_engine_goal_complete":False}
        g.write_json(result_path,result)
        print(json.dumps({"report":g.artifact(result_path),"cases":[{"id":row["fixture"]["id"],
            "status":row["observation"]["status"],"phase":row["observation"]["phase"],
            "players":row["observation"]["players_completed"],"remainder":row["observation"]["remaining_input_bytes"],
            "bool_witness":row["noncanonical_bool_witness"],"error":row["observation"]["error"]} for row in observations]}))
        return 0
    except BaseException as error:
        g.write_json(STAGE/"failed_attempt.json",{"error":type(error).__name__+": "+str(error),
            "child_commands":guard.calls,"forbidden_access_attempts":guard.denied,"sdk_or_game_executed":False})
        raise


if __name__=="__main__":
    raise SystemExit(main())
