"""Inspect the exact owned production unit hit and three GPU bitmap captures.

This is automated posted-input proof; it does not attest to a human click,
stock pixel equivalence, a playable world renderer, or a useful speedup.
"""
from __future__ import annotations

import json
from pathlib import Path

from probe_world_builder import artifact
from ui_window_frame import verify_frame, verify_closed_frame
from verify_city_decision_probe import fail, lines
from verify_world_builder_map_object import check_artifacts


def _document(row):
    check_artifacts(row)
    return json.loads(Path(row['path']).read_text(encoding='utf-8'))


def verify_window(result, request, output, selection, session):
    if request.get('production_window_requested') is not True or \
       result.get('production_window_enabled') is not True or \
       result.get('native_unit_hit_dispatch_verified') is not True or \
       result.get('gpu_frame_bitmap_parity_verified') is not True:
        fail('Production window mode or verified narrow input/capture flags are missing')
    report = _document(result['ui_window_report'])
    check_artifacts(report)
    if report.get('status') != 'LIVE_SDK_UI_WINDOW_POSTED_INPUT_PASS' or \
       report.get('production_fixture_enabled') is not True or \
       report.get('display_resize_enabled') is not True or report.get('refresh_closed_enabled') is not True or \
       report.get('scope') != 'actual_live_SDK_production_VM_and_owned_GPU_HWND_selected_unit_hit_and_closed_refresh' or \
       report.get('real_user_click_verified') is not False or report.get('installed_game_launched') is not False or \
       report.get('pid') != result['pid'] or report.get('returncode') != 0 or report.get('timed_out') is not False or \
       report.get('error') is not None:
        fail('Owned production driver did not preserve its actual PID and narrow automated-input scope')
    if request.get('inherited_ui_window_profile_environment_removed') is not True or \
       request.get('ui_window_profile_environment_overrides') != {'ZEROSIS_UI_WINDOW_PROFILE':'display-refresh'}:
        fail('Production window did not use its explicit closed refresh profile')
    tools = request.get('ui_window_tools', [])
    expected_files = {'live_ui_window_driver.py','render_ui_popup.py','ui_pixel_scene.py','ui_bitmap_fonts.py',
                      'civ5_ui_assets.py','ui_window_frame.py','inline_icons.json'}
    if len(tools) != len(expected_files) or {Path(row['path']).name for row in tools} != expected_files:
        fail('Production window frozen helper closure is incomplete or duplicated')
    root = Path(request['cwd']).resolve()
    for row in tools:
        check_artifacts(row)
        if Path(row['path']).resolve().parent != root/'UiPresentationTools/tools':
            fail('Production presentation helper escaped the exact private runtime')
    scenes, closed, windows, frames = (report.get(name,[]) for name in ('scenes','refresh_scenes','windows','frames'))
    if len(scenes)!=1 or len(closed)!=1 or len(windows)!=1 or len(frames)!=3:
        fail('Production window must retain exactly one unit-choice scene, one closed scene, one HWND and three GPU frames')
    scene, closed_scene, window = scenes[0], closed[0], windows[0]
    if scene.get('sequence')!=1 or scene.get('turn')!=0 or closed_scene.get('sequence')!=1 or closed_scene.get('turn')!=0 or \
       Path(scene['snapshot']['path']).resolve()!=session/'ui-popup-1-window.json' or \
       Path(closed_scene['snapshot']['path']).resolve()!=session/'ui-popup-1-closed.json':
        fail('Production window snapshot identity differs from the actual turn-zero restored SDK session')
    snapshot = _document(scene['snapshot'])
    if snapshot.get('contextName')!='ProductionPopup' or snapshot.get('active') is not True or \
       snapshot.get('presentationClock')!=0.25 or snapshot.get('timerSemaphore')!=0:
        fail('Production native input scene is not the clocked official active popup')
    manifest = _document(scene['manifest'])
    next_manifest = _document(closed_scene['manifest'])
    if manifest.get('context')!='production' or manifest.get('context_name')!='ProductionPopup' or \
       manifest.get('snapshot_state_unchanged') is not True or manifest['snapshot']['sha256']!=scene['snapshot']['sha256'] or \
       next_manifest.get('context')!='production' or next_manifest.get('closed_context_not_drawn') is not True or \
       any(next_manifest.get(name)!=0 for name in ('texture_count','sprite_count')) or next_manifest.get('hit_regions')!=[]:
        fail('Production shown/closed scene did not retain its exact source or empty closed contribution')
    selected = {'key':selection[2],'city_id':selection[0],'unit_id':selection[1]}
    hit = window.get('selected_hit')
    hits = [row for row in manifest.get('hit_regions',[]) if row[0]==selection[2]]
    if window.get('selected_control')!=selected or len(hits)!=1 or hits[0]!=hit or \
       window.get('synthetic_messages_posted') is not True:
        fail('Posted production click is not bound to the same native-selected legal unit and exact clipped hit')
    x,y = window.get('posted_click_logical',[None,None])
    if not hit[1]<=x<hit[3] or not hit[2]<=y<hit[4]:
        fail('Native production test point escaped its selected retained hit area')
    top = next((row for row in reversed(manifest['hit_regions']) if row[1]<=x<row[3] and row[2]<=y<row[4]),None)
    if top!=hit:
        fail('Posted production coordinate is covered by a different active control')
    width,height=window['client'];client_x,client_y=window['posted_click_client']
    scale=min(width/1920,height/1080)
    if abs(x-(client_x-(width-1920*scale)/2)/scale)>1e-8 or \
       abs(y-(client_y-(height-1080*scale)/2)/scale)>1e-8:
        fail('Posted production client point is inconsistent with its native letterbox conversion')
    if window.get('sequence')!=1 or window.get('pid')!=result['pid'] or window.get('accepted')!=1 or window.get('delivered')!=2 or \
       window.get('refresh_accepted')!=0 or window.get('refresh_delivered')!=1 or \
       window.get('scene_generation_before')!=1 or window.get('scene_generation_after')!=2 or \
       not window.get('refresh_device_identity_before',0)==window.get('refresh_device_identity_after') or \
       not window.get('refresh_device_identity_before',0)>0:
        fail('Production unit input or rejected stale/closed input lost its HWND/device/scene-generation boundary')
    identity=(window['hwnd'],window['owner_thread'])
    if lines(output,'UI_WINDOW_EXPECTED_CONTROL')!=[f'1|{selection[2]}|{selection[0]}|{selection[1]}'] or \
       lines(output,'UI_WINDOW_COMPLETE')!=['1|2|1|owner-thread'] or \
       lines(output,'UI_WINDOW_REFRESH_COMPLETE')!=['1|1|0|2|owner-thread'] or \
       lines(output,'UI_WINDOW_STATE_UNCHANGED')!=['1|before-input'] or \
       lines(output,'UI_WINDOW_REFRESH_STATE_UNCHANGED')!=['1|after-refresh'] or \
       lines(output,'PRODUCTION_UI_WINDOW_ROUTE')!=['OWNED_HWND_HIT_OFFICIAL_CALLBACK_SDK_RECEIVER']:
        fail('Production native hit lifecycle markers are missing, duplicated or inconsistent')
    input_rows=[list(map(int,row.split('|'))) for row in lines(output,'UI_WINDOW_INPUT')]
    if len(input_rows)!=3 or any(len(row)!=10 or row[0]!=1 or row[4]!=row[5] or row[6:9]!=[0,0,0] or
                               row[9]!=identity[1] for row in input_rows) or \
       [row[1:4] for row in input_rows]!=[[2,selection[2],1],[1,27,0],[1,27,0]]:
        fail('Production window did not dispatch exactly its unit click and reject the late and closed-scene Escape inputs')
    captures = {}
    for frame in frames:
        phase=frame.get('phase')
        if phase not in ('initial','resized','closed') or phase in captures or frame.get('sequence')!=1 or \
           frame.get('pid')!=result['pid'] or (frame.get('hwnd'),frame.get('owner_thread'))!=identity or \
           frame.get('native_visible') is not True or frame.get('desktop_pixels_verified') is not False or \
           frame.get('client')!=([1000,700] if phase=='initial' else [900,600]):
            fail('Production GPU frame is not from the same owned HWND, thread and expected client')
        source=closed_scene if phase=='closed' else scene
        pixel=(verify_closed_frame if phase=='closed' else verify_frame)(
            Path(source['png']['path']),Path(frame['png']['path']),*frame['client'])
        if pixel!=frame.get('pixel_check'):
            fail('Production GPU bitmap parity differs from independent pixel recomputation')
        captures[phase]=frame
    for before,after in zip(('initial','resized'),('resized','closed')):
        if captures[after]['render_count']<=captures[before]['render_count'] or \
           captures[after]['present_count']<=captures[before]['present_count'] or \
           captures[after]['device_kind']!=captures[before]['device_kind']:
            fail('Production GPU resize/closed refresh did not keep device and counter continuity')
    frame_lines=lines(output,'UI_WINDOW_FRAME')
    if len(frame_lines)!=3:
        fail('Production native GPU capture markers are missing or duplicated')
    for text,phase in zip(frame_lines,('initial','resized','closed')):
        fields=text.split('|',12);frame=captures[phase]
        expected=[str(value) for value in (1,phase,*identity,*frame['client'],frame['render_count'],
                  frame['present_count'],frame['present_hresult'],frame['device_kind'],int(frame['present_occluded']),1,frame['png']['path'])]
        if fields!=expected or frame['present_hresult'] not in (0,0x087A0001) or \
           frame['present_occluded']!=(frame['present_hresult']==0x087A0001):
            fail('Production GPU metadata differs from the actual Host capture marker or exact Present HRESULT')
    return {'driver_report':artifact(Path(result['ui_window_report']['path'])),'selected_control':selected,
            'selected_hit':hit,'posted_click_client':window['posted_click_client'],
            'native_unit_hit_and_original_callback_verified':True,
            'late_escape_rejected_after_official_close':True,'closed_escape_rejected':True,
            'closed_empty_hit_map_rejects_old_unit_coordinate':True,
            'stale_scene_generation_control_event_rejection_verified':False,
            'same_hwnd_device_closed_refresh_verified':True,'gpu_frames':frames,
            'gpu_bitmap_pixel_parity_verified':True,'human_input_verified':False,
            'retail_pixel_equivalence_verified':False,'world_renderer_verified':False}
