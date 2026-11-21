"""Strict offline HLSL compilation, ABI reflection and information-boundary checks.

Only the pinned Windows SDK shader compiler is executed. No graphics device,
Host, GameCore, CLR, window, audio or game is created or loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE_ROOT = PROJECT / 'evidence/world_terrain_original/phase2/shader'
SOURCE = PROJECT / 'Source/Presentation/OriginalFogShader.h'
GPU_TYPES = PROJECT / 'Source/Presentation/OriginalFogGpuTypes.inc'
TOOL_SHA = 'ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'


def ref(path):
    path = Path(path).absolute()
    info = path.stat(follow_symlinks=False)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                file_identity=[info.st_dev, info.st_ino], mtime_ns=info.st_mtime_ns,
                file_attributes=info.st_file_attributes, links=info.st_nlink)


def write_new(path, value):
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def source_contract(shader, types):
    clean = re.sub(r'//[^\n]*', '', shader)
    pixel = clean[clean.index('float4 pixelMain('):]
    branch = re.search(r'\[branch\]\s*if\(state\.y==0\)result=replacement;\s*else\s*\{([^{}]+)\}', pixel)
    known = branch.group(1) if branch else ''
    checks = dict(
        single_colour_output=':SV_Target0' in pixel and not re.search(r'SV_Target[1-9]', clean),
        exact_plot_state_is_integer='Texture2D<uint2> PlotState : register(t3);' in clean,
        exact_state_before_smoothing=pixel.index('PlotState.Load(') < pixel.index('MaskTexture.Sample('),
        unknown_branch_uses_replacement=bool(branch),
        only_revealed_branch_reads_terrain='SceneColour.Load(int3(pixel,0)).rgb' in known,
        only_revealed_branch_reads_lut='FowColourKey.Sample(ClampSampler,result)' in known,
        unknown_no_terrain_or_lut_in_replacement=not re.search(r'SceneColour|SceneDepth|FowColourKey|PlotState',
            clean[clean.index('float3 Replacement('):clean.index('float DistanceFactor(')]),
        replacement_mix='result=lerp(replacement,terrain,mask.r);' in known,
        explored_hidden_lut_mix='result=lerp(result,transformed,mask.r*(1-mask.b));' in known,
        retail_z_up_delta='(local-camera.xyz).xzy*float3(1,-1,1)*distanceParameters.w' in clean,
        original_exponent_order='(1-exp2(delta.z*distanceParameters.x*1.442695))*dot(delta,delta)*distanceParameters.y/delta.z' in clean,
        original_outer_exp='1-min(exp2(exponent*1.442695),1)' in clean,
        original_ramp_uv_and_red='FogRamp.Sample(ClampSampler,float2(ndcY*0.5+0.5,distanceParameters.z)).r' in clean,
        finite_horizontal_ray_limit='if(abs(delta.z)<0.0001)' in clean and
            '-distanceParameters.x*(0.6931471805599453*1.442695)*dot(delta,delta)*distanceParameters.y' in clean,
        final_fog_after_fow='lerp(result,fogColour.rgb,DistanceFactor(local,ndc.y))' in pixel,
        no_integer_output_or_store=not re.search(r'RWTexture|RWBuffer|SV_Target1|Interlocked|\.Store\(', clean),
        no_depth_or_discard_output=not re.search(r'SV_Depth|\bdiscard\b', clean),
        cpu_abi_208='sizeof(FogConstants)==208' in types,
    )
    return checks


def reflected_contract(listing):
    expected = [('inverseViewProjection', 0, 64), ('viewport', 64, 16), ('mapInfo', 80, 16),
                ('camera', 96, 16), ('distanceParameters', 112, 16), ('fogColour', 128, 16),
                ('flow', 144, 48), ('phase', 192, 16)]
    offsets = []
    for name, offset, size in expected:
        match = re.search(r'\b' + name + r'(?:\[3\])?;\s*//\s*Offset:\s*(\d+)\s+Size:\s*(\d+)', listing)
        offsets.append(dict(name=name, expected_offset=offset, expected_size=size,
                            reflected_offset=int(match[1]) if match else None,
                            reflected_size=int(match[2]) if match else None,
                            matches=bool(match and int(match[1]) == offset and int(match[2]) == size)))
    resources = [('SceneColour', 't0'), ('SceneDepth', 't1'), ('MaskTexture', 't2'), ('PlotState', 't3'),
                 ('Cloud1', 't4'), ('Cloud2', 't5'), ('Cloud3', 't6'), ('FlowField', 't7'),
                 ('FogDiffuse', 't8'), ('FowColourKey', 't9'), ('FogRamp', 't10'),
                 ('ClampSampler', 's0'), ('WrapSampler', 's1'), ('MaskSampler', 's2'), ('Fog', 'cb0')]
    bindings = []
    for name, slot in resources:
        matches = [line for line in listing.splitlines() if re.match(r'//\s*' + name + r'\s+', line)
                   and re.search(r'\b' + slot + r'\s+1\s*$', line)]
        bindings.append(dict(name=name, slot=slot, matches=len(matches) == 1))
    instructions = [line.strip() for line in listing.splitlines()
                    if line.strip() and not line.startswith('//')]
    checks = dict(
        all_cbuffer_offsets_and_sizes=all(row['matches'] for row in offsets),
        all_resource_slots_and_counts=all(row['matches'] for row in bindings),
        pixel_shader_model_5='ps_5_0' in instructions,
        reflected_single_colour_target=sum(line.startswith('dcl_output') for line in instructions) == 1 and
            'dcl_output o0.xyzw' in instructions,
        typed_integer_plot_resource=any(line.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t3')
            for line in instructions),
        reflected_no_uav_or_depth=not any('dcl_uav' in line or 'oDepth' in line for line in instructions),
    )
    return dict(checks=checks, constants=offsets, resources=bindings)


def terrain_source_contract(shader, types):
    clean = re.sub(r'//[^\n]*', '', shader)
    pixel = clean[clean.index('O pixelMain('):]
    return dict(
        cpu_abi_192='sizeof(OriginalConstants)==192' in types,
        float4_fog_info='float4 fogInfo;' in clean,
        independent_integer_id_output='uint pick:SV_Target1;' in clean,
        exact_tile_state_is_integer='Texture2D<uint2> PlotState : register(t24);' in clean,
        unknown_exits_before_materials=pixel.index('if(state.y==0)return o;') < pixel.index('Diffuse[i].Sample('),
        picking_uses_only_exact_state='o.pick=state.x;' in pixel and pixel.count('o.pick=') == 2,
        separate_post_pass_disables_old_dim='float fog=fogInfo.x>0.5 || state.y==2?1.0:0.30;' in pixel,
        fog_info_used_only_for_colour=clean.count('fogInfo') == 2,
        original_alpha8_weight='W=a4*a4*weights[i]' in pixel,
        original_material_output='o.specularSquared=specularSum/total;o.materialHeight=heightSum/total;' in pixel,
    )


def terrain_reflected_contract(listing):
    expected = [('materials', 0, 128), ('placement', 128, 16), ('mapInfo', 144, 16),
                ('textureOrigin', 160, 16), ('fogInfo', 176, 16)]
    offsets = []
    for name, offset, size in expected:
        match = re.search(r'\b' + name + r'(?:\[8\])?;\s*//\s*Offset:\s*(\d+)\s+Size:\s*(\d+)', listing)
        offsets.append(dict(name=name, expected_offset=offset, expected_size=size,
                            reflected_offset=int(match[1]) if match else None,
                            reflected_size=int(match[2]) if match else None,
                            matches=bool(match and int(match[1]) == offset and int(match[2]) == size)))
    bindings = []
    # FXC expands the unrolled SM5 texture arrays into eight separate bindings.
    expected_bindings = [(f'{name}[{index}]', 't' + str(first + index), 1)
                         for name, first in [('Diffuse', 0), ('HeightMap', 8), ('Specular', 16)]
                         for index in range(8)]
    expected_bindings += [('PlotState', 't24', 1), ('GroundSampler', 's0', 1), ('Chunk', 'cb1', 1)]
    for name, slot, count in expected_bindings:
        matches = [line for line in listing.splitlines() if re.match(r'//\s*' + re.escape(name) + r'\s+', line)
                   and re.search(r'\b' + slot + r'\s+' + str(count) + r'\s*$', line)]
        bindings.append(dict(name=name, slot=slot, count=count, matches=len(matches) == 1))
    instructions = [line.strip() for line in listing.splitlines()
                    if line.strip() and not line.startswith('//')]
    checks = dict(
        all_cbuffer_offsets_and_sizes=all(row['matches'] for row in offsets),
        all_resource_slots_and_counts=all(row['matches'] for row in bindings),
        four_original_mrt_outputs=sum(line.startswith('dcl_output') for line in instructions) == 4,
        integer_target_one=re.search(r'^// SV_Target\s+1\s+x\s+1\s+TARGET\s+uint\s+x\s*$', listing, re.M) is not None,
        typed_integer_plot_resource=any(line.startswith('dcl_resource_texture2d (uint,uint,uint,uint) t24')
            for line in instructions),
        reflected_no_uav_or_depth=not any('dcl_uav' in line or 'oDepth' in line for line in instructions),
    )
    return dict(checks=checks, constants=offsets, resources=bindings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', default='attempt01')
    parser.add_argument('--target', choices=('fog', 'terrain'), default='fog')
    args = parser.parse_args()
    assert re.fullmatch(r'attempt\d{2}', args.attempt), 'Use a fresh numbered owned attempt'
    stage = STAGE_ROOT / args.attempt
    assert not stage.exists(), 'Inspect the existing owned attempt before retrying'
    assert not STAGE_ROOT.is_symlink() and not any(x.is_symlink() for x in stage.parents)
    source_path = SOURCE if args.target == 'fog' else PROJECT / 'Source/Presentation/OriginalTerrainShader.h'
    types_path = GPU_TYPES if args.target == 'fog' else PROJECT / 'Source/Presentation/OriginalTerrainGpuTypes.inc'
    inputs = [ref(path) for path in (source_path, types_path, Path(__file__))]
    source = source_path.read_text('utf8')
    literals = re.findall(r'R"HLSL\((.*?)\)HLSL"', source, re.S)
    assert len(literals) == 1
    shader = literals[0]
    source_checks = (source_contract if args.target == 'fog' else terrain_source_contract)(shader, types_path.read_text('utf8'))
    assert all(source_checks.values()), source_checks
    pin_path = PROJECT / 'evidence/world_terrain_original/terrain_shader_semantics.json'
    pin = json.loads(pin_path.read_text('utf8'))['tool']
    tool = ref(pin['path'])
    assert tool['sha256'] == pin['sha256'] == TOOL_SHA
    stage.mkdir(parents=True)
    write_new(stage / 'started.json', dict(target=args.target, inputs=inputs, compiler=tool, source_checks=source_checks))
    temporary = stage / (args.target + '.hlsl')
    temporary.write_text(shader, encoding='ascii')
    owned = [temporary]
    passes, reflection = [], None
    try:
        for entry, profile, stem in [('vertexMain', 'vs_5_0', 'vertex'), ('pixelMain', 'ps_5_0', 'pixel')]:
            bytecode, listing = stage / (stem + '.cso'), stage / (stem + '.asm')
            owned.append(bytecode)
            command = [tool['path'], '/nologo', '/Ges', '/WX', '/T', profile, '/E', entry,
                       '/Fo', str(bytecode), '/Fc', str(listing), str(temporary)]
            done = subprocess.run(command, cwd=stage, capture_output=True, timeout=90,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            log = (done.stdout + done.stderr).decode('mbcs', errors='replace')
            log_path = stage / (stem + '_compiler.txt')
            log_path.write_text(log, encoding='utf8')
            row = dict(entry=entry, profile=profile, command=command, exit_code=done.returncode,
                       compiler_output=log, log=ref(log_path))
            if bytecode.exists():
                assert bytecode.read_bytes()[:4] == b'DXBC'
                row['bytecode'] = ref(bytecode)
            if listing.exists():
                row['listing'] = ref(listing)
                if profile == 'ps_5_0':
                    reflection = (reflected_contract if args.target == 'fog' else terrain_reflected_contract)(
                        listing.read_text('utf8', errors='replace'))
            passes.append(row)
            if done.returncode:
                break
    finally:
        assert [ref(x['path']) for x in inputs] == inputs, 'Production inputs changed during compile'
        assert ref(pin['path']) == tool, 'Pinned shader compiler changed'
        rows = [ref(path) for path in owned if path.exists()]
        for row in rows:
            path = Path(row['path'])
            assert path.is_relative_to(stage) and not path.is_symlink() and row['links'] == 1
            assert not row['file_attributes'] & 0x401 and ref(path) == row
        write_new(stage / 'cleanup_plan.json', dict(files=rows, protected_inputs=inputs))
        for row in rows:
            path = Path(row['path'])
            assert ref(path) == row
            path.unlink()
        write_new(stage / 'cleanup_result.json', dict(status='PASS_EXACT_SHADER_INTERMEDIATES_REMOVED',
                  files=rows, deleted_files=len(rows), deleted_logical_bytes=sum(x['bytes'] for x in rows),
                  source_or_original_assets_changed=False))
    passed = len(passes) == 2 and all(x['exit_code'] == 0 for x in passes) and reflection is not None and all(reflection['checks'].values())
    result = dict(schema='zerosis.original_fog.phase2.strict_shader.v1',
                  status=('PASS_STRICT_FXC_FOG_ABI_AND_SOURCE_BOUNDARY' if args.target == 'fog' else
                          'PASS_STRICT_FXC_TERRAIN_FOW_ABI_AND_SOURCE_BOUNDARY') if passed else 'FAIL_FOG_SHADER',
                  target=args.target, inputs=inputs, compiler=tool, compiler_pin=ref(pin_path), passes=passes,
                  source_checks=source_checks, reflection=reflection,
                  literal_sha256=hashlib.sha256(shader.encode('ascii')).hexdigest(),
                  cleanup=ref(stage / 'cleanup_result.json'),
                  host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False,
                  graphics_device_created=False, original_gpu_or_image_parity_verified=False)
    write_new(stage / 'result.json', result)
    print(json.dumps(dict(status=result['status'], source_checks=len(source_checks),
                         reflection_checks=len(reflection['checks']) if reflection else 0,
                         passes=[dict(entry=x['entry'], exit_code=x['exit_code'], compiler_output=x['compiler_output']) for x in passes],
                         retained_asm_bytes=sum(x.get('listing', {}).get('bytes', 0) for x in passes),
                         graphics_device_created=False)))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
