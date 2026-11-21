"""SDK-free reward preferences plus original video-confirmation integration."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import run
import build_exit_confirm_host as common
from menu_suite_storage import storage
from menu_replay_restoration import build_cxx14

V1=PROJECT/'Source/Assets/UIFrontEnd'
V2=PROJECT/'Source/Assets/UIFrontEndV2'
V4=PROJECT/'Source/Assets/UIFrontEndV4'
ROOT=PROJECT/'evidence/game_menu/options_reward_popups/integration'
BUILD=PROJECT/'Build/MenuFrontEndOptions/current'
LOCALIZATION=PROJECT/'Build/InteractiveGameRuntime/20261105T123201Z_9a1a8fa8c1a2/localization.db'
V2_MANIFEST=PROJECT/'evidence/game_menu/menu_runtime_ui_followup/frontend/assets_v2.json'
SLIDER_PROBE=PROJECT/'evidence/game_menu/native_offline_followup/retail_slider_key_probe.json'
SLIDER_PROBE_SHA='514c64c0efd65f38c2b20192eb311c3c89f31932e56ae708d2a7787a206a6121'
OPTIONS_XML=PROJECT/'Source/Assets/UI/Assets/UI/Options/OptionsMenu.xml'
GATE_PROBE=PROJECT/'evidence/game_menu/native_slider_hover/retail_slider_gate_probe.json'
GATE_PROBE_SHA='df984576e0758b95acb322b21f6d069a425d072c642c6b6fec1840b9e9a98911'


def labels(path):
    manifest=json.loads(V2_MANIFEST.read_text('utf8'))
    keys={row['text'] for row in manifest['options_control_layout'] if row['text']}
    old=json.loads((PROJECT/'evidence/game_menu/original_menu_followup/frontend/assets.json').read_text('utf8'))
    keys.update(row['text'] for row in old['controls'] if row['text'])
    keys.update(('TXT_KEY_MULTIPLAYER_OPTIONS','TXT_KEY_OPSCREEN_RESOLUTION','TXT_KEY_OPSCREEN_APPLY_RESOLUTION',
        'TXT_KEY_OPSCREEN_RESOLUTION_TIMER','TXT_KEY_YES_BUTTON','TXT_KEY_NO_BUTTON',
        'TXT_KEY_OPSCREEN_NO_REWARD_POPUPS','TXT_KEY_OPSCREEN_NO_REWARD_POPUPS_TT'))
    database=sqlite3.connect(LOCALIZATION.as_uri()+'?mode=ro&immutable=1',uri=True)
    blob=bytearray(struct.pack('<I',len(keys)))
    try:
        for original in sorted(keys):
            key=original.strip('{}').split(':')[0]
            row=database.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(key,)).fetchone()
            if row is None or not row[0] or row[0].startswith('TXT_KEY_'):raise ValueError('Missing actual Korean caption: '+key)
            for value in (original,row[0]):
                raw=value.encode('utf8');blob+=struct.pack('<I',len(raw))+raw
    finally:database.close()
    with path.open('xb') as stream:stream.write(blob)
    return sorted(keys)


def retail_slider_rules():
    """Bind the volume slider model to the pinned retail Slider key/wheel probe and the source WheelSteps."""
    if hashlib.sha256(SLIDER_PROBE.read_bytes()).hexdigest()!=SLIDER_PROBE_SHA:raise ValueError('Pinned retail slider key probe differs')
    probe=json.loads(SLIDER_PROBE.read_text('utf8'))
    if probe.get('executed') is not False or probe['exe']['sha256']!='b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818':
        raise ValueError('Retail slider probe is not the static pinned-EXE record')
    semantics=probe['slider_key_path']['semantics']
    if not semantics['message'].startswith('WM_KEYUP (0x101) only') or not semantics['keys'].startswith('VK_LEFT (0x25) and VK_UP (0x26) subtract'):
        raise ValueError('Retail slider key semantics differ')
    found=re.findall(r'<Slider\b[^>]*\bID="EffectsVolumeSlider"[^>]*>',OPTIONS_XML.read_text('utf8'))
    steps=re.findall(r'\bWheelSteps="([^"]*)"',found[0]) if len(found)==1 else []
    if steps!=['1']:raise ValueError('Original EffectsVolumeSlider WheelSteps differs')
    model=(PROJECT/'Source/Host/MenuFrontEndOptionsModel.h').read_text('utf8')
    if 'static constexpr int OriginalVolumeSliderWheelSteps=1;' not in model or 'shift?-10' in model or 'shift?10' in model:
        raise ValueError('Volume slider model is not bound to the retail one-step rule')
    if hashlib.sha256(GATE_PROBE.read_bytes()).hexdigest()!=GATE_PROBE_SHA:raise ValueError('Pinned retail slider gate probe differs')
    gate=json.loads(GATE_PROBE.read_text('utf8'))
    if gate.get('executed') is not False or gate['state_bit_0x10000']['lua_mouse_enum']!={'eMouseEnter':5,'eMouseExit':6} or \
       not gate['state_bit_0x10000']['meaning'].startswith('Pointer-over (hover)'):
        raise ValueError('Retail slider gate is not the pinned pointer-over record')
    if 'hover==KeyFor(Control::Volume)' not in model or 'focus_==Control::Volume && page_==Page::Audio' in model:
        raise ValueError('Volume slider keys are not gated by pointer-over')
    return dict(probe=common.artifact(SLIDER_PROBE),gate_probe=common.artifact(GATE_PROBE),
        retail_gate='control state bit 0x10000 = pointer-over (Mouse.eMouseEnter 5 sets, eMouseExit 6 clears)',
        engine_gate='key events carry the lifecycle hovered control; volume keys need hover==KeyFor(Volume), focus is not used',
        effects_volume_wheel_steps=1,step_percent=1,
        subtract_keys=[37,38],add_keys=[39,40],ignored_keys=[35,36],modifiers_change_step=False,
        retail_message='WM_KEYUP',engine_message='first WM_KEYDOWN of a press (auto-repeat filtered)',
        timing_difference='Retail moves on key release; this window moves on the first key press. One press moves one step in both.')


def main():
    source_names=['Tests/menu_frontend_options_offline.cpp','Tests/menu_frontend_options_offline.py',
        'Tests/menu_frontend_scene_fixture.h','Source/Host/MenuFrontEndAssets.h','Source/Host/MenuFrontEndGridLayout.h',
        'Source/Host/MenuFrontEndOptionsModel.h','Source/Host/MenuFrontEndOptionsView.h','Source/Host/MenuOptionsContract.h',
        'Source/Host/MenuOptionsStore.h','Source/Host/MenuOptionsHostBinding.h','Source/Host/MenuLifecycleWindow.h',
        'Source/Host/MenuResolutionCountdown.h','Source/Host/MenuResolutionPreviewClock.h','Source/Host/MenuResolutionPreviewLayout.h',
        'Source/Host/MenuRewardOptionsLayout.h',
        'tools/menu_frontend_options_assets.py','tools/menu_frontend_cpu.py','Tests/menu_replay_restoration.py',
        'Source/Assets/UI/Assets/UI/Options/OptionsMenu.lua','Source/Assets/UI/Assets/UI/Options/OptionsMenu.xml']
    paths=[PROJECT/name for name in source_names]+[LOCALIZATION,V2_MANIFEST,SLIDER_PROBE,GATE_PROBE]
    paths+=sorted(path for root in (V1,V2,V4) for path in root.rglob('*') if path.is_file())
    before=[common.artifact(path) for path in paths]
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:16]
    stage=ROOT/signature;stage.mkdir(parents=True,exist_ok=True)
    receipt=stage/'result.json'
    if receipt.exists():raise ValueError('Inspect the existing result instead of repeating this exact input set')
    BUILD.mkdir(parents=True,exist_ok=True)
    leaves=['labels.bin','options_audio.packet','options_video.packet','options_resolution_preview.packet',
        'MenuFrontEndOptions.obj','MenuFrontEndOptions.map','compile.rsp','read_build_environment.cmd']
    if any((BUILD/name).exists() for name in leaves):raise ValueError('Inspect retained prior temporary inputs')
    report=dict(schema='zerosis.options_reward_popups.integration.v1',inputs_before=before,
        native_window_execution=False,host_or_sdk_executed=False,gpu_execution=False,audio_execution=False,
        retail_pixel_acceptance=False,controlled_backend='Owned fake apply/readback and canonical persistence; actual Source model/session/view and V1/V2/V4 asset readers.')
    try:
        report['localized_release_labels']=labels(BUILD/'labels.bin')
        lifecycle=(PROJECT/'Source/Host/MenuLifecycleWindow.h').read_text('utf8')
        checks={
            'actual_startup_readback':'hooks.applyOptions(window,startup)!=startup' in lifecycle,
            'old_input_generation_rejection':'if(input.sceneGeneration!=window.SceneGeneration())continue;' in lifecycle,
            'dedicated_preview_clock':'resolutionClock.Sample(tick,page==Page::Options && options.ResolutionPreviewActive(),&previewElapsed)' in lifecycle,
            'post_backend_start_origin':'if(!previewBefore && options.ResolutionPreviewActive())resolutionClock.Start(GetTickCount64());' in lifecycle,
            'unclamped_preview_clock_delta':'options.AdvanceResolutionPreview(previewElapsed)' in lifecycle,
            'failure_route_reused':'finishOptions();' in lifecycle,
            'volume_keys_receive_pointer_over':'value.hover=hovered;' in lifecycle,
        }
        if not all(checks.values()):raise ValueError('Actual lifecycle video-preview wiring differs')
        report['source_binding_checks']=checks
        report['retail_slider_rules']=retail_slider_rules()
        built=build_cxx14('MenuFrontEndOptions',BUILD,stage,PROJECT/'Tests/menu_frontend_options_offline.cpp',
            [PROJECT/'Source/Host',PROJECT/'Tests'])
        report['build']=built
        imported=run([Path(built['compiler']).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected controlled fixture imports: '+repr(names))
        report['imported_dlls']=names
        result=run([built['path'],V2,V1,BUILD/'labels.bin',BUILD,V4],cwd=BUILD,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout))
        packet=BUILD/'options_resolution_preview.packet';report['actual_preview_packet']=common.artifact(packet)
        from menu_frontend_cpu import render
        reused=None
        old_proofs=list(ROOT.glob('*/result.json'))+list((PROJECT/'evidence/game_menu/options_video_preview/integration').glob('*/result.json'))
        for old in old_proofs:
            if old==receipt:continue
            previous=json.loads(old.read_text('utf8'))
            prior_packet=previous.get('actual_preview_packet',{})
            prior=previous.get('cpu_proof',{}).get('image',{})
            if previous.get('protected_inputs_unchanged') and prior_packet.get('sha256')==report['actual_preview_packet']['sha256'] and prior:
                image=Path(prior['path'])
                if image.is_file() and common.artifact(image)['sha256']==prior['sha256']:
                    reused=previous['cpu_proof'];report['identical_packet_preview_reuse']=common.artifact(old);break
        report['cpu_proof']=reused or render(packet,stage/'options_resolution_preview.png',V4)
        report['inputs_after']=[common.artifact(path) for path in paths]
        if report['inputs_after']!=before:raise ValueError('Current source/immutable asset fixture input changed')
        report['protected_inputs_unchanged']=True
    except Exception as error:
        report.update(status='FAIL_SOURCE_REWARD_OPTIONS_INTEGRATION',error=str(error));raise
    finally:
        removed=[]
        for leaf in leaves:
            path=BUILD/leaf
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Cleanup escaped exact unshared fixture intermediates')
            row=dict(**common.artifact(path),allocated_bytes=storage.allocated(path));path.unlink()
            row['result']='DELETED_EXACT_OWNED_REGENERABLE_OPTIONS_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed
        with receipt.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2);stream.write('\n')
    print(json.dumps({key:report[key] for key in ('status','checks','resolution_preview_bound','native_window_execution','gpu_execution','protected_inputs_unchanged')}))


if __name__=='__main__':main()
