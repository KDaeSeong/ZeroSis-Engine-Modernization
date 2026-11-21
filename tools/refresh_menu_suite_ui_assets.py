"""Refresh the current 74-payload menu catalog using exact existing inputs.

No full asset preparer, FPK extraction, font/glyph extraction, Lua provider,
renderer, Host or SDK is run. Only the generated header and preparation report
are published; their preceding bytes remain in the attested ExitConfirm build.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch
import xml.etree.ElementTree as ET

import refresh_exit_confirm_ui_assets as reuse


PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/game_menu/original_menu_followup/ui_assets'
HEADER = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
PREPARED = PROJECT / 'evidence/ui_popup/assets/prepared.json'
BASE_ID = '20261101T074006Z_c2fd2fe9be38'
BASE_SHA = '6077a003f247a82df3e5fe6cfa56671df2750ae0bb0fec9710f71df659439ba7'
REUSE_SHA = '4a2ed7b2282642f948cc9c3042d46d526548e033db94a25fd88cdcef390e8618'
NEW_LAYOUTS = ('MenuOptionsLayout', 'TouchHelpLayout', 'MapMenuLayout')
NEW_SCRIPTS = ('TouchControlsMenu', 'SaveMapMenu')
EXTRA_SCENE = (('host_ui_menu_options_addendum', 'Source/Presentation/UiMenuOptions.lua'),
               ('host_ui_map_menu_addendum', 'Source/Presentation/UiMapMenu.lua'))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def checked(path, expected=None):
    row = reuse.artifact(path)
    require(expected is None or row['sha256'] == expected, 'Pinned menu UI input differs: ' + str(path))
    return row


def read_json(path, bound=16 * 1024 * 1024):
    row = checked(path)
    require(row['bytes'] <= bound, 'Menu UI JSON exceeds its bound')
    return json.loads(Path(path).read_bytes().decode('utf-8-sig'))


def source_manifest(host_sources, producer_sources, new_sources):
    unique = {}
    for row in [*host_sources, *producer_sources, *new_sources]:
        info = Path(row['path']).stat()
        require(row['file_identity'] == [info.st_dev, info.st_ino] and row['mtime_ns'] == info.st_mtime_ns,
                'Source changed while sealing the exact menu manifest')
        unique[str(Path(row['path']).absolute()).casefold()] = dict(row, file_attributes=getattr(info, 'st_file_attributes', 0))
    return dict(schema='zerosis.menu_suite_ui.actual_sources.v1', sources=list(unique.values()),
                native_execution=False, full_asset_preparer_main_executed=False)


def reuse_font_metrics(tree, prepared):
    """Select existing exact font metadata and shared glyph references only."""
    fonts, template = {}, None
    for existing in prepared['xml_control_trees'].values():
        metrics = existing.get('fontMetrics')
        if not metrics:
            continue
        if template is None:
            template = metrics
        require(metrics.get('inlineIcons') == template.get('inlineIcons') and
                metrics.get('sharedProfileId') == template.get('sharedProfileId'),
                'Existing prepared font transports disagree')
        for name, value in metrics['fonts'].items():
            require(name not in fonts or fonts[name] == value, 'Existing font identity is ambiguous')
            fonts[name] = value
    needed = set()
    def collect(node):
        attributes = node['attributes']
        defaults = tree.get('styleDefaults', {}).get(attributes.get('Style'), {}).get('attributes', {})
        font = attributes.get('Font') or defaults.get('Font')
        if font:
            needed.add(font)
        for child in node['children']:
            collect(child)
    collect(tree)
    for style in tree.get('styleDefaults', {}).values():
        collect(style)
    require(template is not None and needed and needed <= set(fonts),
            'New layout needs font metadata absent from the retained bank: ' + ', '.join(sorted(needed - set(fonts))))
    result = {name: deepcopy(value) for name, value in template.items() if name not in ('fonts', 'glyphSetRefs')}
    result['fonts'] = {name: deepcopy(fonts[name]) for name in sorted(needed)}
    result['glyphSetRefs'] = sorted({value['glyphSet'] for value in result['fonts'].values()})
    require(all(name in prepared['shared_font_metrics']['glyphSets'] for name in result['glyphSetRefs']),
            'Retained font metadata refers to a missing shared glyph set')
    return result


def texture_inventory(prepared):
    result = {}
    for value in reuse.nested_objects(prepared):
        if (type(value.get('requested_name')) is str and type(value.get('output')) is dict and
                type(value.get('frozen_source')) is dict):
            name = value['requested_name'].replace('\\', '/').casefold()
            for alias in (name, Path(name).name):
                result.setdefault(alias, []).append(value)
    return result


def select_textures(names, inventory, inputs):
    selected, missing = [], []
    for name in names:
        alias = name.replace('\\', '/').casefold()
        candidates = inventory.get(alias) or inventory.get(Path(alias).name) or []
        if not candidates:
            missing.append(name)
            continue
        # Different old request aliases may intentionally decode the same bytes.
        identities = {(row['output']['sha256'], row['frozen_source']['sha256']) for row in candidates}
        require(len(identities) == 1, 'Ambiguous retained menu texture: ' + name)
        row = deepcopy(candidates[0])
        row['requested_name'] = name
        for field in ('frozen_source', 'output', 'frozen_index'):
            if row.get(field):
                inputs.verify(row[field])
        selected.append(row)
    return selected, missing


def selected_texture_receipt(prepared, inputs):
    """Consume the separately authorized exact five-entry file-only capture."""
    import civ5_ui_assets as assets
    path = PROJECT / 'evidence/game_menu/offline_menu_suite/ui_assets/texture_reuse.json'
    if not path.exists():
        return None, [], []
    receipt_ref = checked(path)
    receipt = read_json(path, 256 * 1024)
    required = {'corner16.dds', 'grid9frame27square.dds', 'grid9frame27squareblack.dds', 'slider32.dds', 'sliderbackh.dds'}
    records = receipt.get('records')
    require(receipt.get('schema') == 'zerosis.menu_suite_ui.selected_textures.v1' and
            receipt.get('status') == 'PASS_EXACT_FIVE_MENU_TEXTURES_FROZEN_FILE_ONLY' and
            receipt.get('native_execution') is False and receipt.get('originals_read_only') is True and
            receipt.get('full_pack_copied') is False and type(records) is list and len(records) == 5 and
            {row['basename'] for row in records} == required and
            receipt['original_packs_before'] == receipt['original_packs_after'],
            'Selected texture receipt exceeds its exact authorized five-entry scope')
    inputs.verify(receipt_ref)
    original_packs = {row['path']: row for row in prepared['game_menu_control_pack_sources']}
    for row in receipt['original_packs_before']:
        require(row['path'] in original_packs and row['sha256'] == original_packs[row['path']]['sha256'],
                'Selected texture capture used an unregistered original pack')
        inputs.verify(row)
    source_rows = [receipt_ref, checked(receipt['producer']['path'], receipt['producer']['sha256'])]
    for row in records:
        require(row['source']['pack_path'] in original_packs and row['source']['entry'].casefold() == row['basename'] and
                row['frozen_source']['sha256'] == row['source']['sha256'], 'Selected texture original-entry provenance differs')
        for field in ('frozen_source', 'frozen_index', 'output'):
            if row.get(field):
                current = checked(row[field]['path'], row[field]['sha256'])
                require(Path(current['path']).is_relative_to(PROJECT / 'Source/Assets/UI'),
                        'Selected menu texture escaped the shared owned source tree')
                inputs.verify(current)
                source_rows.append(current)
        raw = Path(row['frozen_source']['path']).read_bytes()
        index = Path(row['frozen_index']['path']).read_bytes() if row.get('frozen_index') else None
        decoded, conversion = assets.decode_dds(raw, index)
        require(row['conversion'] == conversion and (len(decoded), hashlib.sha256(decoded).hexdigest()) ==
                (row['output']['bytes'], row['output']['sha256']), 'Selected texture normalized output differs from actual retained source bytes')
    return receipt_ref, records, source_rows


def compressed_recovery(row):
    backup = checked(row['backup']['path'], row['backup']['sha256'])
    require(type(row['bytes']) is int and 0 <= row['bytes'] <= 16 * 1024 * 1024,
            'Compressed menu recovery exceeds its exact bound')
    with gzip.open(backup['path'], 'rb') as stream:
        raw = stream.read(row['bytes'] + 1)
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'Compressed menu recovery does not reproduce its declared bytes')
    return raw


def reconstruct_prior_header(report):
    recipe = report['header_recovery_ref']
    if recipe.get('schema') != 'zerosis.menu_suite_ui.header_reconstruction.v1':
        return Path(recipe['path']).read_bytes()
    import prepare_ui_popup_assets as preparer
    arrays, _ = reuse.parse_text_arrays(HEADER.read_bytes(), preparer)
    old_scene = compressed_recovery(recipe['old_scene'])
    expected = recipe['unchanged_payloads']
    require(reuse.payload_identities([(name, raw) for name, raw in arrays if name != 'ZeroSisUiScene']) == expected,
            'An array outside the old-scene recovery role changed')
    previous = json.loads(compressed_recovery(recipe['old_prepared']).decode('utf-8-sig'))
    audio = []
    for symbol, filename, script_id, volume in reuse.AUDIO:
        row = next(row for row in previous['purchase_audio'] if row['script']['script_id'] == script_id)
        path = PROJECT / 'Source/Assets/Audio' / (filename + '.wav')
        checked(path, row['wave']['sha256'])
        audio.append((symbol, path.read_bytes(), volume, row['duplicate_policy']))
    raw = reuse.render_header([(name, old_scene if name == 'ZeroSisUiScene' else payload) for name, payload in arrays], audio, preparer)
    require((len(raw), hashlib.sha256(raw).hexdigest()) == (recipe['expected_header']['bytes'], recipe['expected_header']['sha256']),
            'Old menu header does not reconstruct to its exact historical identity')
    return raw


def prepare(refresh_current_74=False):
    import prepare_ui_popup_assets as preparer
    import menu_options_assets as options
    import ui_font_profile as fonts
    require(checked(Path(reuse.__file__).absolute())['sha256'] == REUSE_SHA,
            'Read-only ExitConfirm formatting helper changed')
    base_path = PROJECT / 'evidence/ui_window_host' / BASE_ID / 'build_result.json'
    checked(base_path, BASE_SHA)
    base = read_json(base_path)
    frozen_root = PROJECT / 'Build/UiWindowHost' / BASE_ID / 'frozen'
    candidates = [*base['compiler_inputs'], *base['sources'], base['ui_assets']]
    def recovery(original):
        found = [row for row in candidates if row.get('original_source', row.get('original_path', '')).casefold() == str(original).casefold()]
        require(found and all(row['sha256'] == found[0]['sha256'] for row in found), 'Missing exact existing output recovery')
        row = found[0]
        require(Path(row['path']).is_relative_to(frozen_root), 'Output recovery escaped the immutable base build')
        current, retained = checked(original), checked(row['path'], row['sha256'])
        require((current['bytes'], current['sha256']) == (retained['bytes'], retained['sha256']) and current['links'] == 1,
                'Mutable output is shared or differs from the exact base; inspect rather than overwrite')
        return current, retained
    latest_baseline = None
    if refresh_current_74:
        baseline_path = STAGE / 'second_refresh_baseline.json'
        latest_baseline = read_json(baseline_path, 64 * 1024)
        require(latest_baseline.get('schema') == 'zerosis.menu_suite_ui.second_refresh_baseline.v1' and
                latest_baseline.get('whole_header_copy_created') is False and latest_baseline.get('native_execution') is False,
                'Second menu refresh lacks its typed first-publication recovery')
        before_header, before_prepared = checked(HEADER), checked(PREPARED)
        require(before_header == latest_baseline['mutable_header'] and before_prepared == latest_baseline['mutable_prepared'] and
                before_header['links'] == before_prepared['links'] == 1,
                'Current first74 outputs differ from the exact new one-use baseline')
        old_scene = compressed_recovery(latest_baseline['old_scene'])
        require(compressed_recovery(latest_baseline['old_prepared']) == PREPARED.read_bytes(),
                'First74 preparation report recovery differs')
        compressed_recovery(latest_baseline['old_producer'])
        previous = read_json(latest_baseline['previous_publication']['path'])
        require(checked(latest_baseline['previous_publication']['path']) == latest_baseline['previous_publication'] and
                checked(latest_baseline['previous_source_manifest']['path']) == latest_baseline['previous_source_manifest'] and
                previous['generated_header'] == before_header and previous['prepared_report'] == before_prepared and
                previous['producer']['sha256'] == latest_baseline['old_producer']['sha256'] and
                previous['producer']['bytes'] == latest_baseline['old_producer']['bytes'] and
                previous['source_manifest_artifact']['sha256'] == latest_baseline['previous_source_manifest']['sha256'],
                'Second refresh recovery does not bind the exact historical first74 publication')
        recover_header = dict(schema='zerosis.menu_suite_ui.header_reconstruction.v1',
            expected_header=dict(original_path=str(HEADER), bytes=before_header['bytes'], sha256=before_header['sha256']),
            old_scene=latest_baseline['old_scene'], old_prepared=latest_baseline['old_prepared'],
            unchanged_payloads=reuse.payload_identities([(name, raw) for name, raw in reuse.parse_text_arrays(HEADER.read_bytes(), preparer)[0]
                                                       if name != 'ZeroSisUiScene']))
        require(dict(reuse.parse_text_arrays(HEADER.read_bytes(), preparer)[0])['ZeroSisUiScene'] == old_scene,
                'First74 embedded scene backup differs from the actual original header')
        recover_prepared = latest_baseline['old_prepared']['backup']
    else:
        before_header, recover_header = recovery(HEADER)
        before_prepared, recover_prepared = recovery(PREPARED)
    inputs = reuse.Inputs()
    inputs.game = preparer.GAME
    recovery_rows = ([checked(STAGE / 'second_refresh_baseline.json'), latest_baseline['old_scene']['backup'],
                      latest_baseline['old_prepared']['backup'], latest_baseline['old_producer']['backup'],
                      latest_baseline['previous_publication'], latest_baseline['previous_source_manifest']]
                     if latest_baseline else [recover_header, recover_prepared])
    for row in (before_header, before_prepared, *recovery_rows, checked(base_path)):
        inputs.verify(row, exact_identity=True)
    old = read_json(PREPARED)
    require(old.get('renderer_verified') is False and old.get('status') == 'INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED',
            'UI preparation baseline changed')
    old_arrays, _ = reuse.parse_text_arrays(HEADER.read_bytes(), preparer)
    old_by_name = dict(old_arrays)
    require(not refresh_current_74 and len(old_arrays) == len(old_by_name) == 74 and
            len(old['xml_control_trees']) == 30 and set(NEW_LAYOUTS + NEW_SCRIPTS) <= set(old_by_name),
            'Followup refresh requires the current immutable Host4 74-payload baseline')
    for name, tree in old['xml_control_trees'].items():
        require(old_by_name[name] == ('ZeroSisUiLayout=' + preparer.lua_value(tree) + '\n').encode('ascii'),
                'Prior layout bytes differ from retained metadata: ' + name)
    bank = reuse.normalize_bank(old['shared_font_metrics'], fonts)
    require(old_by_name['SharedFontMetrics'] == ('ZeroSisUiSharedFontMetrics=' + preparer.lua_value(bank) + '\n').encode('ascii'),
            'Retained shared font bank differs from its embedded bytes')
    audio, audio_proof = [], []
    for symbol, filename, script_id, volume in reuse.AUDIO:
        rows = [row for row in old['purchase_audio'] if row['script']['script_id'] == script_id]
        require(len(rows) == 1, 'Audio metadata is missing or duplicated')
        row = rows[0]
        wave = PROJECT / 'Source/Assets/Audio' / (filename + '.wav')
        actual = checked(wave, row['wave']['sha256'])
        require(actual['bytes'] == row['wave']['container_bytes'] and row['script']['min_volume'] == row['script']['max_volume'] == volume,
                'Retained audio bytes or volume changed')
        inputs.verify(actual)
        audio.append((symbol, wave.read_bytes(), volume, row['duplicate_policy']))
        audio_proof.append(actual)
    require(reuse.render_header(old_arrays, audio, preparer) == HEADER.read_bytes(),
            'Prior complete char/audio/index catalog does not reconstruct exactly')
    sources, host_records = {}, {}
    for key, relative, _ in reuse.HOST_LUA:
        path = PROJECT / relative
        record = checked(path)
        inputs.verify(record)
        sources[key], host_records[key] = path.read_bytes(), record
    for key, relative in EXTRA_SCENE:
        path = PROJECT / relative
        record = checked(path)
        inputs.verify(record)
        sources[key], host_records[key] = path.read_bytes(), record
    for key, symbol in (('production_command_guard', 'ProductionCommandGuard'), ('research_command_guard', 'ResearchCommandGuard')):
        require(sources[key] == old_by_name[symbol], 'Command guard changed outside the menu refresh scope')
    scene = reuse.scene_bytes(sources) + b'\n' + sources[EXTRA_SCENE[0][0]] + b'\n' + sources[EXTRA_SCENE[1][0]]
    snapshots = PROJECT / 'Source/Assets/UI'
    new_source_records, new_sources = [], []
    original_options = options.original_sources()
    original_map = preparer.map_menu_original_sources()
    for record in [*original_options.values(), *original_map.values()]:
        original = Path(record['path'])
        snapshot = snapshots / original.relative_to(preparer.GAME)
        actual = checked(snapshot, record['sha256'])
        require(actual['bytes'] == record['bytes'], 'New selected source snapshot byte count differs')
        inputs.verify(record)
        inputs.verify(actual)
        new_sources.append(actual)
    new_trees = {}
    with reuse.FileOnlyGuard(preparer) as guard, ExitStack() as stack:
        for owner, name in ((preparer, 'production_font_metrics'), (preparer, 'load_font'),
                            (fonts, 'load_font_profile')):
            stack.enter_context(patch.object(owner, name, guard.reject(name)))
        for name, relative, kind in preparer.LAYOUTS:
            if name not in NEW_LAYOUTS:
                continue
            element = ET.fromstring((snapshots / relative).read_bytes())
            tree = (options.menu_options_control_tree(element, kind) if kind in ('MenuOptions', 'TouchHelp')
                    else preparer.map_menu_control_tree(element))
            tree['controlDefaultSizes'] = options.menu_checkbox_defaults(tree, snapshots)
            defaults = preparer.production_style_defaults(snapshots, tree)
            require(defaults['source']['sha256'] == old['production_style_defaults_source']['sha256'],
                    'Existing original styles changed')
            tree.update(styleDefaults=defaults['controls'], styleDefaultsSource=defaults['source'], styleDefaultsPolicy=defaults['policy'])
            tree['fontMetrics'] = reuse_font_metrics(tree, old)
            fonts.resolve_prepared_font_metrics(old, tree['fontMetrics'])
            new_trees[name] = tree
        require(set(new_trees) == set(NEW_LAYOUTS) and not guard.rejected_calls,
                'New layout preparation invoked a forbidden native/extraction operation')
    texture_receipt, captured_textures, captured_sources = selected_texture_receipt(old, inputs)
    inventory = texture_inventory(old)
    for row in captured_textures:
        for alias in (row['requested_name'].replace('\\', '/').casefold(), row['basename']):
            inventory.setdefault(alias, []).append(row)
    texture_reuse, missing = {}, {}
    for name, tree in new_trees.items():
        names = preparer.game_menu_texture_names(tree)
        rows, absent = select_textures(names, inventory, inputs)
        texture_reuse[name] = dict(control_texture_names=names, control_textures=rows, created_files=0)
        if absent:
            missing[name] = absent
    require(not missing, 'Required new menu textures lack verified existing records: ' + json.dumps(missing, ensure_ascii=False))
    producer_sources = [checked(Path(__file__).absolute()), checked(Path(reuse.__file__).absolute()),
                        checked(Path(preparer.__file__).absolute()), checked(Path(options.__file__).absolute()),
                        checked(Path(fonts.__file__).absolute())]
    producer_sources.extend(checked(PROJECT / 'tools' / name) for name in
                            ('ui_pixel_scene.py', 'interactive_ui_driver.py', 'render_ui_popup.py'))
    for row in producer_sources:
        inputs.verify(row)
    updated = deepcopy(old)
    updated['xml_control_trees'].update(new_trees)
    updated.update({key: {field: row[field] for field in ('path', 'sha256')} for key, row in host_records.items()})
    updated.update(builder={field: producer_sources[0][field] for field in ('path', 'sha256')},
                   base_builder=deepcopy(old['builder']), text_asset_preparer={field: producer_sources[2][field] for field in ('path', 'sha256')})
    for layout, policy in (('MenuOptionsLayout', 'menu_options'), ('TouchHelpLayout', 'touch_help'), ('MapMenuLayout', 'map_menu')):
        tree = new_trees[layout]
        updated[policy] = dict(layout_asset=layout, context_name=tree['contextName'], popup_kind=tree['popupKind'],
            metadata=deepcopy(tree.get('menuOptions', tree.get('mapMenu'))), **texture_reuse[layout],
            font_metrics_reused=True, source_bytes_preserved=True, native_acceptance_verified=False, renderer_verified=False)
    old_source_records = {row['name']: row for row in old['inputs']}
    ordered = []
    for name, relative in (*preparer.SCRIPTS, *((name, relative) for name, relative, _ in preparer.LAYOUTS), *preparer.SOURCE_ASSETS):
        if name in old_source_records:
            ordered.append(deepcopy(old_source_records[name]))
        else:
            source, snapshot = checked(preparer.GAME / relative), checked(snapshots / relative)
            inputs.verify(source)
            inputs.verify(snapshot)
            require(source['sha256'] == snapshot['sha256'], 'New original/snapshot source differs')
            ordered.append(dict(name=name, installed=source, snapshot=snapshot))
            new_source_records.append(dict(name=name, installed=source, snapshot=snapshot))
    updated['inputs'] = ordered
    updated['selection'] = old['selection'] + '_ORIGINAL_OPTION_CONTROLS'
    texts = []
    for name, relative in preparer.SCRIPTS:
        payload = (snapshots / relative).read_bytes()
        if name not in NEW_SCRIPTS:
            require(old_by_name[name] == payload, 'Existing original script changed: ' + name)
        texts.append((name, payload))
    for name, _, _ in preparer.LAYOUTS:
        payload = ('ZeroSisUiLayout=' + preparer.lua_value(new_trees[name]) + '\n').encode('ascii') if name in new_trees else old_by_name[name]
        texts.append((name, payload))
    texts += [('SharedFontMetrics', old_by_name['SharedFontMetrics']), ('ZeroSisUiScene', scene),
              ('ProductionCommandGuard', old_by_name['ProductionCommandGuard']), ('ResearchCommandGuard', old_by_name['ResearchCommandGuard'])]
    require(len(texts) == len({name for name, _ in texts}) == len(ordered) == 74 and len(updated['xml_control_trees']) == 30,
            'New menu suite registry is not exactly 74 payloads and 30 layouts')
    changed_payloads = [name for name, raw in old_arrays if dict(texts)[name] != raw]
    require('ZeroSisUiScene' in changed_payloads and set(changed_payloads) <= {'ZeroSisUiScene', 'MenuOptionsLayout', 'TouchHelpLayout'},
            'An unrelated existing catalog payload changed')
    encoded = reuse.render_header(texts, audio, preparer)
    require(reuse.parse_text_arrays(encoded, preparer)[0] == texts, 'New menu header failed canonical text-array roundtrip')
    updated['compiled_assets'] = dict(path=str(HEADER), sha256=reuse.sha(encoded))
    updated['menu_suite_text_refresh'] = dict(schema='zerosis.menu_suite_ui.file_only_refresh.v1', producer=producer_sources[0],
        baseline_build=checked(base_path), header_recovery_ref=recover_header, prepared_recovery_ref=recover_prepared,
        catalog_payload_count=74, layout_count=30, actual_host_lua_source_count=len(host_records),
        full_asset_preparer_main_executed=False, native_code_executed=False, font_glyph_extraction_performed=False,
        shared_glyph_bank_unchanged=True, existing_layout_payloads_unchanged=False, changed_payloads=changed_payloads, audio_arrays_unchanged=True,
        texture_or_audio_extraction_performed=False, original_source_files_copied=0, renderer_verified=False)
    updated['menu_suite_text_refresh'].update(selected_texture_capture=texture_receipt,
        selected_texture_capture_separate_file_only_step=True, previous_publication_historical=(latest_baseline['previous_publication'] if latest_baseline else None),
        previous_producer_recovery=(latest_baseline['old_producer'] if latest_baseline else None))
    prepared = reuse.json_bytes(updated)
    inputs.unchanged()
    manifest = source_manifest(list(host_records.values()), producer_sources, new_sources + captured_sources)
    report = dict(schema='zerosis.menu_suite_ui.preflight.v1', status='PASS_74_PAYLOAD_MENU_UI_FILE_ONLY_PREFLIGHT_NOT_APPLIED',
        baseline_header=before_header, baseline_prepared=before_prepared, header_recovery_ref=recover_header,
        prepared_recovery_ref=recover_prepared, producer=producer_sources[0], source_manifest=manifest,
        source_inputs_before=sorted(inputs.rows.values(), key=lambda row: row['path'].casefold()),
        current_host_lua_sources=host_records, catalog_payloads=reuse.payload_identities(texts),
        new_payload_names=[], changed_payloads=changed_payloads,
        unchanged_existing_payload_count=74-len(changed_payloads),
        publication_kind='CURRENT_HOST4_ORIGINAL_OPTIONS_FOLLOWUP_74_PAYLOAD_REFRESH',
        previous_publication_historical=latest_baseline['previous_publication'] if latest_baseline else None,
        shared_glyph_bank_unchanged=True, audio_reuse=audio_proof, texture_reuse=texture_reuse,
        selected_texture_capture=texture_receipt, selected_texture_capture_is_separate_file_only_step=True,
        outputs_expected=dict(header=dict(path=str(HEADER), bytes=len(encoded), sha256=reuse.sha(encoded)),
                              prepared=dict(path=str(PREPARED), bytes=len(prepared), sha256=reuse.sha(prepared))),
        full_asset_preparer_main_executed=False, native_code_executed=False, font_glyph_extraction_performed=False,
        texture_or_audio_extraction_performed=False, installed_game_mods_or_user_saves_written=False,
        native_execution=False, host_sdk_clr_hwnd_gpu_or_game_loaded=False)
    return encoded, prepared, report


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    choice = cli.add_mutually_exclusive_group(required=True)
    choice.add_argument('--preflight', type=Path)
    choice.add_argument('--apply', type=Path)
    cli.add_argument('--preflight-sha256')
    cli.add_argument('--refresh-current-74', action='store_true',
                     help='Use the separately sealed first74 scene/report recovery; never replay the original publication')
    args = cli.parse_args(argv)
    require(sys.dont_write_bytecode and __debug__, 'Use Python -B without optimization')
    path = (args.preflight or args.apply).absolute()
    require(path.parent == STAGE and path.suffix == '.json', 'Refresh report must be one leaf in the owned UI stage')
    header, prepared, report = prepare(args.refresh_current_74)
    if args.preflight:
        require(not args.preflight_sha256 and not path.exists(), 'Inspect an existing preflight instead of replacing it')
        path.write_bytes(reuse.json_bytes(report))
        print(json.dumps(dict(status=report['status'], preflight=checked(path), native_execution=False)))
        return 0
    require(args.preflight_sha256 and checked(path)['sha256'] == args.preflight_sha256,
            'Apply requires the exact reviewed file-only preflight')
    require(read_json(path) == report, 'Source or output bytes changed after the reviewed preflight')
    result = STAGE / ('ui_embedding_final_result.json' if args.refresh_current_74 else 'ui_embedding_result.json')
    require(not result.exists(), 'Inspect the published menu refresh instead of repeating it')
    manifest_path = STAGE / ('final_source_manifest.json' if args.refresh_current_74 else 'source_manifest.json')
    require(not manifest_path.exists(), 'The owned menu UI source manifest already exists')
    pending_header = STAGE / ('UiPopupAssets.generated.h.final.pending' if args.refresh_current_74 else 'UiPopupAssets.generated.h.pending')
    pending_prepared = STAGE / ('prepared.final.json.pending' if args.refresh_current_74 else 'prepared.json.pending')
    require(not pending_header.exists() and not pending_prepared.exists(), 'A prior pending publication needs review')
    for pending, raw in ((pending_header, header), (pending_prepared, prepared)):
        with pending.open('xb') as stream:
            stream.write(raw)
    os.replace(pending_header, HEADER)
    try:
        os.replace(pending_prepared, PREPARED)
    except OSError:
        with pending_header.open('xb') as stream:
            stream.write(reconstruct_prior_header(report))
        os.replace(pending_header, HEADER)
        raise
    for name, target in (('header', HEADER), ('prepared', PREPARED)):
        actual = checked(target)
        expected = report['outputs_expected'][name]
        require(all(actual[key] == expected[key] for key in ('path', 'bytes', 'sha256')) and actual['links'] == 1,
                'Published menu UI output differs from the reviewed byte identity')
    for row in report['source_inputs_before']:
        if row['path'] not in (str(HEADER), str(PREPARED)):
            require(checked(row['path']) == row, 'A non-output input changed during publication')
    manifest_path.write_bytes(reuse.json_bytes(report['source_manifest']))
    report.update(status='PASS_74_PAYLOAD_MENU_UI_EMBEDDED_FILE_ONLY_NOT_HOST_LINKED_OR_EXECUTED',
        reviewed_preflight=checked(path), generated_header=checked(HEADER), prepared_report=checked(PREPARED),
        source_manifest_artifact=checked(manifest_path), pending_output_files_remaining=False,
        logical_output_delta_bytes=len(header) + len(prepared) - report['baseline_header']['bytes'] - report['baseline_prepared']['bytes'])
    result.write_bytes(reuse.json_bytes(report))
    if args.refresh_current_74:
        superseded = STAGE / 'first74_publication_superseded.json'
        require(not superseded.exists(), 'Historical first74 supersession marker already exists')
        superseded.write_bytes(reuse.json_bytes(dict(schema='zerosis.menu_suite_ui.typed_supersession.v1',
            status='FIRST_74_PUBLICATION_HISTORICAL_SUPERSEDED_BY_LATEST_SCENE',
            previous_publication=report['previous_publication_historical'], replacement_publication=checked(result),
            exact_first_scene_and_prepared_recovery=checked(STAGE / 'second_refresh_baseline.json'),
            original_header_reconstructible_without_whole_header_copy=True, native_execution=False)))
    print(json.dumps(dict(status=report['status'], result=checked(result), native_execution=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
