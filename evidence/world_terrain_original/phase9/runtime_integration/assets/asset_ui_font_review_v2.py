"""Read-only review of pinned owned font provenance and original UI read paths."""
from __future__ import annotations
import argparse
import ast
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone
from asset_input_review import artifact, canonical, require, verify_ref, read, PROJECT, OUT, OLD


def run(root):
    root = canonical(root)
    require(root.parent == PROJECT/'Build/InteractiveGameRuntime', 'Unexpected runtime root')
    prepared_path = root/'interactive_ui_support/assets/prepared.json'
    prepared = read(prepared_path)
    inputs = prepared['inputs']
    require(len(inputs) == 74, 'Expected retained 74 original UI inputs')
    ui = []
    for row in inputs:
        installed, snapshot = verify_ref(row['installed']), verify_ref(row['snapshot'])
        require(installed['sha256'] == snapshot['sha256'], 'Original UI/snapshot differs: ' + row['name'])
        ui.append(dict(name=row['name'],installed=installed,snapshot=snapshot))
    font = prepared['font_input_profile']
    require(font['input_storage'] == 'CONTENT_ADDRESSED_ENGINE_OWNED_FONT_INPUTS' and font['source_files_copied'] == 0, 'Font root reuse policy differs')
    manifestref = verify_ref(font['manifest'])
    fontmanifest = read(manifestref['path'])
    fontroot = canonical(font['asset_root'])
    require(fontroot.is_relative_to(PROJECT/'Build/SharedUiFontInputs') and fontroot.name == '06ba57aa477fc561db3f97089f98bf1cf70a34c047b8fa8dbcee2fc1d255a617', 'Font input root differs')
    require(fontmanifest['asset_root'] == str(fontroot) and fontmanifest['profile_id'] == font['profile_id'], 'Font profile root or identity differs')
    require(set(fontmanifest['fonts']) == {'TwCenMT14','TwCenMT16','TwCenMT18','TwCenMT20','TwCenMT22','TwCenMT24'}, 'Font family inventory differs')
    require(len(font['original_inputs']) == 15, 'Font input count differs')
    shared_fonts = [verify_ref(row) for row in font['original_inputs']]
    manifest_fonts = [verify_ref(fontmanifest['color_atlas'])]
    for row in fontmanifest['fonts'].values():
        manifest_fonts.append(verify_ref(row['ggxml']))
        manifest_fonts.extend(verify_ref(item) for item in row['textures'].values())
    require({row['path']:row['sha256'] for row in shared_fonts} == {row['path']:row['sha256'] for row in manifest_fonts}, 'Font manifest inventory differs')
    helper = verify_ref(font['helper'])
    capture_path = PROJECT/'evidence/goody_hut/owned_fonts/capture_result.json'
    capture = read(capture_path)
    require(capture['status']=='PASS' and capture['cache_root']==str(fontroot) and capture['owned_profile']==fontmanifest, 'Owned capture provenance differs')
    require(verify_ref(capture['profile'])['sha256']==manifestref['sha256'], 'Owned capture profile SHA differs')
    require({row['path']:(row['sha256'],row['bytes']) for row in capture['owned_inputs']}=={row['path']:(row['sha256'],row['bytes']) for row in shared_fonts}, 'Owned capture inputs differ')
    profile_payload={key:value for key,value in fontmanifest.items() if key!='profile_id'}
    import hashlib
    profile_identity=hashlib.sha256(json.dumps(profile_payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')).hexdigest()
    require(profile_identity==font['profile_id'], 'Font profile semantic identity differs')
    asset_module = root/'interactive_ui_support/tools/civ5_ui_assets.py'
    tree = ast.parse(asset_module.read_text('utf8'), filename=str(asset_module))
    assignments = {node.targets[0].id:node.value for node in tree.body if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name)}
    rootcall = assignments['MENU_SOURCE_GAME_ROOT']
    require(isinstance(rootcall,ast.Call) and isinstance(rootcall.func,ast.Name) and rootcall.func.id == 'Path' and len(rootcall.args) == 1, 'Original UI root expression differs')
    game = canonical(ast.literal_eval(rootcall.args[0]))
    require(str(game) == r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V", 'Original UI game root differs')
    originals = []
    for name,(relative,size,digest) in ast.literal_eval(assignments['MENU_SOURCE_IDENTITIES']).items():
        row = artifact(game/relative)
        require(row['bytes'] == size and row['sha256'] == digest, 'Original menu identity differs: ' + name)
        originals.append(dict(name=name,artifact=row))
    for name,row in ast.literal_eval(assignments['LOOSE_UI_TEXTURES']).items():
        actual = artifact(game/row['relative_path'])
        require(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'], 'Original loose UI texture differs: ' + name)
        originals.append(dict(name=name,artifact=actual))
    original_fonts = []
    for shared in shared_fonts:
        path = Path(shared['path'])
        require(path.is_relative_to(fontroot), 'Shared font escaped input root')
        original = artifact(game/path.relative_to(fontroot))
        original_fonts.append(dict(original,byte_equal_to_shared=original['sha256']==shared['sha256'] and original['bytes']==shared['bytes']))
    pack_paths = []
    for name in ast.literal_eval(assignments['PACK_POLICY']):
        path = canonical(game/'Resource/DX9'/name)
        require(path.is_file(), 'Missing original UI pack')
        s = path.stat()
        pack_paths.append(dict(path=str(path),bytes=s.st_size,file_identity=[s.st_dev,s.st_ino],mtime_ns=s.st_mtime_ns,file_attributes=getattr(s,'st_file_attributes',0),sha256_recomputed_here=False))
    return dict(schema='zerosis.phase9.ui_font_original_input_review.v1',status='PASS_UI74_FONT15_ORIGINAL_ROOTS_FILE_ONLY',
                utc=datetime.now(timezone.utc).isoformat(),scope='NoNative0',runtime_directory=str(root),prepared=artifact(prepared_path),
                original_ui_inputs=ui,font_manifest=manifestref,font_helper=helper,font_root=str(fontroot),font_profile_id=font['profile_id'],
                font_inputs=shared_fonts,owned_capture_provenance=artifact(capture_path),font_original_observations=original_fonts,installed_font_equality_required_for_runtime_binding=False,installed_font_difference_count=sum(not row['byte_equal_to_shared'] for row in original_fonts),original_root=str(game),selected_original_ui_leaves=originals,
                original_ui_pack_paths_metadata_only=pack_paths,original_pack_payload_copies=0,new_font_input_copies=0,
                native_host_gamecore_clr_hwnd_gpu_audio_or_game_attempts=0,source_or_original_inputs_modified=False,
                limitations='Owned font profile/provenance/path contract and selected original UI leaves only. Owned fonts may differ from current installed fonts; FPK SHA not recomputed here; readability/rendering/native acceptance held.',
                verifier_source=artifact(__file__))


def boundary(event,args):
    if event.startswith(('subprocess.','socket.','winreg.')) or event in ('os.system','os.startfile','ctypes.dlopen'):
        raise PermissionError('NoNative0 forbids native/process/network/registry calls')
    if event == 'open':
        mode,flags = args[1],args[2]
        writing = isinstance(mode,str) and any(c in mode for c in 'wax+')
        writing |= isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        if writing:
            path = Path(os.fsdecode(args[0])).absolute()
            require(path.parent == OUT and path.name.startswith('asset_') and path.suffix == '.json', 'Write escaped owned asset evidence')
    elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime','os.rename','os.replace','os.link','os.symlink'):
        raise PermissionError('UI/font review does not mutate runtime or inputs')


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--runtime',type=Path,default=OLD)
    cli.add_argument('--output-name',default='asset_ui_font_input_review_v2.json')
    args = cli.parse_args()
    output = OUT/args.output_name
    require(output.parent == OUT and output.name.startswith('asset_') and output.suffix == '.json' and not output.exists(), 'Use a new owned asset evidence output')
    sys.addaudithook(boundary)
    result = run(args.runtime)
    with output.open('x',encoding='utf8') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'],scope=result['scope'],original_ui=74,font_inputs=15,original_pack_payload_copies=0,output=artifact(output))))


if __name__ == '__main__':
    main()
