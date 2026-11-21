"""Check exact installed policy texture bytes and one captured snapshot's asset coverage."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from civ5_ui_assets import LOOSE_UI_TEXTURES, UiAssets, require, sha256

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
PATCH = 'SocialPolicies_Patch64_Exp2.dds'
PATCH_RELATIVE = 'Assets/DLC/Expansion2/UI/Art/Icons/' + PATCH


def snapshot_textures(snapshot, icons):
    names, tokens = set(), set()

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('texture', 'Texture', 'ButtonTexture') and isinstance(child, str):
                    if child.casefold().endswith('.dds'):
                        names.add(child.replace('\\', '/').rsplit('/', 1)[-1].casefold())
                if key == 'text' and isinstance(child, str):
                    tokens.update(re.findall(r'\[(ICON_[^\]]+)\]', child))
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(snapshot)
    for token in sorted(tokens):
        require(token in icons and isinstance(icons[token].get('texture'), str),
                'Snapshot inline icon lacks its original texture: ' + token)
        walk(icons[token])
    return names, tokens


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--snapshot-sha256', required=True)
    parser.add_argument('--inline-icons', type=Path, required=True)
    parser.add_argument('--evidence-dir', type=Path, required=True)
    args = parser.parse_args()
    snapshot_bytes, icon_bytes = args.snapshot.read_bytes(), args.inline_icons.read_bytes()
    snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
    require(snapshot_hash == args.snapshot_sha256, 'Captured policy snapshot hash differs')
    snapshot = json.loads(snapshot_bytes)
    require(snapshot.get('contextName') == 'SocialPolicyPopup', 'Expected the original policy context')
    names, tokens = snapshot_textures(snapshot, json.loads(icon_bytes)['icons'])
    require(PATCH.casefold() in names, 'Captured policy snapshot does not request the patch atlas')
    source_path = (GAME / PATCH_RELATIVE).resolve(strict=True)
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    assets = UiAssets(GAME)
    require(not any(PATCH.casefold() in pack.entries for pack in assets.packs),
            'Policy patch atlas unexpectedly moved into a priority FPK')
    with tempfile.TemporaryDirectory(prefix='policy-assets-', dir=PROJECT / 'evidence') as folder:
        record = assets.resolve(PATCH, Path(folder) / 'textures')
        require(record['source'] == {'kind': 'loose-ui-texture', 'path': str(source_path),
                'relative_path': PATCH_RELATIVE, 'bytes': len(source_bytes), 'sha256': source_hash},
                'Resolved policy atlas lost its exact original provenance')
        normalized = Path(record['output']['path']).read_bytes()
        require(Path(record['frozen_source']['path']).read_bytes() == source_bytes and
                normalized[128:] == source_bytes[128:] and
                record['index_source'] is None and record['frozen_index'] is None,
                'Policy patch atlas pixels or frozen source changed')
        require(record['conversion'] == {'encoding': 'RGBA32_TOP_MIP_COPY',
                'width': 128, 'height': 64, 'source_mips': 1,
                'pixel_byte_transform': 'COPY_ONLY', 'source_scalable': False},
                'Policy patch atlas is not the inspected 128x64 raw RGBA DDS')
        require(assets.resolve(PATCH.upper(), Path(folder) / 'textures') is record,
                'Policy patch atlas case-insensitive lookup changed')
    coverage = []
    for name in sorted(names):
        packs = [str(pack.path) for pack in assets.packs if name in pack.entries]
        loose = LOOSE_UI_TEXTURES.get(name)
        require(packs or loose, 'Captured policy snapshot has an unresolved original texture: ' + name)
        coverage.append({'basename': name, 'pack_sources': packs, 'loose_source': loose})
    require(assets.unchanged() and source_path.read_bytes() == source_bytes,
            'Original policy texture or priority FPK changed during the check')
    require(args.snapshot.read_bytes() == snapshot_bytes and args.inline_icons.read_bytes() == icon_bytes,
            'Captured policy snapshot or inline icon catalog changed during the check')
    result = {
        'status': 'PASS_SOCIAL_POLICY_EXACT_TEXTURE_AND_SNAPSHOT_COVERAGE_COMPONENT_ONLY',
        'source': record['source'], 'conversion': record['conversion'],
        'output': {key: record['output'][key] for key in ('bytes', 'sha256')},
        'pixels_copied_unchanged': True, 'source_and_packs_unchanged': True,
        'snapshot': {'path': str(args.snapshot.resolve()), 'sha256': snapshot_hash},
        'inline_icons': {'path': str(args.inline_icons.resolve()),
                         'sha256': hashlib.sha256(icon_bytes).hexdigest(), 'used_tokens': sorted(tokens)},
        'texture_basename_count': len(names), 'texture_coverage': coverage,
        'priority_packs': assets.pack_records,
        'implementation_sha256': {'resolver': sha256(PROJECT / 'tools/civ5_ui_assets.py'),
                                  'test': sha256(Path(__file__))},
        'scope': {'exact_patch_atlas_resolved_and_decoded': True,
                  'other_snapshot_textures_index_checked_only': True,
                  'renderer_and_native_game_verified': False},
    }
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    report = args.evidence_dir / 'result.json'
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'report': str(report.resolve()),
                      'source': record['source'], 'conversion': record['conversion'],
                      'texture_basename_count': len(names),
                      'implementation_sha256': result['implementation_sha256']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
