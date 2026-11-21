"""Independent runtime-only allocation/retention audit; no project-wide scan."""
from datetime import datetime,timezone
from pathlib import Path
import argparse,gzip,hashlib,json,os,stat,sys
from collections import Counter
sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
import audit_exit_host_storage as allocation

RUNTIME=PROJECT/'Build/InteractiveGameRuntime'
PROTECTED=('20261115T134603Z_aa8853762399','20261115T101941Z_99b3c393ee9a',
    '20261115T011241Z_4c8fd55e99db','20261108T003146Z_40a8030edf08')
EXPECTED_HOST='c3bb5ffc2e57630d28a8305f288b501352c03f0e1970b1dc5b321d6ba0683383'
EXPECTED_SDK='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
EXPECTED_SCREEN='f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0'

def write_new(name,value):
    path=STAGE/name
    assert path.parent==STAGE and path.name.startswith('storage_') and not path.exists()
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return record(path,True)

def read(path):return json.loads(Path(path).read_text('utf-8-sig'))

def signature(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_file_attributes)

def record(path,hashed=False,cache=None):
    path=Path(path).absolute()
    before=os.stat(path,follow_symlinks=False)
    assert stat.S_ISREG(before.st_mode) and before.st_dev and before.st_ino
    assert not before.st_file_attributes&0x400 and path.resolve()==path
    row=dict(path=str(path),bytes=before.st_size,file_identity=[before.st_dev,before.st_ino],
        mtime_ns=before.st_mtime_ns,file_attributes=before.st_file_attributes,links=before.st_nlink,
        allocated_bytes=allocation.allocated(path))
    if hashed:
        key=signature(before)
        if cache is not None and key in cache:row['sha256']=cache[key]
        else:
            with path.open('rb') as stream:row['sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
            if cache is not None:cache[key]=row['sha256']
    assert signature(os.stat(path,follow_symlinks=False))==signature(before),str(path)
    return row

def scan(root,hashed=False,cache=None):
    rows=[]
    for directory,names,leaves in os.walk(root,followlinks=False):
        assert not os.stat(directory,follow_symlinks=False).st_file_attributes&0x400
        for name in names:assert not os.stat(Path(directory)/name,follow_symlinks=False).st_file_attributes&0x400
        for name in leaves:rows.append(record(Path(directory)/name,hashed,cache))
    return rows

def identity(row):return tuple(row['file_identity'])

def summary(rows):
    unique={identity(row):row for row in rows}
    counts=Counter(identity(row) for row in rows)
    return dict(paths=len(rows),unique_file_identities=len(unique),logical_path_bytes=sum(row['bytes']for row in rows),
        unique_logical_bytes=sum(row['bytes']for row in unique.values()),
        unique_allocated_bytes=sum(row['allocated_bytes']for row in unique.values()),
        allocation_private_to_root=sum(row['allocated_bytes']for key,row in unique.items() if row['links']==counts[key]),
        allocation_shared_outside_root=sum(row['allocated_bytes']for key,row in unique.items() if row['links']>counts[key]))

def startup():
    assert not (STAGE/'storage_startup.json').exists()
    previous=read(PROJECT/'evidence/world_terrain_original/phase10/current_work.json')
    assert previous['current_host']['build_id']=='20261116T114748Z_014dd63ad3bc'
    assert not previous['storage']['after_pending'] and not previous['protection']['after_pending']
    cache={};protected=[];groups=[];all_rows=[]
    for root in sorted(RUNTIME.iterdir()):
        if not root.is_dir():continue
        rows=scan(root,root.name in PROTECTED,cache)
        sessions=root/'sessions'
        session_rows=[row for row in rows if Path(row['path']).is_relative_to(sessions)]
        role=('latest_prepared' if root.name==PROTECTED[0] else 'previous_prepared' if root.name==PROTECTED[1]
            else 'recovery' if root.name==PROTECTED[2] else 'user_native_session' if root.name==PROTECTED[3]
            else 'empty_retired_shell' if not rows else 'unclassified_retained_candidate_only')
        groups.append(dict(root=str(root),role=role,summary=summary(rows),sessions=summary(session_rows),
            session_directories=[p.name for p in sorted(sessions.iterdir()) if p.is_dir()] if sessions.exists() else [],
            deletion_authorized_by_this_audit=False))
        all_rows.extend(rows)
        if root.name in PROTECTED:protected.extend(rows)
    assert all(any(Path(row['path']).is_relative_to(RUNTIME/name) for row in protected) for name in PROTECTED)
    snapshot=dict(status='PROTECTED_RUNTIME_STORAGE_BASELINE',protected_roots=list(PROTECTED),files=protected)
    data=(json.dumps(snapshot,indent=2)+'\n').encode()
    path=STAGE/'storage_protected_before.json.gz';assert not path.exists();path.write_bytes(gzip.compress(data,mtime=0))
    assert gzip.decompress(path.read_bytes())==data
    cleanup=read(PROJECT/'evidence/world_terrain_original/phase10/cleanup_summary.json')
    own_leftovers=[str(p) for p in (PROJECT/'evidence/world_terrain_original/phase10').rglob('*')
        if p.is_file() and p.suffix in ('.obj','.exe','.cso','.hlsl','.tmp','.dxbc')]
    assert not own_leftovers,own_leftovers
    total=summary(all_rows)
    value=dict(status='PASS_RUNTIME_ONLY_STARTUP_RETENTION_AND_DISPOSABLE_REVIEW',utc=datetime.now(timezone.utc).isoformat(),
        scope='Only Build/InteractiveGameRuntime roots; no whole-project allocation scan.',
        protected_snapshot=record(path,True),groups=groups,total=total,
        previous_phase10_cleanup=record(PROJECT/'evidence/world_terrain_original/phase10/cleanup_summary.json',True),
        previous_phase10_cleanup_status=cleanup['status'],own_phase10_regenerable_work_leftovers=own_leftovers,
        confirmed_disposable_bytes=0,disposable_threshold_bytes=10*1024**3,
        unknown_old_roles_not_deleted=True,new_core_budget_bytes=64*1024**2,
        new_budget_note='Include any new readonly Host cache identity, not just private runtime databases. Direct existing-asset links allocate no new payload.',
        file_identity_source='os.stat(path,follow_symlinks=False); never DirEntry.stat',
        source_runtime_or_old_artifacts_modified=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    result=write_new('storage_startup.json',value)
    print(json.dumps(dict(status=value['status'],runtime_directories=len(groups),
        nonempty=sum(row['summary']['paths']>0 for row in groups),protected_paths=len(protected),
        unique_runtime_allocated_bytes=total['unique_allocated_bytes'],confirmed_disposable_bytes=0,receipt=result['path'])))

def verify_protected():
    old=json.loads(gzip.decompress((STAGE/'storage_protected_before.json.gz').read_bytes()))
    bad=[];aliases=0;cache={}
    for row in old['files']:
        now=record(row['path'],True,cache)
        if any(row[key]!=now[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes')):bad.append(row['path'])
        aliases+=row['links']!=now['links']
    return dict(paths=len(old['files']),differences=bad,alias_only_changes=aliases)

def verify(run_id):
    import re
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',run_id)
    root=RUNTIME/run_id;assert root.is_dir() and run_id not in PROTECTED
    assert not (root/'sessions').exists()
    rows=scan(root,True,{})
    by_name={str(Path(row['path']).relative_to(root)).replace('\\','/'):row for row in rows}
    assert by_name['ZeroSisHost_x64.exe']['sha256']==EXPECTED_HOST
    assert by_name['CvGameCoreDLL_Expansion2_x64.dll']['sha256']==EXPECTED_SDK
    screen=by_name['WorldAssets/screen-light-assets.bin']
    original=read(PROJECT/'evidence/world_terrain_original/phase10/current_work.json')['packages']['screen_light']
    source=record(original['path'],True)
    assert screen['sha256']==source['sha256']==EXPECTED_SCREEN
    assert screen['file_identity']==source['file_identity'] and screen['file_attributes']==source['file_attributes']==32
    protected=verify_protected();assert not protected['differences']
    baseline=json.loads(gzip.decompress((STAGE/'storage_protected_before.json.gz').read_bytes()))
    old_ids={identity(row) for row in baseline['files']}
    existing_packages=read(PROJECT/'evidence/world_terrain_original/phase10/current_work.json')['packages']
    old_ids.update(tuple(row['file_identity']) for row in existing_packages.values())
    # New Host's immutable cache alias may lie outside this runtime root. Its
    # allocation is still charged once when its identity is new to the baseline.
    unique={identity(row):row for row in rows}
    newly_charged=[row for key,row in unique.items() if key not in old_ids]
    charged=sum(row['allocated_bytes'] for row in newly_charged)
    assert charged<=64*1024**2,(charged,64*1024**2)
    database_rows=[row for row in rows if Path(row['path']).suffix.lower() in ('.db','.sqlite','.sqlite3')]
    assert len(database_rows)==2,len(database_rows)
    for row in database_rows:
        assert row['links']==1 and identity(row) not in old_ids
        assert not row['file_attributes']&1
    gr2_config=[row for row in rows if Path(row['path']).suffix.lower() in ('.gr2','.ini','.config')]
    for row in gr2_config:assert row['links']==1 and identity(row) not in old_ids
    support=[row for name,row in by_name.items() if name.startswith('interactive_ui_support/') and name!='interactive_ui_support/support_manifest.json']
    assert len(support)==8
    support_manifest=by_name['interactive_ui_support/support_manifest.json']
    assert support_manifest['links']==1 and identity(support_manifest) not in old_ids
    donor=RUNTIME/PROTECTED[0]
    for row in support:
        relative=Path(row['path']).relative_to(root);before=record(donor/relative,True)
        assert row['file_identity']==before['file_identity'] and row['sha256']==before['sha256']
        assert row['file_attributes']==before['file_attributes']==32
    package_paths={'terrain':'terrain-assets.bin','fog':'WorldAssets/fog-assets.bin',
        'water':'WorldAssets/water-assets.bin','lean':'WorldAssets/water-lean-assets.bin',
        'lighting':'WorldAssets/lighting-assets.bin','screen_light':'WorldAssets/screen-light-assets.bin'}
    package_links={}
    for role,relative in package_paths.items():
        original=record(existing_packages[role]['path'],True)
        target=by_name[relative]
        assert all(original[key]==target[key] for key in ('sha256','file_identity','bytes','mtime_ns','file_attributes'))
        assert target['file_attributes']==32
        package_links[role]=dict(source=original,target=target,new_payload_allocation=0)
    value=dict(status='PASS_NEW_RUNTIME_BUDGET_PRIVACY_RETENTION_AND_PROTECTION',run_id=run_id,
        runtime_directory=str(root),runtime_summary=summary(rows),newly_charged_files=newly_charged,
        core_new_identity_allocated_bytes=charged,core_budget_bytes=64*1024**2,
        budget_headroom_bytes=64*1024**2-charged,databases_private=database_rows,gr2_and_config_private=gr2_config,
        support_directly_shared_files=len(support),private_support_manifest=support_manifest,
        package_direct_links=package_links,six_packs_new_payload_copies=0,screen_original_source=source,
        protected_before_after=protected,new_game_only=True,
        original_or_user_or_old_runtime_modified=False,native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False)
    result=write_new('storage_final_review.json',value)
    print(json.dumps(dict(status=value['status'],run_id=run_id,core_allocated_bytes=charged,
        headroom_bytes=value['budget_headroom_bytes'],protected_paths=protected['paths'],receipt=result['path'])))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=('startup','verify'));parser.add_argument('--run-id');args=parser.parse_args()
    if args.operation=='startup':startup()
    else:assert args.run_id;verify(args.run_id)
