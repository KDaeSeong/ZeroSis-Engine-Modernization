"""Seal selected font inputs and share lossless generated glyph tables."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

PROJECT = Path(__file__).absolute().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
PROFILE_PATH = PROJECT / 'Source/Assets/UI/font_input_profile.json'
FONT_IDS = ('TwCenMT14', 'TwCenMT16', 'TwCenMT18', 'TwCenMT20', 'TwCenMT22', 'TwCenMT24')
PROFILE_SCHEMA = 'zerosis.ui.font_input_profile.v1'
BANK_SCHEMA = 'zerosis.ui.shared_font_metrics.v1'
STORAGE_TAG = 'ZEROSIS_UI_SHARED_GLYPH_SETS_V1'
TRANSPORT_FIELDS = ('glyphSetStorage', 'sharedProfileId', 'glyphSetRefs')
GLYPH_FIELDS = {'advance', 'width', 'height', 'originX', 'originY'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def artifact(path):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path, 'Font input path is not canonical')
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and not before.st_file_attributes & 0x400, 'Font input is not an ordinary file')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Font input changed while hashing')
    return dict(path=str(path), bytes=after.st_size, sha256=sha)


def profile_identity(profile):
    payload = {key: value for key, value in profile.items() if key != 'profile_id'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()


def capture_profile(game_root=GAME):
    from ui_bitmap_fonts import load_font
    game_root = Path(game_root).absolute()
    fonts = {}
    colors = None
    for font_id in FONT_IDS:
        font = load_font(game_root, font_id)
        ggxml = artifact(font.ggxml_path)
        require(ggxml['sha256'] == font.ggxml_sha256, 'Font changed after it was parsed')
        current_colors = artifact(font.color_atlas_path)
        require(current_colors['sha256'] == font.color_atlas_sha256 and
                (colors is None or colors == current_colors), 'Font color source changed')
        colors = current_colors
        textures = {}
        for alias, sheet in sorted(font.sheets.items()):
            row = artifact(sheet.path)
            require(row['sha256'] == sheet.sha256 and row['bytes'] == sheet.size, 'Font atlas changed after parsing')
            textures[alias] = row
        fonts[font_id] = dict(ggxml=ggxml, glyph_count=len(font.glyphs), textures=textures)
    profile = dict(schema=PROFILE_SCHEMA, asset_root=str(game_root), fonts=fonts, color_atlas=colors)
    profile['profile_id'] = profile_identity(profile)
    verify_profile_inputs(profile, game_root)
    return profile


def verify_profile_inputs(profile, game_root=GAME):
    game_root = Path(game_root).absolute()
    require(type(profile) is dict and set(profile) == {'schema', 'asset_root', 'fonts', 'color_atlas', 'profile_id'} and
            profile['schema'] == PROFILE_SCHEMA and profile['asset_root'] == str(game_root) and
            is_sha(profile['profile_id']) and profile_identity(profile) == profile['profile_id'], 'Invalid font input profile')
    require(type(profile['fonts']) is dict and set(profile['fonts']) == set(FONT_IDS), 'Font profile has the wrong selected font set')
    rows = [profile['color_atlas']]
    for font_id, font in profile['fonts'].items():
        require(type(font) is dict and set(font) == {'ggxml', 'glyph_count', 'textures'} and
                type(font['glyph_count']) is int and font['glyph_count'] > 0 and type(font['textures']) is dict and font['textures'],
                'Malformed selected font profile')
        require(Path(font['ggxml']['path']) == game_root / 'Assets/UI/Fonts/Tw Cent MT' / (font_id + '.ggxml'), 'Font definition escaped its selected original path')
        rows.extend((font['ggxml'], *font['textures'].values()))
    require(Path(profile['color_atlas']['path']) == game_root / 'Assets/UI/ColorAtlas.xml', 'Font colors escaped their selected original path')
    unique = {}
    for row in rows:
        require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and is_sha(row['sha256']) and
                type(row['bytes']) is int and row['bytes'] > 0 and Path(row['path']).is_absolute() and
                Path(row['path']).is_relative_to(game_root), 'Font profile contains an invalid source reference')
        key = os.path.normcase(row['path'])
        require(key not in unique or unique[key] == row, 'Font profile aliases different input identities')
        unique[key] = row
    for row in unique.values():
        require(artifact(row['path']) == row, 'Installed font input differs from the sealed profile: ' + Path(row['path']).name)
    return list(unique.values())


def profile_input_root(path=PROFILE_PATH):
    path = Path(path)
    require(path.stat().st_size <= 256 * 1024, 'Font profile manifest exceeds its bound')
    profile = json.loads(path.read_text(encoding='utf-8'))
    require(type(profile) is dict and profile.get('schema') == PROFILE_SCHEMA and
            profile.get('profile_id') == profile_identity(profile), 'Invalid font input profile identity')
    root = Path(profile.get('asset_root', ''))
    parent = PROJECT / 'Build/SharedUiFontInputs'
    require(root.is_absolute() and root.parent == parent and re.fullmatch('[0-9a-f]{64}', root.name),
            'Production fonts must use the selected engine-owned cache')
    require(root.resolve(strict=True) == root and parent.resolve(strict=True) == parent and
            root.is_dir() and not root.stat().st_file_attributes & 0x400 and
            not parent.stat().st_file_attributes & 0x400, 'Font cache root is not ordinary')
    return root


def load_font_profile(path=PROFILE_PATH, game_root=None):
    from ui_bitmap_fonts import load_font
    path = Path(path)
    if game_root is None:
        game_root = profile_input_root(path)
    require(path.stat().st_size <= 256 * 1024, 'Font profile manifest exceeds its bound')
    profile = json.loads(path.read_text(encoding='utf-8'))
    verify_profile_inputs(profile, game_root)
    fonts = {}
    for font_id in FONT_IDS:
        font = load_font(game_root, font_id)
        expected = profile['fonts'][font_id]
        require(font.ggxml_sha256 == expected['ggxml']['sha256'] and len(font.glyphs) == expected['glyph_count'] and
                font.color_atlas_sha256 == profile['color_atlas']['sha256'], 'Parsed font differs from its input profile')
        require(set(font.sheets) == set(expected['textures']) and
                all(sheet.sha256 == expected['textures'][alias]['sha256'] for alias, sheet in font.sheets.items()), 'Parsed font atlas profile differs')
        fonts[font_id] = font
    verify_profile_inputs(profile, game_root)
    return profile, fonts


def integer_glyph_map(glyphs):
    require(type(glyphs) is dict and glyphs, 'Glyph set is missing')
    result = {}
    for raw_key, value in glyphs.items():
        if type(raw_key) is int:
            key = raw_key
        else:
            require(isinstance(raw_key, str) and re.fullmatch('0|[1-9][0-9]*', raw_key), 'Glyph key is not a canonical codepoint')
            key = int(raw_key)
        require(0 <= key <= 0x10ffff and key not in result and type(value) is dict and set(value) == GLYPH_FIELDS,
                'Duplicate codepoint or invalid glyph record')
        require(all(type(number) is int and abs(number) <= 9007199254740991 for number in value.values()) and
                value['width'] >= 0 and value['height'] >= 0,
                'Glyph metrics must preserve exact source integers')
        result[key] = dict(value)
    return result


def referenced_sets(metrics):
    fonts = metrics.get('fonts')
    require(type(fonts) is dict and fonts, 'Font metadata is missing')
    refs = set()
    for font in fonts.values():
        require(type(font) is dict and is_sha(font.get('glyphSet')) and font.get('sha256') == font['glyphSet'],
                'Font source digest differs from its glyph-set identity')
        refs.add(font['glyphSet'])
    return sorted(refs)


def intern_font_metrics(metrics, bank, profile_id):
    require(type(metrics) is dict and not any(key in metrics for key in TRANSPORT_FIELDS) and
            type(bank) is dict and is_sha(profile_id), 'Invalid inline metrics for sharing')
    refs = referenced_sets(metrics)
    glyphs = metrics.get('glyphSets')
    require(type(glyphs) is dict and sorted(glyphs) == refs, 'Inline glyph sets differ from their font references')
    for identity in refs:
        canonical = integer_glyph_map(glyphs[identity])
        require(identity not in bank or bank[identity] == canonical, 'Equal font digests contain different glyph metrics')
        if identity not in bank:
            bank[identity] = canonical
    result = {key: value for key, value in metrics.items() if key != 'glyphSets'}
    result.update(glyphSetStorage=STORAGE_TAG, sharedProfileId=profile_id, glyphSetRefs=refs)
    return result


def resolve_prepared_font_metrics(prepared, metrics):
    require(type(metrics) is dict, 'Selected layout font metrics are missing')
    refs = referenced_sets(metrics)
    if not any(key in metrics for key in TRANSPORT_FIELDS):
        glyphs = metrics.get('glyphSets')
        require(type(glyphs) is dict and sorted(glyphs) == refs, 'Legacy glyph sets differ from their font references')
    else:
        require(all(key in metrics for key in TRANSPORT_FIELDS) and 'glyphSets' not in metrics and
                metrics['glyphSetStorage'] == STORAGE_TAG and is_sha(metrics['sharedProfileId']) and
                type(metrics['glyphSetRefs']) is list and metrics['glyphSetRefs'] == refs, 'Invalid or mixed shared glyph references')
        bank = prepared.get('shared_font_metrics')
        require(type(bank) is dict and set(bank) == {'schema', 'profileId', 'glyphSets'} and bank['schema'] == BANK_SCHEMA and
                bank['profileId'] == metrics['sharedProfileId'] and type(bank['glyphSets']) is dict,
                'Shared font bank or input profile differs')
        require(all(identity in bank['glyphSets'] for identity in refs), 'Shared font bank is missing a referenced set')
        glyphs = {identity: bank['glyphSets'][identity] for identity in refs}
    result = {key: value for key, value in metrics.items() if key not in TRANSPORT_FIELDS and key != 'glyphSets'}
    result['glyphSets'] = {identity: integer_glyph_map(glyphs[identity]) for identity in refs}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true', required=True)
    args = parser.parse_args()
    profile = capture_profile()
    require(not PROFILE_PATH.exists(), 'Keep the existing profile; do not silently replace its input identity')
    with PROFILE_PATH.open('x', encoding='utf-8') as stream:
        json.dump(profile, stream, indent=2); stream.write('\n')
    rows = verify_profile_inputs(profile)
    print(json.dumps(dict(status='FONT_PROFILE_CAPTURED_READONLY_ORIGINAL_INPUTS', profile=artifact(PROFILE_PATH),
                         profile_id=profile['profile_id'], fonts=len(profile['fonts']), selected_source_files=len(rows),
                         source_logical_bytes=sum(row['bytes'] for row in rows), source_files_copied=0,
                         glyph_counts={name: row['glyph_count'] for name, row in profile['fonts'].items()})))


if __name__ == '__main__':
    main()
