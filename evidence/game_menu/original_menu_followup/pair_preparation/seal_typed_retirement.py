"""Publish typed-six historical evidence only; never emit/register a Host profile."""
from file_only_reuse import STAGE, PROJECT, load
import argparse
import json
import os
from pathlib import Path
import re


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--build-id',required=True)
    for name in ('report','attestation','cleanup-plan','cleanup-result'):
        cli.add_argument('--'+name+'-sha256',required=True)
    args=cli.parse_args()
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',args.build_id):raise RuntimeError('Invalid exact build ID')
    if args.build_id in ('20261101T074006Z_c2fd2fe9be38','20261101T090433Z_2281c299c25f'):
        raise RuntimeError('This tool cannot seal a preserved baseline or superseded intermediate')
    helper=load('evidence/game_menu/offline_menu_suite/pair_preparation/finalize_candidate_profile.py',
        '8598668773b61f80f7228c7fa6a0ac4d5933217a5251c0fc6c369d139865cc74','_typed_retirement_only_helpers')
    helper.STAGE=STAGE
    directory=STAGE/args.build_id
    files=helper.retained._Files(check_metadata=True);refs={}
    for name,path,sha in (
        ('report',PROJECT/'evidence/ui_window_host'/args.build_id/'build_result.json',args.report_sha256),
        ('attestation',directory/'independent_attestation.json',args.attestation_sha256),
        ('cleanup_plan',directory/'cleanup_plan.json',args.cleanup_plan_sha256),
        ('cleanup_result',directory/'cleanup_result.json',args.cleanup_result_sha256)):
        if not re.fullmatch('[0-9a-f]{64}',sha):raise RuntimeError('Every exact proof needs a SHA256 pin')
        refs[name]=files.verify(dict(path=str(path),sha256=sha))
    build,att,plan,result=(files.json(refs[n]) for n in ('report','attestation','cleanup_plan','cleanup_result'))
    if build['build_id']!=args.build_id or not helper.menu.same(att['build_result'],refs['report']):
        raise RuntimeError('Attestation/report identity differs')
    if not (att['status']=='PASS_INDEPENDENT_CURRENT_MENU_SUITE_HOST_BYTES_AND_INPUTS' and
            helper.menu.same(att['image'],build['executable']) and result['build_id']==args.build_id and
            result['files_deleted']==6 and result['all_candidates_absent'] is True and
            result['current_image_unchanged'] is True and result['plan_sha256']==refs['cleanup_plan']['sha256'] and
            att.get('host_or_sdk_or_dll_or_window_execution') is False and
            result.get('protected_objects_or_sources_deleted') is False and result.get('runtime_default_or_saves_deleted') is False):
        raise RuntimeError('Typed retirement is not bound to the completed exact-six cleanup')
    for row in build['current_source_inputs']:files.verify(row)
    for row in helper.menu.frozen_rows(build).values():files.verify(row)
    units=build['final_compilation']['translation_units']
    if len(units)!=5 or len(plan['candidates'])!=6:raise RuntimeError('Typed retirement must cover five COFF objects and one environment script')
    object_names={helper.menu.key(u['object']['path']):u['translation_unit'] for u in units};retired=[]
    for row in plan['candidates']:
        if os.path.lexists(row['path']):raise RuntimeError('A retired intermediate still exists')
        key=helper.menu.key(row['path']);retired.append(dict(path=row['path'],bytes=row['bytes'],sha256=row['sha256'],
            role='FINAL_COFF_OBJECT' if key in object_names else 'BUILD_ENVIRONMENT_SCRIPT',translation_unit=object_names.get(key)))
    ledger=dict(schema='zerosis.menu_host.typed_retirement.v1',build_id=args.build_id,**refs,retired=retired,
        historical_only=True,missing_input_exception_scope='EXACT_TYPED_SIX_INTERMEDIATES',native_execution=False)
    spec={name+'_path':str(Path(row['path']).relative_to(PROJECT)) for name,row in refs.items()}
    spec.update({name+'_sha256':row['sha256'] for name,row in refs.items()});spec['cleanup_status']=result['status']
    helper.menu._retirement(build,PROJECT,spec,dict(retirement_ledger=ledger,cleanup_plan=plan,cleanup_result=result),files)
    image=files.verify(build['executable']);files.finish()
    sidecar_ref=helper.artifact(directory/'sidecar_independent_attestation.json')
    sidecar=json.loads(Path(sidecar_ref['path']).read_text(encoding='utf-8'))
    if not (sidecar['status']=='PASS_FINAL_62_SIDECAR_BYTES_IDENTITIES_AND_EXE_FILE_ONLY' and
            sidecar['build_id']==args.build_id and helper.menu.same(sidecar['executable'],image) and
            sidecar['hardlinked_files']==62 and sidecar['additional_unique_payload_bytes']==0):
        raise RuntimeError('Compile-only sealing needs the exact final independent sidecar proof')
    ledger_path=directory/'typed_retirement.json';helper.write_new(ledger_path,ledger)
    audit=dict(schema='zerosis.original_menu.compile_only_retirement.v1',status='PASS_COMPILE_ONLY_ATTESTED_AND_EXACT_SIX_RETIRED',
        build_id=args.build_id,build_result=refs['report'],independent_attestation=refs['attestation'],executable=image,
        cleanup_result=refs['cleanup_result'],typed_retirement=helper.artifact(ledger_path),
        frontend_sidecar_attestation=sidecar_ref,
        registered=False,eligible_for_registration=False,required_frontend_sidecar_count=62,
        prepared_runtime_sidecar_transport_integrated=False,default_promoted=False,
        original_Host_SDK_CLR_window_GPU_or_game_executed=False,full_native_or_original_ui_acceptance=False)
    helper.write_new(directory/'compile_only_audit.json',audit)
    print(json.dumps(dict(status=audit['status'],build_id=args.build_id,typed_retirement=helper.artifact(ledger_path),registered=False)))


if __name__=='__main__':main()
