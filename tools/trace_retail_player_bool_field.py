"""Locate one pinned public Player bool witness using existing pure inspectors.

Only one no-SDK build and one headless stdin run; raw/plaintext stay in RAM.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
from datetime import datetime,timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.request
import zlib

PROJECT=Path(__file__).absolute().parents[1]
BASE=PROJECT/"evidence/retail_save_container/map_trace"
STAGE=BASE/"restore_booleans/player1_trace"
SOURCE_SHA="a6010b3f0efff794b1638b9ca4fde4241b26b6b9552d827cf316f9ebbb157a0b"
PINS={
    "probe_public_retail_save":"f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header":"9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build":"c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline":"7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}


def main():
    assert os.name=="nt" and len(sys.argv)==1 and not sys.flags.optimize
    for name,digest in PINS.items():
        path=PROJECT/"tools"/(name+".py")
        for part in (path,*path.parents):
            assert not part.lstat().st_file_attributes&0x400
        assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    modules={name:importlib.import_module(name) for name in PINS}
    assert all(Path(module.__file__).absolute()==PROJECT/"tools"/(name+".py") for name,module in modules.items())
    g,h,n=[modules[name] for name in ("probe_public_retail_save","verify_retail_save_header","native_build")]
    for encoding in ("mbcs","utf-8","utf-8-sig"):
        b"warm".decode(encoding)
    def load(path,digest):
        row=g.artifact(path);assert row["sha256"]==digest
        return row,g.read_json(path)
    public_pin,public=load(BASE/"chunk_frames_component/public_result.json","9219e7b264e4190127a29f7d81f6bdfb403637221e1fd0d7ef275559dc7b614d")
    bool_pin,boolean=load(BASE/"restore_booleans/result.json","f367c4866e2445cac4daedc77f073504083d41643883de75aa1fe7cc34ed4028")
    post_pin,post=load(BASE/"restore_booleans/publication/post_checks.json","ea968edfa1ceb221970988edd518a3ef62f67c0a6700ba6dc7a70d2f4aa38d5b")
    g.unchanged(post["protected_files"]+post["source_contract_inputs"]+[post["current_probe_source"]])
    source=PROJECT/"Tests/retail_player_bool_trace.cpp"
    assert g.artifact(source)["sha256"]==SOURCE_SHA
    headers=g.host_headers(source,PROJECT)
    inputs=[g.artifact(path) for path in (source,*headers,Path(__file__).absolute(),
        *(PROJECT/"tools"/(name+".py") for name in PINS))]+[public_pin,bool_pin,post_pin]
    compiler=g.artifact(h.COMPILER);assert compiler["sha256"]==h.COMPILER_SHA
    fingerprint=g.identity({"schema":"zerosis.retail.player_bool_field.identity.v1","inputs":inputs,"compiler":compiler})
    parent=g.ordinary(PROJECT/"Build/RetailPlayerBoolTrace");parent.mkdir(exist_ok=True);STAGE.mkdir(parents=True,exist_ok=True)
    root=g.ordinary(parent/fingerprint);evidence=STAGE/("compile_"+fingerprint)
    result_path,start_path=STAGE/"result.json",STAGE/"started.json"
    assert not any(path.exists() for path in (root,evidence,result_path,start_path)),"Inspect the exact previous attempt"
    case=public["cases"][1];fixture=case["fixture"]
    assert fixture["id"]=="rivar_settler12"
    expected=case["wire"]["observation"]["players"][1]
    assert expected["slot"]==expected["id"]==1 and expected["start"]==7625870 and expected["end"]==7799422 and expected["records"]==13831
    witness=boolean["cases"][1]["noncanonical_bool_witness"]
    assert witness=={"inflated_byte_offset":7795644,"value":68}
    context=ssl.create_default_context()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    url=fixture["raw_url"];assert url.startswith("https://raw.githubusercontent.com/")
    with opener.open(urllib.request.Request(url,headers={"User-Agent":"ZeroSis-player-bool-field-trace"}),timeout=20) as response:
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
        remaining=64*1024*1024-len(body);assert remaining>0
        body.extend(decoder.decompress(raw[begin:begin+size],remaining))
        assert not decoder.unconsumed_tail and not decoder.unused_data
        cursor,total=begin+size,total+size
    assert cursor==len(raw) and total==frames["total_payload_bytes"] and decoder.eof is False
    assert len(body)==16727961==case["inflated_bytes"] and hashlib.sha256(body).hexdigest()==case["inflated_sha256"]
    assert body[witness["inflated_byte_offset"]]==68
    env_command=("cmd.exe","/d","/c",str(root/"read_build_environment.cmd"))
    compile_command=(str(h.COMPILER),"@"+str(root/"compile.rsp"),"/link","/MACHINE:X64","/INCREMENTAL:NO","/Brepro","/WX","/OPT:REF","/OPT:ICF")
    command=(str(root/"RetailPublicProbe.exe"),)
    outputs=[root/name for name in ("RetailPublicProbe.exe","retail_public_probe.obj","compile.rsp","dependencies.json","read_build_environment.cmd")]
    outputs += [evidence/name for name in ("build_started.json","compile.log","build_result.json","failed_attempt.json")]
    outputs += [STAGE/name for name in ("result.json","started.json","stdout.log","stderr.log","process.json","failed_attempt.json")]
    guard=g.OfflineGuard(commands=[env_command,compile_command,command],directory=root,
        readable=[Path(row["path"]) for row in inputs+post["protected_files"]+post["source_contract_inputs"]+[post["current_probe_source"],compiler]],
        writable=outputs,directories=[root,evidence])
    sys.addaudithook(guard.audit)
    try:
        g.write_json(start_path,{"fingerprint":fingerprint,"inputs":inputs,"fixture":fixture,"expected_player":expected,"witness":witness,"sdk_executed":False})
        build,environment=g.ensure_build(project=PROJECT,root=root,evidence=evidence,source=source,headers=headers,inputs=inputs,
            compiler=compiler,compiler_path=h.COMPILER,vs=h.VS,command=compile_command,environment_for=n.environment_for,
            pe_imports=h.pe_imports,guard=guard,fingerprint=fingerprint)
        run=subprocess.run(command,cwd=root,env=environment,input=bytes(body),capture_output=True,timeout=45,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        assert len(run.stdout)<=64*1024 and len(run.stderr)<=16*1024
        g.write_text(STAGE/"stdout.log",run.stdout.decode("utf-8-sig",errors="replace"),64*1024)
        g.write_text(STAGE/"stderr.log",run.stderr.decode("utf-8",errors="replace"),32*1024)
        g.write_json(STAGE/"process.json",{"returncode":run.returncode,"stdout_bytes":len(run.stdout),"stderr_bytes":len(run.stderr)})
        assert run.returncode==0,"Inspect the preserved diagnostic stdout/stderr"
        native=json.loads(run.stdout.decode("utf-8-sig"))
        assert native["status"]=="OBSERVED_PINNED_PLAYER_BOOL_CONTAINMENT" and native["input_bytes"]==len(body)
        assert native["player_id"]==1 and native["player_start"]==7625870 and native["player_end"]==7799422 and native["array_records"]==13831
        assert native["witness"]=={"offset":7795644,"value":68}
        assert all(native[key] is False for key in ("sdk_executed","gamecore_loaded","window_created","game_accessed","user_saves_accessed",
            "complete_player_validated","complete_save_verified","restore_approved","full_engine_goal_complete"))
        assert 7<=len(native["spans"])<=64
        matches=[]
        for row in native["spans"]:
            offset,size=row["offset"],row["bytes"]
            assert isinstance(row["name"],str) and len(row["name"])<80 and 0<=offset<=len(body) and 0<=size<=len(body)-offset
            assert row["contains_witness"]==(offset<=7795644<offset+size)
            if row["contains_witness"]:matches.append(row)
        assert matches
        g.unchanged(inputs+post["protected_files"]+post["source_contract_inputs"]+[post["current_probe_source"],compiler]+list(build["artifacts"].values()))
        assert len(guard.calls)==3 and not guard.denied
        result={"schema":"zerosis.retail.player_bool_field_trace.v1","status":"OBSERVED_PINNED_PLAYER_BOOL_SUBRECORD_CONTAINMENT",
            "utc":datetime.now(timezone.utc).isoformat(),"inputs":inputs,"build_report":g.artifact(evidence/"build_result.json"),
            "fixture":fixture,"raw_sha256":case["raw_sha256"],"inflated_bytes":len(body),"inflated_sha256":case["inflated_sha256"],
            "native":native,"matching_spans":matches,"stdout":g.artifact(STAGE/"stdout.log"),"stderr":g.artifact(STAGE/"stderr.log"),
            "process":g.artifact(STAGE/"process.json"),"child_commands":guard.calls,"forbidden_access_attempts":guard.denied,
            "retired_logical_bytes":build["retired_logical_bytes"],"exact_source_member_identified":False,"producer_contract_verified":False,
            "raw_inflated_or_database_saved":False,"sdk_host_hwnd_or_original_game_executed":False,"user_game_files_accessed":False,
            "complete_save_verified":False,"restore_approved":False,"full_engine_goal_complete":False}
        g.write_json(result_path,result)
        print(json.dumps({"report":g.artifact(result_path),"matching_spans":matches,"retired_logical_bytes":build["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        g.write_json(STAGE/"failed_attempt.json",{"error":type(error).__name__+": "+str(error),"child_commands":guard.calls,
            "forbidden_access_attempts":guard.denied,"sdk_or_game_executed":False})
        raise


if __name__=="__main__":
    raise SystemExit(main())
