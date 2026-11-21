"""Check an explicit diagnostic record budget without changing parser defaults.

Reuse authenticated C++ frame spans and one pinned public file in RAM. Only
one no-SDK probe build, six argv controls and one full wire diagnostic run.
"""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/map_trace/record_budget"
SOURCE_SHA = "8a2aaf84479f53873cc8df94c8c956d7cf431acc9c369d4ec3c2327db62dbe93"
CHANGE_SHA = "42b097539aa3fd3f1f1622d129be3138df8b59858efb5ed534b0825696c97d70"
PINS = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}


def main():
    assert os.name == "nt" and len(sys.argv) == 1 and not sys.flags.optimize
    for name, digest in PINS.items():
        path = PROJECT / "tools" / (name + ".py")
        for part in (path, *path.parents):
            assert not part.lstat().st_file_attributes & 0x400
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    modules = {name:importlib.import_module(name) for name in PINS}
    assert all(Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py") for name,module in modules.items())
    g,h,n = [modules[name] for name in ("probe_public_retail_save","verify_retail_save_header","native_build")]
    for encoding in ("mbcs","utf-8","utf-8-sig"):
        b"warm".decode(encoding)
    def load(path, digest):
        row = g.artifact(path)
        assert row["sha256"] == digest
        return row,g.read_json(path)
    prior_pin,prior = load(STAGE.parent / "chunk_frames_component/public_result.json", "9219e7b264e4190127a29f7d81f6bdfb403637221e1fd0d7ef275559dc7b614d")
    post_pin,post = load(STAGE.parent / "chunk_frames_component/publication/post_checks.json", "aa2ef20051bfc038752100fa334fd404b49a6fd5bc9afec5ae0051af7df11584")
    protected = post["protected_files"]
    g.unchanged(protected)
    source = PROJECT / "Tests/retail_public_probe.cpp"
    source_pin = g.artifact(source)
    assert source_pin["sha256"] == SOURCE_SHA
    change_pin,change = load(STAGE / "source_change.json",CHANGE_SHA)
    backup = STAGE / "source_before.cpp.gz"
    backup_pin = g.artifact(backup)
    before = gzip.decompress(backup.read_bytes())
    assert hashlib.sha256(before).hexdigest() == "6d4c9a22434e6373b51b6615f5c32d4862729d394ff3bec47491d08df66a698d"
    assert len(before) == 27099
    headers = g.host_headers(source,PROJECT)
    assert g.artifact(PROJECT / "Source/Host/RetailSaveChunkFrames.h")["sha256"] == "b355fc3b732825441a1464c36831eafe3e57d99c3ee86079c784b4969e71fea7"
    inputs = [g.artifact(path) for path in (source,*headers,Path(__file__).absolute(),
        *(PROJECT / "tools" / (name + ".py") for name in PINS))] + [prior_pin,post_pin,change_pin,backup_pin]
    compiler = g.artifact(h.COMPILER)
    assert compiler["sha256"] == h.COMPILER_SHA
    fingerprint = g.identity({"schema":"zerosis.retail.record_budget.identity.v1","inputs":inputs,"compiler":compiler})
    parent = g.ordinary(PROJECT / "Build/RetailRecordBudget")
    parent.mkdir(exist_ok=True)
    root = g.ordinary(parent / fingerprint)
    evidence = STAGE / ("compile_" + fingerprint)
    result_path,start_path = STAGE / "result.json",STAGE / "started.json"
    assert not any(path.exists() for path in (root,evidence,result_path,start_path)), "Inspect the exact prior attempt"
    case = prior["cases"][0]
    assert case["fixture"]["id"] == "jpl_before" and case["wire"]["observation"]["error"]["code"] == 6
    fixture = case["fixture"]
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
    url = fixture["raw_url"]
    assert url.startswith("https://raw.githubusercontent.com/")
    with opener.open(urllib.request.Request(url,headers={"User-Agent":"ZeroSis-record-budget-diagnostic"}),timeout=20) as response:
        assert response.geturl() == url
        raw = response.read(fixture["bytes"]+1)
    assert len(raw) == fixture["bytes"] and hashlib.sha256(raw).hexdigest() == case["raw_sha256"]
    assert hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() == fixture["git_blob_sha1"]
    frames = case["header"]["observation"]["chunk_frames"]
    position,total = frames["container_span"]["offset"],0
    assert frames["container_span"]["bytes"] == len(raw)-position and len(frames["frames"]) == 11
    decoder,inflated = zlib.decompressobj(),bytearray()
    for frame in frames["frames"]:
        assert frame["header"] == {"offset":position,"bytes":4}
        begin,size = frame["payload"]["offset"],frame["payload"]["bytes"]
        assert begin == position+4 and 0 < size <= 65536 and size <= len(raw)-begin
        assert int.from_bytes(raw[position:position+4],"little") == size
        remaining = 64*1024*1024-len(inflated)
        assert remaining > 0
        inflated.extend(decoder.decompress(raw[begin:begin+size],remaining))
        assert not decoder.unconsumed_tail and not decoder.unused_data
        position,total = begin+size,total+size
    assert position == len(raw) and total == frames["total_payload_bytes"]
    assert len(inflated) == case["inflated_bytes"] and hashlib.sha256(inflated).hexdigest() == case["inflated_sha256"]
    assert decoder.eof is False
    common = ("--awards","5","--grand","4","--projects","6","--boolean-encoding","sdk-byte","--max-input","1")
    definitions = [
        ("unchanged_default",("--inflated",*common),b"\0",False),
        ("zero_rejected",("--inflated",*common,"--max-records","0"),b"",True),
        ("duplicate_rejected",("--inflated",*common,"--max-records","2097152","--max-records","1"),b"",True),
        ("bound_plus_one_rejected",("--inflated",*common,"--max-records","67108865"),b"",True),
        ("decimal_rejected",("--inflated",*common,"--max-records","1.0"),b"",True),
        ("header_mode_rejected",("--header",*common,"--max-records","2097152"),b"",True),
        ("jpl_explicit_budget",("--inflated","--awards","5","--grand","4","--projects","6","--boolean-encoding","sdk-byte",
            "--max-input",str(len(inflated)),"--max-records","2097152"),bytes(inflated),False)]
    commands = [(str(root / "RetailPublicProbe.exe"),*args) for _name,args,_data,_reject in definitions]
    assert len(set(commands)) == 7
    env_command = ("cmd.exe","/d","/c",str(root / "read_build_environment.cmd"))
    compile_command = (str(h.COMPILER),"@"+str(root / "compile.rsp"),"/link","/MACHINE:X64","/INCREMENTAL:NO","/Brepro","/WX","/OPT:REF","/OPT:ICF")
    outputs = [root/name for name in ("RetailPublicProbe.exe","retail_public_probe.obj","compile.rsp","dependencies.json","read_build_environment.cmd")]
    outputs += [evidence/name for name in ("build_started.json","compile.log","build_result.json","failed_attempt.json")]
    outputs += [result_path,start_path,STAGE/"failed_attempt.json"]
    for index in range(7):
        outputs += [STAGE/("probe_"+str(index)+suffix) for suffix in (".stdout.log",".stderr.log",".process.json")]
    guard = g.OfflineGuard(commands=[env_command,compile_command,*commands],directory=root,
        readable=[Path(row["path"]) for row in inputs+protected+[compiler]],writable=outputs,directories=[root,evidence])
    sys.addaudithook(guard.audit)
    try:
        g.write_json(start_path,{"fingerprint":fingerprint,"inputs":inputs,"commands":commands,"producer_finish_verified":False})
        build,environment = g.ensure_build(project=PROJECT,root=root,evidence=evidence,source=source,headers=headers,
            inputs=inputs,compiler=compiler,compiler_path=h.COMPILER,vs=h.VS,command=compile_command,
            environment_for=n.environment_for,pe_imports=h.pe_imports,guard=guard,fingerprint=fingerprint)
        observations = []
        for index,(name,_args,data,rejected) in enumerate(definitions):
            run = subprocess.run(commands[index],cwd=root,env=environment,input=data,capture_output=True,timeout=45,
                creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            assert len(run.stdout)<=64*1024 and len(run.stderr)<=16*1024
            stdout,stderr,process = [STAGE/("probe_"+str(index)+suffix) for suffix in (".stdout.log",".stderr.log",".process.json")]
            g.write_text(stdout,run.stdout.decode("utf-8-sig",errors="replace"),64*1024)
            g.write_text(stderr,run.stderr.decode("utf-8",errors="replace"),32*1024)
            g.write_json(process,{"returncode":run.returncode,"stdout_bytes":len(run.stdout),"stderr_bytes":len(run.stderr)})
            assert run.returncode in (0,1)
            native = g.small_native_json(run.stdout)
            if rejected:
                assert run.returncode==1 and native["status"]=="DIAGNOSTIC_ARGUMENT_REJECTED" and not native["stdin_read_complete"]
            else:
                assert native["stdin_read_complete"] and native["input_bytes"]==len(data)
                assert native["profiles"]["boolean_encoding"]=="sdk-byte" and native["profiles"]["widths_explicit"]
                assert [native["profiles"][key] for key in ("awards","grand","projects")]==[5,4,6]
                if index==0:
                    assert native["maximum_total_records"]==1048576 and native["profiles"]["record_budget_explicit"] is False
                    assert native["status"]=="DIAGNOSTIC_PARSER_REJECTED" and run.returncode==1
                else:
                    assert native["maximum_total_records"]==2097152 and native["profiles"]["record_budget_explicit"] is True
                    assert native["retail_outer_sequence_verified"] is False
            observations.append({"name":name,"returncode":run.returncode,"observation":native,"stdout":g.artifact(stdout),
                "stderr":g.artifact(stderr),"process":g.artifact(process)})
        g.unchanged(inputs+protected+[compiler]+list(build["artifacts"].values()))
        assert not guard.denied and len(guard.calls)==9
        result = {"schema":"zerosis.retail.record_budget.diagnostic.v1","status":"OBSERVED_EXPLICIT_RECORD_BUDGET_DIAGNOSTICS",
            "utc":datetime.now(timezone.utc).isoformat(),"inputs":inputs,"build_report":g.artifact(evidence/"build_result.json"),
            "protected_count":len(protected),"cases":observations,"fixture":fixture,"raw_sha256":case["raw_sha256"],
            "inflated_bytes":len(inflated),"inflated_sha256":case["inflated_sha256"],"frame_spans_reused_from":prior_pin,
            "child_commands":guard.calls,"forbidden_access_attempts":guard.denied,"retired_logical_bytes":build["retired_logical_bytes"],
            "default_total_record_limit_unchanged":True,"other_parser_limits_unchanged":True,"automatic_retry_used":False,
            "producer_contract_verified":False,"zlib_eof":False,"raw_inflated_or_database_saved":False,
            "sdk_host_hwnd_or_original_game_executed":False,"user_game_files_accessed":False,
            "complete_save_verified":False,"restore_approved":False,"full_engine_goal_complete":False}
        g.write_json(result_path,result)
        full = observations[-1]["observation"]
        print(json.dumps({"report":g.artifact(result_path),"argv_cases":6,"jpl_status":full["status"],
            "teams":full["teams_completed"],"players":full["players_completed"],"records":full["array_records_completed"],
            "remainder":full["remaining_input_bytes"],"supporting":full["supporting"],"error":full["error"]}))
        return 0
    except BaseException as error:
        g.write_json(STAGE/"failed_attempt.json",{"error":type(error).__name__+": "+str(error),
            "child_commands":guard.calls,"forbidden_access_attempts":guard.denied,"sdk_or_game_executed":False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
