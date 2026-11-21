"""Retire only this replacement task's attested intermediate/fixture files."""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

PROJECT = Path(__file__).absolute().parents[1]
BASE = PROJECT / "Build/NativeSaveReplacement"
EVIDENCE = PROJECT / "evidence/save_overwrite/source_contract/native_transaction"
INTERMEDIATES = ("20261016T115651Z_f344f3e1dbe8", "20261016T120106Z_05de0e58ab47",
                 "20261016T120217Z_fe14b88a775b", "20261016T120447Z_2c6a3486c478")

class Basic(C.Structure):
    _fields_ = [("creation", C.c_longlong), ("access", C.c_longlong),
                ("write", C.c_longlong), ("change", C.c_longlong), ("attributes", W.DWORD)]
class Info(C.Structure):
    _fields_ = [("attributes", W.DWORD), ("creation", W.FILETIME), ("access", W.FILETIME),
                ("write", W.FILETIME), ("volume", W.DWORD), ("high", W.DWORD),
                ("low", W.DWORD), ("links", W.DWORD), ("index_high", W.DWORD), ("index_low", W.DWORD)]
class Standard(C.Structure):
    _fields_ = [("allocation", C.c_longlong), ("size", C.c_longlong), ("links", W.DWORD),
                ("delete_pending", C.c_ubyte), ("directory", C.c_ubyte)]
class Disposition(C.Structure):
    _fields_ = [("delete", C.c_ubyte)]

def seal(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def guard(path):
    assert path.resolve(strict=True) == path.absolute()
    assert path == BASE or BASE in path.parents
    for ancestor in (path, *path.parents):
        assert not (getattr(os.lstat(ancestor), "st_file_attributes", 0) & 0x400), str(ancestor)
        if ancestor == PROJECT:
            break

class Kernel:
    def __init__(self):
        self.k = C.WinDLL("kernel32", use_last_error=True)
        definitions = {
            "CreateFileW": ([W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE],W.HANDLE),
            "CloseHandle": ([W.HANDLE],W.BOOL),
            "GetFileInformationByHandle": ([W.HANDLE,C.POINTER(Info)],W.BOOL),
            "GetFileInformationByHandleEx": ([W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
            "GetFinalPathNameByHandleW": ([W.HANDLE,W.LPWSTR,W.DWORD,W.DWORD],W.DWORD),
            "ReadFile": ([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p],W.BOOL),
            "SetFileInformationByHandle": ([W.HANDLE,C.c_int,C.c_void_p,W.DWORD],W.BOOL),
        }
        for name,(args,result) in definitions.items():
            method=getattr(self.k,name);method.argtypes=args;method.restype=result
    @staticmethod
    def require(value):
        if not value: raise C.WinError(C.get_last_error())
    def open(self,path,directory=False,remove=False):
        guard(path)
        access = 0x80 if directory else 0x80000000 | (0x10000|0x100 if remove else 0)
        value=self.k.CreateFileW(str(path),access,3 if directory else 0,None,3,
                                 0x200000 | (0x2000000 if directory else 0),None)
        if value==W.HANDLE(-1).value:raise C.WinError(C.get_last_error())
        return value
    def close(self,value):self.require(self.k.CloseHandle(value))
    def describe(self,value,path,hashed=True):
        i,s=Info(),Standard();self.require(self.k.GetFileInformationByHandle(value,C.byref(i)))
        self.require(self.k.GetFileInformationByHandleEx(value,1,C.byref(s),C.sizeof(s)))
        final=C.create_unicode_buffer(32768);count=self.k.GetFinalPathNameByHandleW(value,final,len(final),0)
        assert count and count<len(final) and Path(final.value.removeprefix("\\\\?\\"))==path
        assert not (i.attributes&0x400) and not s.delete_pending
        out={"path":str(path),"file_id":[i.volume,i.index_high,i.index_low],"links":i.links,
             "attributes":i.attributes,"bytes":s.size,"allocation_bytes":s.allocation,
             "last_write_filetime":(i.write.dwHighDateTime<<32)|i.write.dwLowDateTime,
             "directory":bool(s.directory)}
        if hashed:
            assert not s.directory and i.links==1
            h=hashlib.sha256();buffer=C.create_string_buffer(1024*1024);total=0
            while True:
                count=W.DWORD();self.require(self.k.ReadFile(value,buffer,len(buffer),C.byref(count),None))
                if not count.value:break
                total+=count.value;h.update(buffer.raw[:count.value])
            assert total==s.size;out["sha256"]=h.hexdigest()
        return out
    def capture(self,path,directory=False):
        value=self.open(path,directory)
        try:return self.describe(value,path,not directory)
        finally:self.close(value)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--final-run",required=True)
    args=parser.parse_args();assert re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}",args.final_run)
    assert args.final_run not in INTERMEDIATES
    final_root=BASE/args.final_run;final_report=EVIDENCE/args.final_run/"result.json"
    d=json.loads(final_report.read_text());assert d["run_id"]==args.final_run
    assert d["status"]=="NATIVE_SAVE_CATALOG_BOUNDARIES_PASS" and d["native_checks"]==756
    assert d["replacement_checks"]>=418 and d["process_interruption_recovery_cases"]==12
    output=EVIDENCE/args.final_run/"cleanup.json";assert not output.exists(),"Never rerun a partial cleanup ledger"
    api=Kernel();plan={"schema":"zerosis.owned_replacement_cleanup.v1","utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                     "status":"PLANNED","final_result":seal(final_report),"source":seal(Path(__file__).absolute()),
                     "files":[],"directories":[],"protected":[],"intermediates":[],"error":None}
    pin=api.open(BASE,True)
    try:
        selected=[];dirs=[]
        for run_id in INTERMEDIATES:
            root=BASE/run_id;report=EVIDENCE/run_id/"result.json"
            document=json.loads(report.read_text());assert document["run_id"]==run_id and document.get("finished_utc")
            assert document["status"] in ("NATIVE_SAVE_CATALOG_BOUNDARIES_PASS","NATIVE_SAVE_CATALOG_BOUNDARIES_FAILED")
            plan["intermediates"].append({"root":str(root),"result":seal(report),"status":document["status"]})
            guard(root);assert root.parent==BASE
            selected.extend(f for f in root.rglob("*") if f.is_file())
            dirs.extend(f for f in root.rglob("*") if f.is_dir());dirs.append(root)
        guard(final_root)
        for flavor in ("optimized","debug"):
            folder=final_root/flavor
            for path in folder.iterdir():
                if path.is_dir() and (path.name=="data" or path.name.startswith("crash-")):
                    selected.extend(f for f in path.rglob("*") if f.is_file())
                    dirs.extend(f for f in path.rglob("*") if f.is_dir());dirs.append(path)
                elif path.is_file() and path.name=="native_save_catalog.obj":selected.append(path)
        selected=sorted(set(selected));dirs=sorted(set(dirs),key=lambda f:(-len(f.parts),str(f)))
        for path in selected:plan["files"].append({"before":api.capture(path),"status":"PLANNED"})
        selected_ids={tuple(x["before"]["file_id"]) for x in plan["files"]};assert len(selected_ids)==len(selected)
        for path in final_root.rglob("*"):
            if path.is_file() and path not in selected:
                item=api.capture(path);assert tuple(item["file_id"]) not in selected_ids
                plan["protected"].append(item)
        for path in dirs:plan["directories"].append({"before":api.capture(path,True),"status":"PLANNED"})
        output.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
        for row in plan["files"]:
            before=row["before"];path=Path(before["path"]);value=api.open(path,remove=True)
            try:
                assert api.describe(value,path)==before
                if before["attributes"]&1:
                    basic=Basic();basic.attributes=(before["attributes"]&~1) or 128
                    api.require(api.k.SetFileInformationByHandle(value,0,C.byref(basic),C.sizeof(basic)))
                disposal=Disposition(1);api.require(api.k.SetFileInformationByHandle(value,4,C.byref(disposal),C.sizeof(disposal)))
            finally:api.close(value)
            assert not os.path.lexists(path);row["status"]="REMOVED_VALIDATED_EXCLUSIVE_HANDLE"
        for row in plan["directories"]:
            path=Path(row["before"]["path"]);now=api.capture(path,True)
            assert now["file_id"]==row["before"]["file_id"] and not list(path.iterdir())
            guard(path);path.rmdir();row["status"]="REMOVED_EMPTY_VERIFIED_DIRECTORY"
        for item in plan["protected"]:assert api.capture(Path(item["path"]))==item
        assert seal(final_report)==plan["final_result"]
        plan["status"]="COMPLETE"
    except BaseException as exc:
        plan["status"]="PARTIAL_OR_REVALIDATION_FAILED";plan["error"]={"type":type(exc).__name__,"message":str(exc)}
        raise
    finally:
        api.close(pin)
        removed=[x["before"] for x in plan["files"] if x["status"].startswith("REMOVED")]
        plan["removed_files"]=len(removed);plan["removed_logical_bytes"]=sum(x["bytes"] for x in removed)
        plan["removed_unique_allocation_bytes"]=sum(x["allocation_bytes"] for x in removed)
        plan["remaining_protected_files"]=len(plan["protected"])
        plan["root_inputs_or_retail_accessed"]=False
        output.write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":plan["status"],"cleanup":seal(output),"removed_files":plan["removed_files"],
                      "removed_logical_bytes":plan["removed_logical_bytes"],"removed_unique_allocation_bytes":plan["removed_unique_allocation_bytes"],
                      "retained_current_files":len(plan["protected"])}))

if __name__=="__main__":main()
