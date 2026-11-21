"""Record the WindowTrim native-mapping proof; implementation is deferred by user decision (file-only).

usage: python -B -X utf8 record.py backup|publish
"""
from __future__ import annotations
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
SHARED = ['docs/CLAUDE_HANDOFF.md', 'docs/ORIGINAL_MENUS_OFFLINE.md',
          'evidence/save_menu/20261013_original_screen/current_progress.json']
OLD_LIMIT = 'Four WindowTrim candidates (82x396 trim versus the 394px texture) remain open; native UV/scaling is unproved.'
NEW_LIMIT = ('WindowTrim native mapping is proven (default Image samples Size pixels 1:1; the 98x394 BNW art is cropped to 82 columns), '
             'but the V3 pack still uses the full-image resample candidate until the next front-end pack revision; '
             'the 2 rows read beyond the image (sampler address mode) remain unproven.')


def ref(path):
    raw = Path(path).read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def write_new(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def backup():
    rows = []
    for name in SHARED:
        raw = (PROJECT / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        target = STAGE / 'source_before' / (name.replace('/', '__') + '.' + digest[:16] + '.gz')
        target.parent.mkdir(exist_ok=True)
        with target.open('xb') as stream:
            stream.write(gzip.compress(raw, mtime=0))
        assert hashlib.sha256(gzip.decompress(target.read_bytes())).hexdigest() == digest
        rows.append(dict(path=name, bytes=len(raw), sha256=digest, backup=str(target.relative_to(PROJECT)).replace('\\', '/')))
    write_new(STAGE / 'source_before.json', dict(changed_file_backups=rows, full_project_copy=False))
    print(json.dumps(dict(status='SHARED_RECORDS_KEPT', backups=len(rows))))


def publish():
    probe = json.loads((STAGE / 'retail_image_probe.json').read_text('utf8'))
    facts = json.loads((STAGE / 'texture_facts.json').read_text('utf8'))
    assert probe['exe']['sha256'] == 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818' and probe['executed'] is False
    assert len(facts['candidates']) == 4
    current = dict(
        schema='zerosis.frontend_windowtrim.current_work.v1', utc=datetime.now(timezone.utc).isoformat(),
        status='PASS_WINDOWTRIM_NATIVE_MAPPING_RECORDED_IMPLEMENTATION_DEFERRED',
        user_decision='2026-11-07: record the evidence only; apply with the next front-end asset pack revision.',
        proofs=dict(retail_static_probe=ref(STAGE / 'retail_image_probe.json'), texture_facts=ref(STAGE / 'texture_facts.json'),
                    findings=ref(STAGE / 'findings.json')),
        native_mapping=probe['image_control']['semantics'],
        windowtrim=dict(probe['windowtrim'], textures={name: dict(active_layer=value['active_layer'],
                        active_size=[value['active']['width'], value['active']['height']],
                        opaque_texels_not_drawn=value['active']['opaque_texels_in_columns_not_drawn'],
                        layer_sizes={layer['layer']: [layer.get('width'), layer.get('height')] for layer in value['layers']})
                        for name, value in facts['textures'].items()}),
        next_pack_revision_change=[
            'Replace the four WindowTrim full-image resample candidates (keys 114, 116, 117, 119) with source (0,0)-(82,394) drawn 1:1 at the XML position.',
            'Record the 2 rows beyond the 394-row image as unproven (do not fabricate them) until the sampler/FTXT shader path is established.',
            'Regenerate the immutable front-end pack as a new revision, retarget its consumers, and re-run the Host/sidecar/prepared-runtime cycle.'],
        current_pack_unchanged=True, host_or_runtime_rebuilt=False, native_execution=False,
        full_engine_goal_complete=False)
    write_new(STAGE / 'current_work.json', current)
    path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    progress = json.loads(path.read_text('utf8'))
    progress['limits'] = [NEW_LIMIT if line == OLD_LIMIT else line for line in progress.get('limits', [])]
    assert NEW_LIMIT in progress['limits']
    progress['frontend_windowtrim_stage'] = dict(status=current['status'], record=ref(STAGE / 'current_work.json'),
                                                 user_decision=current['user_decision'])
    path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(status=current['status'], record=str(STAGE / 'current_work.json'))))


if __name__ == '__main__':
    commands = dict(backup=backup, publish=publish)
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit(__doc__)
    commands[sys.argv[1]]()
