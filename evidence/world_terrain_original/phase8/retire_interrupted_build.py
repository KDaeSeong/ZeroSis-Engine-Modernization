"""Retire this turn's unreferenced interrupted build after its replacement seals."""
from pathlib import Path
import argparse, gzip, hashlib, importlib.util, json, os, sys
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common
from menu_suite_storage import storage
OLD='20261115T115920Z_a4b5d1514cc1'
NEW='20261115T121456Z_dbb01a1f4f50'
ROOT=PROJECT/'Build/UiWindowHost'/OLD
DIRECTORY=STAGE/'interrupted_cleanup'
HELPER=PROJECT/'tools/prune_superseded_runtime_artifacts.py'
HELPER_SHA='e7dc5a356deba20add2482c4109f5e78775b48480c5ea81e483289e97f3b3678'

def write_new(path,value):
    with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2);f.write('\n')

def check_root():
    assert ROOT.resolve()==(PROJECT/'Build/UiWindowHost'/OLD).absolute()
    assert ROOT.parent.resolve()==(PROJECT/'Build/UiWindowHost').resolve()
    assert not ROOT.stat().st_file_attributes&0x400

def replacement():
    report=PROJECT/'evidence/ui_window_host'/NEW/'build_result.json'
    profile=STAGE/'pair_preparation'/NEW/'prepared_profile.json'
    data=json.loads(profile.read_text('utf8'))
    assert not data['native_execution']and not data['globally_registered']
    proofs=[report,profile,STAGE/'host_build_retry01/attempts/dbb01a1f4f508ec9e674/run.json']
    assert all(OLD.encode()not in path.read_bytes()for path in proofs)
    return [common.artifact(path)for path in proofs]

def plan():
    assert not DIRECTORY.exists();DIRECTORY.mkdir();check_root();protected=replacement()
    records=[];directories=[]
    for directory,names,leaves in os.walk(ROOT,followlinks=False):
        path=Path(directory);assert path.resolve().is_relative_to(ROOT.resolve())and not path.stat().st_file_attributes&0x400
        directories.append(str(path))
        for name in names:assert not(Path(directory)/name).stat().st_file_attributes&0x400
        for name in leaves:
            path=Path(directory)/name;assert path.suffix.lower()not in('.civ5save','.zssave','.zssettings')and 'sessions'not in path.relative_to(ROOT).parts
            row=common.artifact(path);assert not row['file_attributes']&0x400
            row['allocated_bytes']=storage.allocated(path);records.append(row)
    ids={}
    for row in records:
        info=ids.setdefault(tuple(row['file_identity']),dict(rows=0,links=row['links'],allocation=row['allocated_bytes']))
        assert info['links']==row['links']and info['allocation']==row['allocated_bytes'];info['rows']+=1
    released=sum(info['allocation']for info in ids.values()if info['rows']==info['links'])
    document=dict(status='REVIEWABLE_EXACT_INTERRUPTED_BUILD_RETIREMENT',root=str(ROOT),replacement=protected,files=records,
        directories=directories,logical_bytes=sum(row['bytes']for row in records),unique_files=len(ids),expected_released_bytes=released,
        unique_source_or_user_saves_deleted=False,reason='Fresh replacement has actual12 command records, independent attestation and sealed profile; interrupted build has no live donor/runtime reference. Preserve its logs, staticPE, interruption receipt and this compressed metadata ledger.')
    path=DIRECTORY/'plan.json.gz';path.write_bytes(gzip.compress((json.dumps(document,indent=2)+'\n').encode(),mtime=0))
    print(json.dumps(dict(status=document['status'],files=len(records),logical_bytes=document['logical_bytes'],expected_released_bytes=released,plan_sha256=common.artifact(path)['sha256'])))

def apply(digest):
    path=DIRECTORY/'plan.json.gz';assert common.artifact(path)['sha256']==digest
    data=json.loads(gzip.decompress(path.read_bytes()));assert data['root']==str(ROOT);check_root()
    for row in data['replacement']:assert common.artifact(row['path'])==row
    assert common.artifact(HELPER)['sha256']==HELPER_SHA
    spec=importlib.util.spec_from_file_location('bounded_disposition_helper',HELPER);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert not(DIRECTORY/'started.json').exists();write_new(DIRECTORY/'started.json',dict(plan_sha256=digest,root=str(ROOT),apply_count=1))
    removed={};count=0
    for row in data['files']:
        leaf=Path(row['path']);assert leaf.resolve().is_relative_to(ROOT.resolve())
        now=common.artifact(leaf);identity=tuple(row['file_identity'])
        assert all(now[k]==row[k]for k in('bytes','sha256','file_identity','mtime_ns','file_attributes'))
        assert now['links']==row['links']-removed.get(identity,0)
        module.unlink_without_attribute_changes(leaf);assert not os.path.lexists(leaf)
        removed[identity]=removed.get(identity,0)+1;count+=1
    for directory in sorted(map(Path,data['directories']),key=lambda value:len(value.parts),reverse=True):
        assert directory.resolve().is_relative_to(ROOT.parent.resolve())and not any(directory.iterdir());directory.rmdir()
    assert not ROOT.exists()
    for row in data['replacement']:assert common.artifact(row['path'])==row
    result=dict(status='PASS_INTERRUPTED_BUILD_RETIRED_AFTER_SEALED_REPLACEMENT',plan=common.artifact(path),files_deleted=count,
        logical_bytes_removed=data['logical_bytes'],released_unique_allocated_bytes=data['expected_released_bytes'],
        replaced_by=NEW,old_payload_retained=False,logs_and_metadata_retained=True,shared_donor_attributes_not_changed=True,
        host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    write_new(DIRECTORY/'result.json',result);print(json.dumps(result))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['plan','apply']);parser.add_argument('--sha256');args=parser.parse_args()
    if args.action=='plan':plan()
    else:apply(args.sha256)
