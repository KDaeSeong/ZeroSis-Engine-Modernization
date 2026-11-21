"""Observe a fixed public corpus at a verified Map boundary, without scanning."""
from __future__ import annotations
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require
from verify_retail_save_state import public_input, OUTPUT_SHA
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT/'evidence/retail_save_container/post_map'


def main():
    require(len(sys.argv) == 1, 'Unexpected observation invocation')
    source = PROJECT/'evidence/retail_save_container/map_state/build_result.json'
    require(artifact(source)['sha256'] == '0b3c0ff058dff74df9e1a47bf742ca45370eac6cd80de50ba8c169c5ba50ddd7',
            'Verified Map evidence changed')
    proof = json.loads(source.read_text(encoding='utf-8'))
    public = public_input()
    row = proof['results'][0]['test']['public']
    require(row == proof['results'][1]['test']['public'] and row['next_inflated_offset'] == 1695150,
            'Map boundary changed')
    begin, plots = row['next_inflated_offset'], row['plot_count']
    candidate_end = begin+276+4*plots
    def word(offset):
        require(0 <= offset <= len(public)-4, 'Observation escaped public bytes')
        return struct.unpack_from('<I', public, offset)[0]
    observed = dict(status='OBSERVED_PUBLIC_POST_MAP_NOT_LAYOUT_APPROVAL', map_component=artifact(source),
        public_input_bytes=len(public), public_inflated_sha256=OUTPUT_SHA, map_end=begin,
        following_words=list(struct.unpack_from('<16I', public, begin)),
        supporting_candidate=dict(start=begin, plot_count=plots, bytes=276+4*plots, end=candidate_end,
            parent_version_word=word(begin), barbarians_version_word=word(begin+4),
            goody_huts_version_word=word(begin+8+4*plots),
            next_word=word(candidate_end), next_team_id_position_word=word(candidate_end+128)),
        boundaries_scanned=False, private_archive_order_used_as_oracle=False,
        supporting_placement_verified=False, sdk_state_restored=False,
        whole_container_or_original_save_write_verified=False, public_body_retained=False,
        host_gamecore_or_hwnd_executed=False, user_saves_accessed=False)
    STAGE.mkdir(exist_ok=True)
    (STAGE/'boundary_probe.json').write_text(json.dumps(observed,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(observed))


if __name__ == '__main__':
    main()
