"""Seal a fresh plan for one superseded build root. This tool never deletes."""
from file_only_reuse import STAGE, PROJECT, current_builder
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    current_builder();sys.path.insert(0,str(PROJECT/'tools'))
    import build_menu_suite_host as builder
    import retained_menu_suite_host_input as menu
    from menu_suite_storage import storage
    mid='20261101T090433Z_2281c299c25f';final='20261101T091435Z_bc34fab66a03'
    root=PROJECT/'Build/UiWindowHost'/mid
    assert root.resolve(strict=True)==root and root.parent==PROJECT/'Build/UiWindowHost'
    mid_report=PROJECT/'evidence/ui_window_host'/mid/'build_result.json'
    mid_raw=mid_report.read_bytes();mid_sha=hashlib.sha256(mid_raw).hexdigest()
    assert mid_sha.startswith('69b0d9')
    build=json.loads(mid_raw);assert build['build_id']==mid and build['status']=='UI_WINDOW_HOST_CANDIDATE_BUILT'
    assert all(build[name] is False for name in menu.OFFLINE_FIELDS)
    final_report=PROJECT/'evidence/ui_window_host'/final/'build_result.json'
    assert storage.digest(final_report)=='cd167cb92abb1dc02b53893c87123c741f8a27bbf11434dbaf2f8d20cb9e3404'
    current=json.loads(final_report.read_text())
    assert Path(current['baseline_build']['path'])==PROJECT/'evidence/ui_window_host/20261101T074006Z_c2fd2fe9be38/build_result.json'
    assert current['baseline_build']['sha256']=='6077a003f247a82df3e5fe6cfa56671df2750ae0bb0fec9710f71df659439ba7'
    final_att_path=STAGE/final/'independent_attestation.json';final_att=json.loads(final_att_path.read_text())
    assert final_att['status']=='PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS'
    assert final_att['build_result']['sha256']==storage.digest(final_report)
    sidecar_path=STAGE/final/'sidecar_independent_attestation.json';sidecar=json.loads(sidecar_path.read_text())
    assert sidecar['status']=='PASS_FINAL_62_SIDECAR_BYTES_IDENTITIES_AND_EXE_FILE_ONLY' and sidecar['build_id']==final
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,dict):
            for item in value.values():yield from strings(item)
        elif isinstance(value,list):
            for item in value:yield from strings(item)
    prefix=str(root).replace('\\','/').casefold()
    assert not any(prefix in s.replace('\\','/').casefold() for s in strings(current))
    assert not any(prefix in s.replace('\\','/').casefold() for s in strings(sidecar))
    protected={menu.key(r['path']) for r in current['protected_artifacts']}
    assert not any(Path(r['path']).is_relative_to(root) for r in current['protected_artifacts'])
    frozen=menu.frozen_rows(build);known={menu.key(r['path']):r for v in build.values() for r in menu.walk(v)}
    object_paths={menu.key(u['object']['path']) for u in build['final_compilation']['translation_units']}
    image_path=menu.key(build['executable']['path']);env_path=menu.key(root/'read_build_environment.cmd')
    export_paths={menu.key(root/'final/ZeroSisHost_x64.exp'),menu.key(root/'final/ZeroSisHost_x64.lib')}
    link_log=Path(build['link_log']['path']).read_text(encoding='mbcs')
    assert all(name in link_log for name in ('ZeroSisHost_x64.lib','ZeroSisHost_x64.exp'))
    parser,_,_=builder.load_helpers()
    files=[];directories=[];groups=defaultdict(list);keepers={}
    for path in (root,*sorted(root.rglob('*'))):
        info=path.lstat()
        if path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:raise RuntimeError('Reparse retirement candidate rejected')
        assert path.resolve(strict=True)==path and (path==root or path.is_relative_to(root))
        for ancestor in path.parents:
            if getattr(ancestor.lstat(),'st_file_attributes',0)&0x400:raise RuntimeError('Nonordinary retirement ancestor')
        if path.is_dir():directories.append(dict(path=str(path),**storage.metadata(info)));continue
        info=storage.ordinary(path);key=menu.key(path);sha=storage.digest(path)
        if key in frozen:
            expected=frozen[key];assert (info.st_size,sha)==(expected['bytes'],expected['sha256'])
            if expected['materialization']=='attested_snapshot_hardlink':
                donor=Path(expected['reused_from_path']);assert not donor.is_relative_to(root)
                keep=storage.ordinary(donor)
                assert storage.digest(donor)==sha and (keep.st_dev,keep.st_ino)==(info.st_dev,info.st_ino)
                role='FROZEN_SHARED_INPUT_ALIAS_EXTERNAL_DONOR_PRESERVED'
                keepers[menu.key(donor)]=dict(path=str(donor),sha256=sha,**storage.metadata(keep))
            else:
                assert expected['materialization'] in ('owned_changed_source_copy','owned_added_source_copy')
                origin=Path(expected['origin']);assert not origin.is_relative_to(root) and origin.is_file()
                role='SUPERSEDED_BUILD_ONLY_PRIVATE_FROZEN_COPY'
        elif key==image_path:role='SUPERSEDED_UNEXECUTED_HOST_IMAGE'
        elif key in object_paths:role='SUPERSEDED_COFF_OBJECT'
        elif key==env_path:role='BUILD_ENVIRONMENT_SCRIPT'
        elif key in export_paths:
            raw=path.read_bytes()
            if path.suffix=='.exp':assert parser.coff(raw)['machine_hex']=='0x8664'
            else:assert raw.startswith(b'!<arch>\n') and b'ZeroSisHost_x64.exe' in raw
            role='EXACT_LINKER_LOG_DECLARED_DERIVED_EXPORT_OUTPUT'
        elif key in known:role='HASH_ATTESTED_BUILD_RECIPE_OR_OUTPUT'
        else:raise RuntimeError('Unknown intermediate file role: '+str(path))
        if key in known:assert (info.st_size,sha)==(known[key]['bytes'],known[key]['sha256'])
        row=dict(path=str(path),sha256=sha,role=role,allocated_bytes=storage.allocated(path),**storage.metadata(info))
        files.append(row);groups[tuple(row['file_identity'])].append(row)
    released=retained_alloc=0
    for rows in groups.values():
        links={r['links'] for r in rows};assert len(links)==1 and next(iter(links))>=len(rows)
        alloc=rows[0]['allocated_bytes']
        if next(iter(links))==len(rows):released+=alloc
        else:
            retained_alloc+=alloc
            assert any(tuple(r['file_identity']) in {tuple(k['file_identity']) for k in keepers.values()} for r in rows)
    archives=[]
    run_path=Path(build['started']['path']).with_name('run.json');run=json.loads(run_path.read_text())
    for path in (mid_report,run_path,Path(run['reviewed_preflight']['path'])):
        assert path.is_relative_to(PROJECT/'evidence') and final not in str(path) and not path.is_relative_to(root)
        archives.append(dict(path=str(path),sha256=storage.digest(path),**storage.metadata(storage.ordinary(path))))
    plan=dict(schema='zerosis.original_menu.superseded_root_retirement_plan.v1',status='SEALED_PLAN_ONLY_NOT_EXECUTED',
        build_id=mid,exact_root=str(root),intermediate_report=builder.common.artifact(mid_report),
        retained_final_report=builder.common.artifact(final_report),final_independent_attestation=builder.common.artifact(final_att_path),
        final_sidecar_attestation=builder.common.artifact(sidecar_path),files=files,directories=directories,
        external_hardlink_keepers=list(keepers.values()),protected_path_count=len(protected),protected_paths_overlap=0,
        file_count=len(files),directory_count=len(directories),logical_bytes=sum(r['bytes'] for r in files),
        unique_file_ids=len(groups),unique_allocated_bytes=sum(rows[0]['allocated_bytes'] for rows in groups.values()),
        estimated_allocated_bytes_released=released,shared_allocation_preserved_outside_root=retained_alloc,
        optional_intermediate_text_archive_candidates=archives,current_final_reports_archived_or_deleted=False,
        historical_only=True,root_separate_action_required=True,final_six_typed_retirement_separate=True,
        deletion_executed=False,Host_SDK_CLR_HWND_GPU_game_executed=False,profile_registered=False,
        preserved_baseline='20261101T074006Z_c2fd2fe9be38',preserved_prepared='20261101T080450Z_424fb64608b2')
    output=STAGE/mid/'whole_root_cleanup_plan.json';output.parent.mkdir(exist_ok=True)
    if output.exists():raise RuntimeError('Inspect an existing single-use retirement plan')
    output.write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=plan['status'],files=len(files),directories=len(directories),logical_bytes=plan['logical_bytes'],
        estimated_allocated_bytes_released=released,external_hardlink_keepers=len(keepers),plan=builder.common.artifact(output))))


if __name__=='__main__':main()
