"""Derive the immutable V4 front-end pack from V3: only the four WindowTrim sprites change.

Retail ForgeUI draws an <Image> without StretchMode by sampling Size pixels 1:1
(evidence/game_menu/frontend_windowtrim). V3 resampled the whole 98x394 image
into the authored 82x396. V4 keeps every other V3 byte as an immutable hardlink
and rewrites only the four sprite records with native_default_image_region().
File-only: no Host, SDK, window, GPU or game execution.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
V3 = PROJECT / 'Source/Assets/UIFrontEndV3'
V3_MANIFEST = PROJECT / 'evidence/game_menu/replay_calendar_legend/legend/assets_v3.json'
V3_MANIFEST_SHA = 'eb5408e1aeb55ed8469c2fb313f18beb82eb8bab3c2cc9456f60c3b7a1a3d9a1'
V4 = PROJECT / 'Source/Assets/UIFrontEndV4'
STAGE = PROJECT / 'evidence/game_menu/native_offline_followup/frontend_v4'
MANIFEST = STAGE / 'assets_v4.json'
SCHEMA = 'zerosis.original_frontend.assets.v2'
SPRITE = struct.Struct('<IQ16f')
WINDOWTRIM_KEYS = (114, 116, 117, 119)
OFFLINE = dict(native_execution=False, sdk_loaded=False, host_or_sdk_or_window_executed=False,
               gpu_execution=False, retail_pixel_acceptance=False, native_geometry_verified=False)


def require(value, message):
    if not value:
        raise ValueError(message)


def parse_packet(raw):
    require(raw[:8] == b'ZSUPIX02', 'Not a ZSUPIX02 scene packet')
    width, height, textures, sprites, hits, scrolls = struct.unpack_from('<6I', raw, 8)
    require((width, height, hits, scrolls) == (1920, 1080, 0, 0), 'Unexpected front-end packet header')
    cursor, names = 32, []
    for _ in range(textures):
        size, = struct.unpack_from('<I', raw, cursor)
        cursor += 4
        names.append(raw[cursor:cursor + size].decode('utf8'))
        cursor += size
    rows = []
    for _ in range(sprites):
        rows.append((cursor, SPRITE.unpack_from(raw, cursor)))
        cursor += SPRITE.size
    require(cursor == len(raw), 'Front-end packet has trailing data')
    return names, rows


def main():
    from menu_frontend_options_assets import artifact, hardlink
    from menu_frontend_skin_pages import NATIVE_DEFAULT_IMAGE_EVIDENCE, native_default_image_region
    from menu_replay_legend_assets import seal_private
    from retained_host_runtime_input import _Files
    from retained_menu_suite_host_input import sidecar_source_inventory
    require(not os.path.lexists(V4) and not os.path.lexists(MANIFEST), 'Inspect the existing V4 pack instead of repeating it')
    v3_ref = artifact(V3_MANIFEST)
    require(v3_ref['sha256'] == V3_MANIFEST_SHA, 'Immutable V3 manifest changed')
    files = _Files(check_metadata=True)
    v3_gate = sidecar_source_inventory(PROJECT, V3, v3_ref, SCHEMA, files)
    files.finish()
    require(v3_gate['file_count'] == 154, 'V3 sidecar gate count differs')
    manifest = json.loads(V3_MANIFEST.read_text('utf8'))
    v3_rows = {Path(row['path']).relative_to(V3).as_posix(): row for row in manifest['files']}
    candidates = {row['key']: row for row in manifest['original_image_size_candidates']}
    require(tuple(sorted(candidates)) == WINDOWTRIM_KEYS, 'WindowTrim candidate roster differs')
    evidence = artifact(PROJECT / NATIVE_DEFAULT_IMAGE_EVIDENCE)
    probe = json.loads(Path(evidence['path']).read_text('utf8'))
    require(probe['exe']['sha256'] == 'b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818' and probe['executed'] is False,
            'Native Image mapping evidence differs')
    changed, diffs = {}, []
    for path in sorted(V3.glob('*.packet')):
        raw = bytearray(path.read_bytes())
        names, rows = parse_packet(raw)
        touched = False
        for offset, sprite in rows:
            key = sprite[1]
            if key not in candidates:
                continue
            row = candidates[key]
            basename = row['texture'].replace('\\', '/').rsplit('/', 1)[-1].casefold()
            texture = names[sprite[0]] if sprite[0] < len(names) else ''
            # Sprite keys are page-local; another page reuses these numbers for other controls.
            if Path(texture).name[:8] != hashlib.sha256(basename.encode('utf8')).hexdigest()[:8]:
                continue
            x, y, width, height = row['target_bounds']
            source, target = sprite[2:6], sprite[6:10]
            require(source == (0.0, 0.0, 98.0, 394.0) and target == (x, y, x + width, y + height) and
                    (width, height) == (82.0, 396.0) and tuple(row['source_extent']) == (98, 394) and
                    sprite[10:18] == (0.0, 0.0, 1920.0, 1080.0, 1.0, 1.0, 1.0, 1.0),
                    'V3 WindowTrim sprite differs from its recorded resample candidate')
            region = native_default_image_region((0, 0), (int(width), int(height)), tuple(row['source_extent']))
            drawn_w, drawn_h = region['drawn_size']
            replacement = (sprite[0], key, *map(float, region['source']), x, y, x + drawn_w, y + drawn_h, *sprite[10:18])
            SPRITE.pack_into(raw, offset, *replacement)
            diffs.append(dict(packet=path.name, key=key, texture=texture, before=dict(source=list(source), target=list(target)),
                              after=dict(source=list(replacement[2:6]), target=list(replacement[6:10])),
                              texture_columns_not_drawn=region['texture_columns_not_drawn'],
                              rows_beyond_texture_not_drawn=region['rows_beyond_texture']))
            touched = True
        if touched:
            changed[path.name] = bytes(raw)
    require(sorted(row['key'] for row in diffs) == list(WINDOWTRIM_KEYS) and set(changed) == {'MainMenu.packet', 'SinglePlayer.packet'},
            'WindowTrim sprites were not found exactly once each')
    STAGE.mkdir(parents=True, exist_ok=True)
    V4.mkdir()
    unchanged, written = [], []
    for relative, row in sorted(v3_rows.items()):
        source, target = V3 / relative, V4 / relative
        if relative in changed:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(changed[relative])
            seal_private(target)
            written.append(dict(relative_path=relative, before=dict(bytes=row['bytes'], sha256=row['sha256']),
                                after=dict(bytes=len(changed[relative]), sha256=hashlib.sha256(changed[relative]).hexdigest())))
        else:
            hardlink(source, target)
            require(os.path.samefile(source, target), 'V4 alias is not the exact V3 file')
            unchanged.append(relative)
    v4_files = [artifact(path) for path in sorted(V4.rglob('*')) if path.is_file()]
    require(len(v4_files) == 154 and all(row['file_attributes'] & 1 for row in v4_files), 'V4 pack is incomplete or mutable')
    output = deepcopy(manifest)
    text = json.dumps(output, ensure_ascii=False)
    old_root, new_root = json.dumps(str(V3))[1:-1], json.dumps(str(V4))[1:-1]
    output = json.loads(text.replace(old_root + '\\\\', new_root + '\\\\').replace('"' + old_root + '"', '"' + new_root + '"'))
    require(output['source_root'] == str(V4), 'V4 source root rewrite failed')
    for row in output['original_image_size_candidates']:
        region = native_default_image_region((0, 0), (int(row['target_bounds'][2]), int(row['target_bounds'][3])),
                                             tuple(row['source_extent']))
        row.update(drawn_bounds=[*row['target_bounds'][:2], *region['drawn_size']], source_rectangle=list(region['source']),
                   transform=dict(x_scale_numerator=1, x_scale_denominator=1, y_scale_numerator=1, y_scale_denominator=1),
                   texture_columns_not_drawn=region['texture_columns_not_drawn'],
                   rows_beyond_texture_not_drawn=region['rows_beyond_texture'],
                   rows_beyond_texture_policy='NOT_DRAWN_RETAIL_SAMPLER_AND_FTXT_SHADER_RESULT_UNPROVEN',
                   sampling='CURRENT_PRESENTER_SAMPLING_1TO1_RETAIL_DEFAULT_SAMPLER_INDEX_10',
                   policy='ORIGINAL_DEFAULT_IMAGE_SIZE_PIXELS_1TO1_FROM_TEXTURE_OFFSET',
                   native_mapping_evidence=NATIVE_DEFAULT_IMAGE_EVIDENCE, retail_texture_stretch_verified=True,
                   native_uv_and_scaling_parity_unresolved=False)
    output.update(OFFLINE, schema=SCHEMA, source_root=str(V4),
                  pack_revision='ACTIVE_EXPANSION2_COMMON_SKIN_CURRENT_14PX_LEGEND_NATIVE_WINDOWTRIM_V4',
                  immutable_v3_manifest=v3_ref, original_v3_preserved=True,
                  unchanged_v3_hardlink_count=len(unchanged), unchanged_v3_relative_paths=unchanged,
                  changed_v3_relative_paths=written, windowtrim_sprite_changes=diffs,
                  native_image_mapping_evidence=evidence, files=v4_files)
    raw = (json.dumps(output, indent=2, ensure_ascii=False) + '\n').encode('utf8')
    with MANIFEST.open('xb') as stream:
        stream.write(raw)
    seal_private(MANIFEST)
    files = _Files(check_metadata=True)
    v4_gate = sidecar_source_inventory(PROJECT, V4, artifact(MANIFEST), SCHEMA, files)
    files.finish()
    files = _Files(check_metadata=True)
    v3_after = sidecar_source_inventory(PROJECT, V3, v3_ref, SCHEMA, files)
    files.finish()
    require(v4_gate['file_count'] == 154 and v3_after['file_count'] == 154, 'V4 or preserved V3 gate failed')
    proof = dict(schema='zerosis.frontend_v4.preflight.v1', **OFFLINE, manifest=artifact(MANIFEST), v3_manifest=v3_ref,
                 file_count=v4_gate['file_count'], unchanged_hardlinks=len(unchanged), changed_files=written,
                 windowtrim_sprite_changes=diffs, v3_gate_after=dict(file_count=v3_after['file_count'], unchanged=True),
                 new_payload_bytes=sum(row['after']['bytes'] for row in written))
    with (STAGE / 'frontend_v4_preflight.json').open('x', encoding='utf8') as stream:
        json.dump(proof, stream, indent=2)
        stream.write('\n')
    return proof


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    result = main()
    print(json.dumps(dict(status='PASS_NATIVE_WINDOWTRIM_V4_FRONTEND_PACK_PREPARED_NOT_EXECUTED',
                          manifest=result['manifest']['path'], manifest_sha256=result['manifest']['sha256'],
                          files=result['file_count'], hardlinks=result['unchanged_hardlinks'],
                          changed=[row['relative_path'] for row in result['changed_files']], **OFFLINE)))
