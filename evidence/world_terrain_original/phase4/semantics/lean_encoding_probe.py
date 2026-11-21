"""Read-only LEAN word/covariance diagnostics; no original asset extraction."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
STAGE=Path(__file__).absolute().parent
PROJECT=STAGE.parents[3]
sys.path.insert(0,str(PROJECT/'tools'))
from civ5_ui_assets import Fpk
from civ5_original_water_assets import validate_lean


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    inventory=json.loads((PROJECT/'evidence/world_terrain_original/asset_inventory.json').read_text('utf8'))
    path=Path(inventory['game_root'])/'Resource/Common/TerrainModels.fpk'
    expected=inventory['packs']['Resource/Common/TerrainModels.fpk']['sha256']
    assert sha(path)==expected
    pack=Fpk(path);rows=[]
    for name in ['waterbumps16.lean','riverrough16.lean','riversmooth16.lean']:
        raw,meta=pack.read(name);info=validate_lean(raw);levels=[]
        assert info['bytes_per_channel']==2
        for first,second in zip(info['planes'][0]['levels'],info['planes'][1]['levels']):
            count=first['width']*first['height'];step=max(1,count//4096)
            means=[[],[]];variances=[[],[],[]];half_finite=0;half_nonfinite=0;sample_count=0
            for index in range(0,count,step):
                offset=first['offset']+index*8;cross_offset=second['offset']+index*2
                words=struct.unpack_from('<4H',raw,offset);cross=struct.unpack_from('<H',raw,cross_offset)[0]
                r,g,b,a=[value/65535 for value in words];xy=cross/65535
                mx,my=2*r-1,2*g-1
                means[0].append(mx);means[1].append(my)
                variances[0].append(b-mx*mx);variances[1].append(a-my*my);variances[2].append((2*xy-1)-mx*my)
                half=struct.unpack_from('<4e',raw,offset)+struct.unpack_from('<e',raw,cross_offset)
                if all(math.isfinite(value) for value in half):half_finite+=1
                else:half_nonfinite+=1
                sample_count+=1
            levels.append(dict(level=first['level'],sampled=sample_count,
                mean_xy_range=[[min(values),max(values)] for values in means],
                unorm_covariance_range=[[min(values),max(values)] for values in variances],
                unorm_diagonal_below_minus_3e5=[sum(value< -3e-5 for value in values) for values in variances[:2]],
                float16_interpretation_nonfinite_samples=half_nonfinite,float16_interpretation_finite_samples=half_finite))
        rows.append(dict(member=meta,output_scale=info['output_scale'],shape=[info['width'],info['height'],info['mips']],
                         flags=info['flag_at32'],levels=levels))
    commands=[]
    for name in ['run_water.bat','make_river_lean.bat']:
        raw,meta=pack.read(name);commands.append(dict(member=meta,text=raw.decode('latin1')))
    assert sha(path)==expected
    result=dict(schema='zerosis.original_water.phase4.lean_encoding_diagnostic.v1',
        status='PASS_READ_ONLY_WORD_AND_COVARIANCE_DIAGNOSTIC',pack=dict(path=str(path),sha256=expected),
        assets=rows,generator_command_evidence=commands,
        direct_shader_sample_decode='Given shader float samples, mean=(2R-1,2G-1); diagonal moments=(B,A); cross moment=2*plane1.R-1. Mirroring X negates mean.x and cross moment only.',
        proposed_gpu_views='R16G16B16A16_UNORM plus R16_UNORM, with original words/mips retained; this is an inference from16-bit linear output, encoded values and consumer arithmetic.',
        certainty_boundary=['The raw bytes and generator commands are pinned. This probe does not execute LeanMaker or the original loader.',
            'Original DXGI/D3D texture-format upload code is not traced; use the proposed UNORM views as an explicit compatibility inference.',
            'Header output_scale corresponds to the batch argument, but its assignment to shader cb1[13].x is not proven.',
            'Quantised second moments can produce tiny negative diagonal covariance; GPU stabilisation thresholds are separate policies.'],
        raw_asset_bytes_written=0,host_gamecore_clr_hwnd_gpu_audio_or_game_executed=False)
    with (STAGE/'lean_encoding.json').open('x',encoding='utf8') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=result['status'],assets=len(rows),levels=sum(len(row['levels']) for row in rows),
        sampled=sum(level['sampled'] for row in rows for level in row['levels']),asset_bytes_written=0)))


if __name__=='__main__':main()
