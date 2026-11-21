"""Record the fog math contract and remove only this task's failed CPU intermediates."""
from __future__ import annotations
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[4]
sys.path.insert(0,str(PROJECT/'tools'))
from build_exit_confirm_host import artifact
from menu_suite_storage import storage
HERE=Path(__file__).absolute().parent


def write_new(path,value):
    with path.open('x',encoding='utf8',newline='\n') as stream:
        json.dump(value,stream,indent=1,ensure_ascii=False);stream.write('\n')


def sequence(text,wanted):
    lines=[line.strip() for line in text.splitlines() if line.strip() and not line.startswith('//')]
    return any(lines[at:at+len(wanted)]==wanted for at in range(len(lines)-len(wanted)+1))


def main():
    subset=json.loads((HERE/'bytecode/result.json').read_text('utf8'))
    ps=(HERE/'bytecode/TerrainShader_0_ps.asm').read_text('utf8')
    formulas=[
        ['sample_indexable(texture2d)(float,float,float,float) r1.xyz, v2.zwzz, t5.xyzw, s5',
         'add r0.xyz, r0.xyzx, -r1.xyzx',
         'sample_indexable(texture2d)(float,float,float,float) r2.xy, v3.xyxx, t4.xzyw, s4',
         'mad r0.xyz, r2.xxxx, r0.xyzx, r1.xyzx',
         'mad r0.w, r2.y, -r2.x, r2.x',
         'sample_indexable(texture3d)(float,float,float,float) r1.xyz, r0.xyzx, t6.xyzw, s6',
         'add r1.xyz, -r0.xyzx, r1.xyzx',
         'mad r0.xyz, r0.wwww, r1.xyzx, r0.xyzx'],
        ['add r2.xyz, v4.xyzx, -cb1[19].xyzx', 'mul r0.w, r2.z, cb2[1].x',
         'mul r0.w, r0.w, l(1.442695)', 'exp r0.w, r0.w',
         'add r0.w, -r0.w, l(1.000000)', 'dp3 r1.w, r2.xyzx, r2.xyzx',
         'mul r1.w, r1.w, cb2[1].y', 'mul r0.w, r0.w, r1.w',
         'div r0.w, r0.w, r2.z', 'mul r0.w, r0.w, l(1.442695)',
         'exp r0.w, r0.w', 'min r0.w, r0.w, l(1.000000)',
         'add r0.w, -r0.w, l(1.000000)'],
        ['mad r2.x, v5.y, l(0.500000), l(0.500000)', 'mov r2.y, cb2[1].w',
         'sample_indexable(texture2d)(float,float,float,float) r1.w, r2.xyxx, t2.yzwx, s2',
         'mul r0.w, r0.w, r1.w', 'mad o0.xyz, r0.wwww, r1.xyzx, r0.xyzx']]
    assert all(sequence(ps,wanted) for wanted in formulas)
    reference=subset['shaders'][0]['retail_blob'];exe=Path(subset['exe']['path'])
    assert artifact(exe)==subset['exe']
    with exe.open('rb') as stream:
        stream.seek(int(reference['file_offset'],16));blob=stream.read(reference['bytes'])
    cbytes=struct.pack('<f',1.442695)
    assert blob.count(cbytes)==2
    cleanup=[]
    for name in ('cpu','cpu_retry01'):
        stage=HERE/name;build=stage/'build';assert build.is_dir()
        rows=[]
        for path in sorted(build.iterdir()):
            assert path.is_file() and path.suffix in ('.exe','.obj','.map','.rsp','.cmd','.h')
            row=dict(artifact(path),allocated_bytes=storage.allocated(path))
            assert row['links']==1 and not row['file_attributes']&0x401
            rows.append(row)
        assert {Path(row['path']).name for row in rows}=={
            'read_build_environment.cmd','compile.rsp','original_fog_golden.h',
            'original_fog_model.exe','original_fog_model.obj','original_fog_model.map'}
        write_new(stage/'cleanup_plan.json',dict(directory=str(build),files=rows,
            kept_evidence=['started.json','console.txt','imports.txt','compile_original_fog_model_x64_cxx14.txt'],
            failure='Test asserted zero error for float lerp returning 0.099999994 instead of 0.100000001; source test tolerance corrected to 1e-6.'))
        for row in rows:
            path=Path(row['path']);assert path.is_relative_to(build)
            actual=artifact(path)
            assert all(actual[key]==row[key] for key in ('bytes','sha256','file_identity','mtime_ns','file_attributes','links'))
            path.unlink()
        assert not any(build.iterdir());build.rmdir()
        result=dict(status='PASS_REMOVED_OWNED_FAILED_CPU_INTERMEDIATES',files=rows,
            deleted_files=len(rows),deleted_logical_bytes=sum(row['bytes'] for row in rows),
            released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows))
        write_new(stage/'cleanup_result.json',result);cleanup.append(artifact(stage/'cleanup_result.json'))
    record=dict(schema='zerosis.original_fog.math_contract.v1',status='PASS_CPU_REFERENCE_ONLY',
        production_header=artifact(PROJECT/'Source/Presentation/OriginalFogModel.h'),
        controlled_result=artifact(HERE/'cpu_retry03/result.json'),bytecode_subset=artifact(HERE/'bytecode/result.json'),
        checked_instruction_sequences=len(formulas),
        confirmed_shader_operations=dict(
            replacement_mix='C0 = replacement + R * (terrain - replacement)',
            colour_amount='A = R * (1 - B)',
            colour_lut_coordinate='C0.rgb directly, no half-texel or colour-space conversion in this pass',
            colour_mix='C1 = C0 + A * (LUT(C0.rgb) - C0)',
            delta='world.xyz - camera.xyz; retail Z is up',
            distance_exponent='t = (1 - exp2(delta.z * heightK * c)) * dot(delta,delta) * density / delta.z',
            distance_mix='fog = (1 - min(exp2(t * c),1)) * rampRed; C2 = C1 + fog * (FogColor - C1)',
            c_float32=struct.unpack('<f',cbytes)[0],c_bytes_le=cbytes.hex(),c_occurrences=blob.count(cbytes),
            ramp_coordinate='(interpolated screenNdcY * 0.5 + 0.5, runtime row)',
            ramp_channel='R: sample target is r1.w, resource swizzle t2.yzwx maps that destination to original X/R',
            cloud_cutoff='FOWParticleShader/FOWBaseLayer discard on original mask G < 0.01; alpha = G * source alpha'),
        model_safety_policies=dict(
            unknown='exactRevealed=false bypasses terrain, smoothed mask and LUT inputs; replacement RGB and alpha 1 returned',
            zero_height_delta='Continuous limit t = -heightK * ln(2) * c * dot(delta,delta) * density; retail shader divides 0/0 here',
            physical_domain='Finite nonnegative heightK and density; ramp samples clamped to [0,1]',
            coordinate_bounds='World coordinates +/-1,000,000; time +/-1,000,000,000 seconds',
            map_bound='Axis 256, cells 16384; mask 4M texels; vertical wrap requires even height'),
        candidates=dict(
            mask='R=explored/B=visible/G=1-R from use; original CPU write meanings and target resolution not confirmed',
            raster='16 texels per hex, texel-centre nearest ownership, separable [1,4,6,4,1]/16 blur; state booleans only',
            sampling='Normalized texel-centre linear clamp for LUT; configurable clamp/repeat 2D; retail sampler states unconfirmed',
            cloud_flow='Three fixed scale/speed/phase layers driven only by supplied time, not the retail FluidFOW/flowfield equation',
            runtime_values='heightK, density, ramp row and retail camera coordinate calibration not recovered here',
            colour_space='CPU pass consumes caller colour values; upstream CacheBake/display gamma parity is not claimed'),
        excluded='Picking IDs are outside this model; no terrain, material, height, seed or device fields in Grid/Cell',
        failed_attempt_cleanup=cleanup,host_sdk_clr_hwnd_gpu_audio_or_game_executed=False,
        report_label='Shader operations reconstructed; whole effect and screen parity unverified')
    write_new(HERE/'model_contract.json',record)
    print(json.dumps(dict(status=record['status'],equation_sequences=len(formulas),
        current_result=record['controlled_result']['path'],cleaned_failed_attempts=len(cleanup))))


if __name__=='__main__':main()
