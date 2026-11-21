"""Inspect one exact sequential public boundary; never scan for a player tag."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require
from verify_retail_save_state import public_input, OUTPUT_SHA

PROJECT = Path(__file__).absolute().parents[1]


def main():
    require(len(sys.argv) == 1, 'Unexpected boundary probe arguments')
    stage = PROJECT/'evidence/retail_save_container/player_prefix'
    target = stage/'boundary_probe.json'
    require(not target.exists(), 'Inspect retained Player-boundary observation before repeating')
    proof_path = PROJECT/'evidence/serialization/type_array_count/build_result.json'
    require(artifact(proof_path)['sha256'] == '14c0edb33f21c2b2f95bb5db5a2a5374e44a064b66e70b4ab57253b6d44bbba7', 'Team witness identity changed')
    proof = json.loads(proof_path.read_text(encoding='utf-8'))
    for row in proof['inputs']:
        require(artifact(row['path']) == row, 'Team witness input changed')
    one = proof['results'][1]['public_probe']['result']['public']
    require(one == proof['results'][2]['public_probe']['result']['public'] and one['team_count'] == 64, 'Team modes disagree')
    public = public_input()
    require(hashlib.sha256(public).hexdigest() == OUTPUT_SHA, 'Authenticated public RAM input changed')
    start = one['teams_end']
    require(start == 2309550 and start+876 <= len(public), 'Unexpected exact Team boundary')
    sources = [artifact(PROJECT/name) for name in (
        'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvPlayer.cpp',
        'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvPlayerAI.cpp',
        'Source/SDK_BNW_x64/FirePlace/include/FireWorks/FStlContainerSerialization.h')]
    result = dict(schema='zerosis.retail_save.post_team_boundary.v1', status='FIXED_BOUNDARY_OBSERVATION_ONLY',
        utc=datetime.now(timezone.utc).isoformat(), script=artifact(Path(__file__).absolute()),
        team_proof=artifact(proof_path), source_evidence=sources, input_bytes=len(public), input_sha256=OUTPUT_SHA,
        inflated_offset=start, first_16_i32=list(struct.unpack_from('<16i', public, start)),
        byte_values_at_relative_840=list(public[start+840:start+864]),
        i32_at_relative_864=struct.unpack_from('<i', public, start+864)[0],
        i32_at_relative_868=struct.unpack_from('<i', public, start+868)[0],
        u32_at_relative_872=struct.unpack_from('<I', public, start+872)[0],
        scanning_performed=False, player_structure_framed=False, ruleset_compatibility_verified=False,
        complete_save_validated=False, sdk_restore_verified=False, host_gamecore_or_hwnd_executed=False,
        original_install_or_user_saves_accessed=False, public_save_or_body_retained=False, full_engine_goal_complete=False)
    stage.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=result['status'], offset=start, first_16_i32=result['first_16_i32'],
        id_candidate=result['i32_at_relative_864'], first_vector_count_candidate=result['u32_at_relative_872'], report=artifact(target))))


if __name__ == '__main__':
    main()
