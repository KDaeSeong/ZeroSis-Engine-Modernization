"""Independently inspect the final mandatory sidecar; no native image is loaded."""
from file_only_reuse import STAGE, PROJECT, current_builder
import hashlib
import json
from pathlib import Path
import sys


def main():
    current_builder();sys.path.insert(0,str(PROJECT/'tools'))
    import retained_host_runtime_input as retained
    import retained_menu_suite_host_input as menu
    files=retained._Files(check_metadata=True)
    def artifact(path):
        path=Path(path);info=files.ordinary(path)
        return files.verify(dict(path=str(path),bytes=info.st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    sidecar_ref=artifact(STAGE.parent/'host_build/sidecar.json');sidecar=files.json(sidecar_ref)
    identifier='20261101T091435Z_bc34fab66a03'
    assert sidecar['build_id']==identifier and sidecar['status']=='PASS_62_IMMUTABLE_FRONTEND_SIDECAR_HARDLINKS_FILE_ONLY'
    assert sidecar['build_report']['sha256']=='cd167cb92abb1dc02b53893c87123c741f8a27bbf11434dbaf2f8d20cb9e3404'
    build=files.json(sidecar['build_report']);image=files.verify(build['executable'])
    assert image['bytes']==7252992 and image['sha256']=='dd93b7f1c758d9e7a071005f16b5a6d3669e62f8cd77e1c002a4dc82dfaaef89'
    manifest=files.json(sidecar['manifest']);files.verify(sidecar['producer'])
    assert manifest['schema']=='zerosis.original_frontend.assets.v1' and manifest['native_execution'] is False and manifest['sdk_loaded'] is False
    source=PROJECT/'Source/Assets/UIFrontEnd';target=PROJECT/'Build/UiWindowHost'/identifier/'final/UIFrontEnd'
    assert Path(sidecar['source_root'])==source and Path(sidecar['target_root'])==target
    assert len(manifest['files'])==len(sidecar['links'])==sidecar['hardlinked_files']==62
    expected=menu.rows(manifest['files']);seen=set();target_ids=set();source_ids=set();rows=[]
    for link in sidecar['links']:
        old,src,dst=link['source_before'],link['source'],link['sidecar']
        assert Path(src['path']).is_relative_to(source) and Path(dst['path'])==target/Path(src['path']).relative_to(source)
        key=menu.key(src['path']);assert key in expected and key not in seen;seen.add(key)
        assert menu.same(src,expected[key]) and all(old[k]==src[k] for k in ('path','bytes','sha256','file_identity','mtime_ns'))
        assert old['file_attributes']|1==src['file_attributes'] and src['file_attributes']&1
        actual_src,actual_dst=files.verify(src),files.verify(dst)
        actual_src['links']=files.ordinary(src['path']).st_nlink
        actual_dst['links']=files.ordinary(dst['path']).st_nlink
        assert actual_src['file_identity']==actual_dst['file_identity']==src['file_identity']==dst['file_identity']
        assert actual_src['sha256']==actual_dst['sha256'] and actual_src['links']==actual_dst['links'] and actual_src['links']>=old['links']+1
        source_ids.add(tuple(actual_src['file_identity']));target_ids.add(tuple(actual_dst['file_identity']))
        rows.append(dict(source=actual_src,sidecar=actual_dst))
    actual={menu.key(f) for f in target.rglob('*') if f.is_file()}
    assert actual=={menu.key(row['sidecar']['path']) for row in rows} and seen==set(expected)
    assert not target_ids-source_ids and sidecar['additional_unique_payload_bytes']==0
    assert sidecar['source_generated_pack_sealed_readonly'] is True and sidecar['game_cache_or_user_original_attributes_changed'] is False
    assert sidecar['host_or_sdk_or_window_executed'] is False
    files.finish()
    result=dict(schema='zerosis.original_menu.frontend_sidecar.independent.v1',status='PASS_FINAL_62_SIDECAR_BYTES_IDENTITIES_AND_EXE_FILE_ONLY',
        build_id=identifier,build_result=sidecar['build_report'],executable=image,sidecar_report=sidecar_ref,source_manifest=sidecar['manifest'],
        files=rows,hardlinked_files=62,unique_source_file_ids=len(source_ids),additional_unique_payload_bytes=0,
        generated_pack_readonly_only=True,native_image_loaded_or_executed=False,host_sdk_clr_hwnd_gpu_or_game_executed=False,
        registered=False,prepared_runtime_transport_integrated=False)
    output=STAGE/identifier/'sidecar_independent_attestation.json'
    if output.exists():raise RuntimeError('Sidecar attestation is single-use')
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],hardlinks=62,additional_unique_payload_bytes=0,attestation=artifact(output))))


if __name__=='__main__':main()
