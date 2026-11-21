"""Apply only the root-reviewed exact plan and its complete protection supplement."""
from file_only_reuse import PROJECT, STAGE, current_builder
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    current_builder();sys.path.insert(0,str(PROJECT/'tools'))
    from menu_suite_storage import storage
    from civ5_ui_assets import _unlink_font_target_without_attribute_changes as unlink
    import retained_host_runtime_input as retained
    import retained_menu_suite_host_input as menu
    mid='20261101T090433Z_2281c299c25f';final='20261101T091435Z_bc34fab66a03';directory=STAGE/mid
    planpath=directory/'whole_root_cleanup_plan.json';suppath=directory/'protection_supplement.json'
    assert storage.digest(planpath)=='a786cab4321f9c8cf719da80b250e0cc6fc2db0c959dcc3f0aabfeb20be82516'
    assert storage.digest(suppath)=='a7358b79265731f4336e5571cd5a2cce0d76655cd9a812567a25a32a2d6dde4c'
    plan=json.loads(planpath.read_text());supp=json.loads(suppath.read_text());root=Path(plan['exact_root'])
    assert root==PROJECT/'Build/UiWindowHost'/mid and root.is_relative_to(PROJECT/'Build/UiWindowHost')
    assert plan['file_count']==687 and plan['directory_count']==87 and len(plan['external_hardlink_keepers'])==616
    assert supp['authoritative_baseline_paths_checked']==3270 and supp['protected_path_overlap']==[]
    baseline_ref=supp['authoritative_turn_baseline'];assert storage.digest(baseline_ref['path'])==baseline_ref['sha256']
    baseline=json.loads(Path(baseline_ref['path']).read_text());assert len(baseline['protected_artifacts'])==3270
    assert sys.argv[1:] in ([],['--resume'])
    resume=sys.argv[1:]==['--resume'];prior_deleted=[]
    partialpath=directory/'whole_root_cleanup_partial_failure.json'
    if resume:
        partial=json.loads(partialpath.read_text());prior_deleted=partial['deleted']
        assert len(prior_deleted)==30 and len(set(prior_deleted))==30 and not partial['removed_directories'] and not partial['text_archives']
        assert set(prior_deleted)<={r['path'] for r in plan['files']} and all(not os.path.lexists(p) for p in prior_deleted)
    def verify(row,links=True):
        f=Path(row['path']);info=storage.ordinary(f);now=storage.metadata(info)
        for ancestor in (f,*f.parents):
            assert not getattr(ancestor.lstat(),'st_file_attributes',0)&0x400
        keys=('bytes','file_identity','mtime_ns','file_attributes')+(('links',) if links else ())
        assert all(now[k]==row[k] for k in keys),str(f)
        assert storage.digest(f)==row['sha256'],str(f)
        return now
    def protected_and_final():
        hashes={}
        for row in baseline['protected_artifacts']:
            f=Path(row['path']);assert not f.is_relative_to(root)
            now=storage.metadata(storage.ordinary(f));identity=tuple(now['file_identity'])
            if identity not in hashes:hashes[identity]=storage.digest(f)
            assert hashes[identity]==row['sha256'] and all(now[k]==row[k] for k in ('bytes','file_identity','mtime_ns','file_attributes'))
        files=retained._Files(check_metadata=True)
        build=files.json(plan['retained_final_report'])
        for row in [*build['current_source_inputs'],*menu.frozen_rows(build).values()]:files.verify(row)
        image=files.verify(build['executable'])
        assert image['sha256']=='dd93b7f1c758d9e7a071005f16b5a6d3669e62f8cd77e1c002a4dc82dfaaef89'
        sidecar=files.json(plan['final_sidecar_attestation']);assert sidecar['hardlinked_files']==62
        for pair in sidecar['files']:
            a,b=files.verify(pair['source']),files.verify(pair['sidecar'])
            assert a['file_identity']==b['file_identity']
        files.finish();return build,image
    build,image=protected_and_final()
    actual_files={str(f) for f in root.rglob('*') if f.is_file()}
    actual_dirs={str(root),*(str(f) for f in root.rglob('*') if f.is_dir())}
    assert actual_files=={r['path'] for r in plan['files']}-set(prior_deleted) and actual_dirs=={r['path'] for r in plan['directories']}
    for row in plan['files']:
        f=Path(row['path']);assert f.is_relative_to(root)
        if row['path'] in prior_deleted:continue
        assert f.resolve(strict=True)==f;verify(row)
    for row in plan['directories']:
        f=Path(row['path']);s=f.lstat();now=storage.metadata(s)
        assert f.is_dir() and not f.is_symlink() and not getattr(s,'st_file_attributes',0)&0x400
        assert now['file_identity']==row['file_identity'] and now['file_attributes']==row['file_attributes']
    prior_counts=Counter(tuple(r['file_identity']) for r in plan['files'] if r['path'] in prior_deleted)
    for row in plan['external_hardlink_keepers']:
        now=verify(row,links=False)
        assert now['links']==row['links']-prior_counts[tuple(row['file_identity'])]
    archive_rows=plan['optional_intermediate_text_archive_candidates'];assert len(archive_rows)==3
    protected_paths={menu.key(r['path']) for r in baseline['protected_artifacts']}
    def strings(v):
        if isinstance(v,str):yield v
        elif isinstance(v,list):
            for x in v:yield from strings(x)
        elif isinstance(v,dict):
            for x in v.values():yield from strings(x)
    for row in archive_rows:
        path=Path(row['path']);assert path.is_relative_to(PROJECT/'evidence') and not path.is_relative_to(root)
        assert menu.key(path) not in protected_paths and final not in str(path) and row['links']==1
        assert not any(str(path).replace('\\','/').casefold() in v.replace('\\','/').casefold() for v in strings(build))
        verify(row)
    started=directory/'whole_root_cleanup_started.json'
    if resume:
        original_started=json.loads(started.read_text());assert original_started['plan_sha256']==storage.digest(planpath) and original_started['supplement_sha256']==storage.digest(suppath)
        started=directory/'whole_root_cleanup_resume_started.json'
    with started.open('x',encoding='utf-8') as f:json.dump(dict(plan_sha256=storage.digest(planpath),supplement_sha256=storage.digest(suppath),previous_deleted_count=len(prior_deleted),remaining_files=len(actual_files),prior_partial_sha256=storage.digest(partialpath) if resume else None),f)
    deleted=list(prior_deleted);removed=[];archived=[]
    try:
        for row in plan['files']:
            if row['path'] in prior_deleted:continue
            verify(row);unlink(Path(row['path']));assert not os.path.lexists(row['path']);deleted.append(row['path'])
        for row in sorted(plan['directories'],key=lambda r:len(Path(r['path']).parts),reverse=True):
            f=Path(row['path']);now=storage.metadata(f.lstat())
            assert now['file_identity']==row['file_identity'] and now['file_attributes']==row['file_attributes'] and not any(f.iterdir())
            f.rmdir();removed.append(str(f))
        assert not os.path.lexists(root)
        counts=Counter(tuple(r['file_identity']) for r in plan['files'])
        for row in plan['external_hardlink_keepers']:
            now=verify(row,links=False);assert now['links']==row['links']-counts[tuple(row['file_identity'])]
        archive_dir=directory/'archived_text';archive_dir.mkdir()
        for role,row in zip(('intermediate_build_report','intermediate_run','intermediate_plan'),archive_rows):
            verify(row);path=Path(row['path']);raw=path.read_bytes();target=archive_dir/(role+'.json.gz')
            packed=gzip.compress(raw,mtime=0)
            with target.open('xb') as f:f.write(packed)
            assert gzip.decompress(target.read_bytes())==raw and hashlib.sha256(raw).hexdigest()==row['sha256']
            verify(row);unlink(path);assert not os.path.lexists(path)
            archived.append(dict(role=role,original=row,archive=dict(path=str(target),bytes=len(packed),sha256=storage.digest(target)),
                restored_raw_sha256=hashlib.sha256(gzip.decompress(packed)).hexdigest(),raw_removed=True))
        _,after_image=protected_and_final();assert menu.same(image,after_image)
        result=dict(schema='zerosis.original_menu.superseded_root_cleanup_result.v1',status='PASS_EXACT_SUPERSEDED_ROOT_AND_TEXT_ARCHIVE_RETIREMENT',
            build_id=mid,exact_root=str(root),plan=dict(path=str(planpath),sha256=storage.digest(planpath)),protection_supplement=dict(path=str(suppath),sha256=storage.digest(suppath)),
            files_deleted=len(deleted),directories_removed=len(removed),all_candidates_absent=True,logical_root_bytes_removed=plan['logical_bytes'],
            unique_root_allocated_bytes_released=plan['estimated_allocated_bytes_released'],shared_external_allocation_preserved=plan['shared_allocation_preserved_outside_root'],
            external_keepers_verified=616,protected_turn_baseline_paths_verified=3270,protected_bytes_identity_mtime_attributes_changed=False,
            final_executable_unchanged=True,final_frozen_and_current_inputs_unchanged=True,final_sidecar62_verified=True,
            baseline_Host4_prepared424fb_default_originals_saves_preserved=True,text_archives=archived,
            raw_intermediate_text_bytes_removed=sum(r['original']['bytes'] for r in archived),gzip_bytes_retained=sum(r['archive']['bytes'] for r in archived),
            current_final_reports_removed=False,original_plan_and_supplement_preserved=True,registered=False,
            resumed_after_permission_error=resume,previously_deleted_paths_not_retried=len(prior_deleted),
            Host_SDK_CLR_HWND_GPU_or_game_executed=False)
        output=directory/'whole_root_cleanup_result.json'
        with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
        print(json.dumps(dict(status=result['status'],files_deleted=687,directories_removed=87,root_logical_bytes_removed=plan['logical_bytes'],
            root_allocated_bytes_released=plan['estimated_allocated_bytes_released'],archives=3,raw_text_bytes_removed=result['raw_intermediate_text_bytes_removed'],
            gzip_bytes_retained=result['gzip_bytes_retained'],result=dict(path=str(output),bytes=output.stat().st_size,sha256=storage.digest(output)))))
    except BaseException as error:
        with (directory/('whole_root_cleanup_resume_partial_failure.json' if resume else 'whole_root_cleanup_partial_failure.json')).open('x',encoding='utf-8') as f:
            json.dump(dict(deleted=deleted,removed_directories=removed,text_archives=archived,error_type=type(error).__name__,error=str(error)),f,indent=2)
        raise


if __name__=='__main__':main()
