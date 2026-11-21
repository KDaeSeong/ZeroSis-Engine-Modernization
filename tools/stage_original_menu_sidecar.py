"""Hardlink one exact generated frontend manifest beside an offline Host."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import stat

import build_menu_suite_host as build
import retained_menu_suite_host_input as menu
from retained_host_runtime_input import _Files


def main(argv=None):
    cli=argparse.ArgumentParser()
    cli.add_argument('--build-report',type=Path,required=True)
    cli.add_argument('--report-sha256',required=True)
    cli.add_argument('--asset-manifest',type=Path)
    cli.add_argument('--asset-manifest-sha256')
    cli.add_argument('--source-root',type=Path)
    cli.add_argument('--output',type=Path)
    args=cli.parse_args(argv);P=build.PROJECT
    custom=any(value is not None for value in (args.asset_manifest,args.asset_manifest_sha256,args.source_root))
    if custom and not all(value is not None for value in (args.asset_manifest,args.asset_manifest_sha256,args.source_root)):
        cli.error('--asset-manifest, --asset-manifest-sha256 and --source-root are required together')
    ref=build.common.pin(args.build_report,args.report_sha256)
    report=json.loads(Path(ref['path']).read_bytes());identifier=report['build_id']
    assert re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',identifier)
    root=P/'Build/UiWindowHost'/identifier
    assert args.build_report.absolute()==P/'evidence/ui_window_host'/identifier/'build_result.json'
    assert report['status']=='UI_WINDOW_HOST_CANDIDATE_BUILT' and all(report[name] is False for name in menu.OFFLINE_FIELDS)
    image=build.common.sealed(report['executable']);assert Path(image['path'])==root/'final/ZeroSisHost_x64.exe'
    manifest_path=args.asset_manifest.absolute() if custom else P/'evidence/game_menu/original_menu_followup/frontend/assets.json'
    manifest_ref=build.common.pin(manifest_path,args.asset_manifest_sha256) if custom else build.common.artifact(manifest_path)
    source=args.source_root.absolute() if custom else P/'Source/Assets/UIFrontEnd'
    manifest=json.loads(manifest_path.read_bytes());target=root/'final/UIFrontEnd'
    out=args.output.absolute() if args.output else P/'evidence/game_menu/original_menu_followup/host_build/sidecar.json'
    assert out.is_relative_to(P/'evidence') and '..' not in out.parts and not os.path.lexists(out)
    assert not os.path.lexists(target)
    before_files=_Files(check_metadata=True)
    source_proof=menu.sidecar_source_inventory(P,source,manifest_ref,manifest['schema'],before_files,require_readonly=custom)
    if not custom:assert source_proof['file_count']==62 and manifest['schema']=='zerosis.original_frontend.assets.v1'
    before_files.finish();target.mkdir();links=[]
    for row in source_proof['files']:
        relative=menu.sidecar_relative_path(row['relative_path']);p=source/relative;q=target/relative
        q.parent.mkdir(parents=True,exist_ok=True);before=build.common.artifact(p)
        if not before['file_attributes']&1:
            # Historical default only: seal a private generated member. Custom
            # manifests must already be immutable; never chmod a shared donor.
            assert not custom and before['links']==1
            os.chmod(p,stat.S_IREAD)
        os.link(p,q)
        current,alias=build.common.artifact(p),build.common.artifact(q)
        assert current['file_identity']==alias['file_identity'] and current['sha256']==alias['sha256']==row['source']['sha256']
        assert current['bytes']==alias['bytes']==row['source']['bytes'] and current['file_attributes']&1 and current['links']==before['links']+1
        links.append(dict(source_before=before,source=current,sidecar=alias))
    descriptor=dict(schema='zerosis.retained_menu_host.required_sidecar.v1',relative_root='UIFrontEnd',
        source_root=str(source),frozen_root=str(target),manifest=manifest_ref,manifest_schema=manifest['schema'],
        file_count=len(links),files=[dict(relative_path=Path(row['source']['path']).relative_to(source).as_posix(),
            source=row['source'],frozen=row['sidecar']) for row in links])
    validation=menu.validate_required_sidecars(P,identifier,descriptor,_Files(check_metadata=True))
    assert build.common.sealed(report['executable'])['sha256']==image['sha256']
    result=dict(status=('PASS_IMMUTABLE_FRONTEND_SIDECAR_HARDLINKS_FILE_ONLY' if custom else 'PASS_62_IMMUTABLE_FRONTEND_SIDECAR_HARDLINKS_FILE_ONLY'),
        producer=build.common.artifact(Path(__file__).absolute()),build_id=identifier,build_report=ref,manifest=manifest_ref,
        source_root=str(source),target_root=str(target),links=links,hardlinked_files=len(links),additional_unique_payload_bytes=0,
        required_sidecar=descriptor,sidecar_validation=validation,source_generated_pack_sealed_readonly=True,
        game_cache_or_user_original_attributes_changed=False,host_or_sdk_or_window_executed=False)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status='PASS',hardlinked_files=len(links),additional_unique_payload_bytes=0,receipt=str(out))))


if __name__=='__main__':main()
