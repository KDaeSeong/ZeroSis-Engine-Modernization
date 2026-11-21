"""Attach the separately verified SDK historical-input recovery and exact cleanup receipts."""
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[2]
sys.path.insert(0,str(PROJECT/'tools'))
import build_exit_confirm_host as common

def read(path):return json.loads(Path(path).read_text('utf8'))
def ref(path):return common.artifact(Path(path).absolute())

def main():
    value=read(STAGE/'current_work.json');assert 'runtime_input_recovery' not in value
    module=ref(PROJECT/'tools/current_runtime_sdk_input.py')
    assert module['sha256']=='ff092c1b0ba80c3b5d33a79f6246bd9606073e9c49a79e2fd60a8bb9feaf0b88'
    history=PROJECT/'evidence/sdk_runtime_play/historical_os_inputs'
    profile=ref(history/'profile.json');result=ref(history/'validation_result.json')
    assert profile['sha256']=='68c0242d04c17c2f3d743e3bc95e78648b4d8294d01a02e64f9b2207f7c91f0d'
    assert result['sha256']=='552960153d8bb4062a42ce787a98c458238dd1c79a5947d425e4a9b136622931'
    build=read(value['current_host']['build_result']['path'])
    assert not any(common.key(row['path'])==common.key(module['path']) for row in build['current_source_inputs'])
    run=value['current_prepared_runtime']['run_id'];request=read(PROJECT/'evidence/interactive_game'/run/'request.json')
    frozen=request['provenance']['current_runtime_sdk_input']
    assert frozen['sha256']==module['sha256'] and Path(frozen['path']).is_relative_to(PROJECT/'evidence/interactive_game'/run)
    frozen=ref(frozen['path']);assert frozen['sha256']==module['sha256']
    payloads=[ref(history/name) for name in ('cmd.exe.history.bin','tzres.dll.history.bin')]
    assert sum(row['bytes'] for row in payloads)==352256
    recovery=dict(status='PASS_EXACT_BYTE_BACKED_HISTORICAL_SYSTEM_INPUTS_PREPARATION_RECOVERED',
        requirements=ref(STAGE/'requirements_runtime_recovery.json'),source_before=ref(STAGE/'sdk_validator_before.json'),
        current_validator=module,frozen_preparation_validator=frozen,profile=profile,validation=result,
        independent_review='Root and idle_cache_tests read-only reviews: exact static parent/profile and two byte-backed aliases only; existing SDK graph checks retained.',
        rejection_checks=14,retained_payloads=payloads,retained_payload_bytes=352256,
        initial_preparation_failure=ref(PROJECT/'evidence/game_menu/menu_runtime_ui_followup/pair_preparation'/
            value['current_host']['build_id']/'materialization/failure.json'),
        successful_retry=value['current_prepared_runtime']['prepared_verification'],
        new_sdk_compilation=False,system_files_or_original_reports_modified=False,current_os_provider_replaced=False,
        host_source_closure_changed=False,gamecore_sha256='430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9')
    value['runtime_input_recovery']=recovery
    leaves=[STAGE/'tests/cleanup_result.json',STAGE/'pair_preparation'/value['current_host']['build_id']/'cleanup_result.json',
            STAGE/'failed_discovery_cleanup_result.json']
    count=0;released=0;receipts=[]
    for path in leaves:
        data=read(path);receipts.append(ref(path))
        count+=data.get('retired_files',data.get('files_deleted',data.get('deleted_files',0)))
        released+=data.get('released_unique_allocated_bytes',data.get('allocated_bytes_released',0))
    value['storage'].update(owned_intermediate_cleanup_receipts=receipts,owned_intermediate_files_deleted=count,
        owned_intermediate_unique_allocated_bytes_released=released)
    (STAGE/'runtime_input_recovery.json').write_text(json.dumps(recovery,indent=2)+'\n',encoding='utf8')
    (STAGE/'current_work.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    text=('추가 연동 기록: 기존 SDK 제작 당시의 Windows 파일 두 개가 운영체제 갱신 뒤 달라져 첫 준비가 중단됐다. '
        'WinSxS의 실제 옛 사본을 재해시해 같은 바이트임을 확인하고, 합계352,256바이트의 역사 자료로만 보관했다. '
        '고정된 static SDK·부모·프로필과 정확한 두 원래 입력에만 적용되는 검증 별칭을 추가했다. '
        '보관 바이트는 일반 검증과 종료 재해시를 거치며 기존 전체 SDK 입력·객체·의존성 검사는 유지했다. '
        '훼손·범위 이탈 거부14개와 공개 파일 검증을 통과해 준비 재시도1이 성공했다. SDK 재빌드·시스템 파일 변경·과거 도구 실행은 없었다. '
        '근거는 `evidence/sdk_runtime_play/historical_os_inputs/validation_result.json`과 '
        '`evidence/game_menu/idle_render_cache/runtime_input_recovery.json`이다.\n\n')
    marker='## 유휴 렌더링 재사용 단계 — 2026-11-15\n\n'
    for name in ('docs/CLAUDE_HANDOFF.md','docs/ORIGINAL_MENUS_OFFLINE.md'):
        path=PROJECT/name;contents=path.read_text('utf8');assert contents.count(marker)==1
        path.write_text(contents.replace(marker,marker+text,1),encoding='utf8')
    print(json.dumps(dict(status=recovery['status'],owned_intermediate_files_deleted=count,
        owned_intermediate_unique_allocated_bytes_released=released,historical_payload_bytes=352256)))

if __name__=='__main__':main()
