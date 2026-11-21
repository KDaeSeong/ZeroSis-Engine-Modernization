"""Compile reconstructed forest and terrain HS/DS without creating a device."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parent
PROJECT = ROOT.parents[3]
sys.path.insert(0, str(PROJECT / 'Tests'))
from original_water_shader import ref, write_new


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--attempt',required=True)
    args=cli.parse_args()
    assert re.fullmatch(r'shader\d{2}',args.attempt)
    stage = ROOT / args.attempt
    assert not stage.exists()
    stage.mkdir()
    compiler = Path(r'C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\fxc.exe')
    assert ref(compiler)['sha256'] == 'ced7c1f95e4dffb614971826625e70da6d24aff1b4f2a3ae5952939c9547d7e6'
    protected = [ref(compiler), ref(Path(__file__).absolute())]
    protected += [ref(PROJECT/'Source/Presentation'/name) for name in ('OriginalForestShader.h','OriginalTerrainTessellationShader.h')]
    write_new(stage/'started.json',dict(inputs=protected,native_execution=False))
    owned, passes = [], []
    requirements = {
        'ForestShader_0_vs.asm.txt': ['dcl_constantbuffer CB7[90], dynamicIndexed',
            'mad r0.yzw, v0.xxyz, cb7[r0.x + 0].wwww, cb7[r0.x + 0].xxyz'],
        'ForestShader_0_ps.asm.txt': ['lt r1.x, r0.w, l(0.100000)',
            'l(-0.147130, -0.288860, 0.436000, 0.000000)',
            'l(0.615000, -0.514990, -0.100010, 0.000000)',
            'mad r1.x, r1.y, -r1.x, r1.x', 'mov o0.w, r0.w'],
        'TerrainShader_0_hs.asm.txt': ['dcl_input_control_point_count 16',
            'dcl_output_control_point_count 16', 'dcl_tessellator_domain domain_quad',
            'dcl_tessellator_partitioning partitioning_integer',
            'dcl_tessellator_output_primitive output_triangle_ccw', 'mov o[r0.x + 0].x, cb1[14].x',
            'mov o[r0.x + 4].x, cb1[14].x'],
        'TerrainShader_0_ds.asm.txt': ['dcl_input_control_point_count 16',
            'mul r2.xyzw, r0.xxxx, cb1[11].xyzw', 'mad r2.xyzw, cb1[10].xyzw, r3.xxxx, r2.xyzw',
            'dp4 r2.x, cb1[10].xyzw, r1.xyzw', 'dp4 r2.w, cb1[13].xyzw, r1.xyzw']}
    semantics = []
    for name, literals in requirements.items():
        path = ROOT / name
        text = path.read_text('ascii')
        assert all(line in text for line in literals), name
        semantics.append(dict(original_disassembly=ref(path), required_original_instructions=literals))
        protected.append(ref(path))
    try:
        for label, source_name, entries in (
            ('forest', 'OriginalForestShader.h', [('vertexMain','vs_5_0'),('pixelMain','ps_5_0')]),
            ('tessellation', 'OriginalTerrainTessellationShader.h', [('vertexMain','vs_5_0'),('hullMain','hs_5_0'),('domainMain','ds_5_0')])):
            source = PROJECT / 'Source/Presentation' / source_name
            protected.append(ref(source))
            literals = re.findall(r'R"HLSL\((.*?)\)HLSL"', source.read_text('utf8'), re.S)
            assert len(literals) == 1
            shader = stage / (label + '.hlsl')
            shader.write_text(literals[0], encoding='ascii')
            owned.append(shader)
            for entry, profile in entries:
                output = stage / (label + '_' + entry + '.cso')
                assembly = stage / (label + '_' + entry + '.asm.txt')
                owned.append(output)
                command = [str(compiler),'/nologo','/Ges','/WX','/T',profile,'/E',entry,
                           '/Fo',str(output),'/Fc',str(assembly),str(shader)]
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, check=False, timeout=30,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                log = (result.stdout + result.stderr).decode('mbcs')
                (stage / (label + '_' + entry + '.log')).write_text(log, encoding='utf8')
                assert result.returncode == 0 and not re.search(r'\b(?:error|warning)\s+[A-Z]?\d+',log,re.I), log
                listing = assembly.read_text('ascii')
                assert profile in listing and not any(word in listing for word in ('dcl_uav','oDepth'))
                if profile=='hs_5_0':
                    assert all(line in listing for line in ('partitioning_integer','output_triangle_ccw','dcl_output_control_point_count 16'))
                if label=='forest' and profile=='ps_5_0':
                    assert 'dcl_output o0.xyzw' in listing and not re.search(r'dcl_output o[1-9]',listing)
                passes.append(dict(source=ref(source),entry=entry,profile=profile,command=command,
                    return_code=0,warnings=0,assembly=ref(assembly),bytecode_before_cleanup=ref(output)))
        assert all(ref(row['path'])==row for row in protected)
        write_new(stage/'result.json',dict(status='PASS_STRICT_FOREST_AND_BICUBIC_SHADER_COMPONENTS',
            passes=passes,original_semantics=semantics,protected_inputs=protected,
            production_forest_submission_enabled=False,production_hs_ds_enabled=False,
            unresolved=['original compressed GR2 decode and placement stream','actual CPU-uploaded basis and patch world scale','original world camera calibration'],
            native_host_sdk_clr_hwnd_gpu_audio_or_game_executed=False))
    finally:
        rows = [ref(p) for p in owned if p.exists()]
        write_new(stage/'cleanup_plan.json',dict(files=rows,exact_owned_leaves_only=True))
        for row in rows:
            path=Path(row['path'])
            assert path.parent==stage and path.resolve().is_relative_to(ROOT.resolve())
            assert row['links']==1 and not row['file_attributes']&0x401 and ref(path)==row
            path.unlink()
        write_new(stage/'cleanup_result.json',dict(status='PASS_EXACT_OWNED_SHADER_INTERMEDIATES_REMOVED',
            deleted_files=len(rows),released_unique_allocated_bytes=sum(row['allocated_bytes'] for row in rows),files=rows))
    print(json.dumps(dict(status='PASS_STRICT_FOREST_AND_BICUBIC_SHADER_COMPONENTS',passes=len(passes),warnings=0)))


if __name__=='__main__':
    main()
