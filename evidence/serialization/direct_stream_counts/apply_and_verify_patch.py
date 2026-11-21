"""Apply only the reviewed eighteen direct-count sites; never build or run the SDK."""
from __future__ import annotations
from datetime import datetime, timezone
import argparse
import difflib
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
PRIOR_HELPER = PROJECT/'evidence/serialization/player_count_width/apply_and_verify_patch.py'
loader = importlib.util.spec_from_file_location('scoped_count_tracking', PRIOR_HELPER)
common = importlib.util.module_from_spec(loader)
loader.loader.exec_module(common)
artifact, atomic, digest, guarded, replay, require = (
    common.artifact, common.atomic, common.digest, common.guarded, common.replay, common.require)
PORT = PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
ORIGINAL = PROJECT/'Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2'
PATCHES = PROJECT/'Source/Porting/sdk_x64_patches.json'
MANIFEST = PROJECT/'evidence/sdk_x64/port_manifest.json'
PLAN = STAGE/'plan.json'
DIFF = STAGE/'direct_stream_counts.diff'
RECEIPT = STAGE/'port_patch_tracking.json'
INVENTORY_A = PROJECT/'evidence/serialization/player_count_width/remaining_direct_counts_a.json'
INVENTORY_B = PROJECT/'evidence/serialization/player_count_width/remaining_direct_counts_b.json'
INPUT_HASHES = {
    INVENTORY_A: '0613bacda43b7a677cdb808fddf1370c86c9d11c28efb754f4d67a1ae4be2f26',
    INVENTORY_B: '394016c31474f1ba5bb2ecee3ad458aa13b6312e5074e1a581bd9e648af724ea',
    PATCHES: 'a5820e7f774d49156cc6d6e743d0dc0ec7704b798289f1f24dd66838229e3f52',
    MANIFEST: 'bfa0aaf365f5f5674c7070f1b6064a8b4872b6630b851b39f92c05e766cc295c',
}
BASELINES = {
    'CvArmyAI.cpp': 'c5262d0711e5775426df3e19d00bef09449f20cb4fa896e79113c3b75b8be7c9',
    'CvCultureClasses.cpp': 'caee037dae6968e8d130f7a885ace109945d3f2424140a9ae5cfe0d58b1ae7a9',
    'CvDiplomacyRequests.cpp': '43b2530e35c845669136f0d2f0684d06a3c08bd639bca8f8dab82685d1f42529',
    'CvEconomicAI.cpp': '8aafc8503b86cf9fa5871470a7afc0756d0fcd1b6cae290902a6c739fcafa43b',
    'CvEspionageClasses.cpp': '46461f15570127dbcddfc6c003163ee2faa8506eb13fd5a23631330fc81abcc1',
    'CvPopupReturn.cpp': 'f11d77ed6e99df6b715ffca1b6d2e7f4791b33b49e1451d14edf55660db2e70a',
    'CvReplayInfo.cpp': 'f55c3cce24e98def5a49df7f892d8b2ae851f8dbaf3b77e65c99aee410ed7197',
    'CvReplayMessage.cpp': 'd7ab3bf204aeff93f0ed16ce2822cf3b75d22d9a1abe49064ce9b2f815dd8ecb',
}
SIGNATURES = {
    'CvArmyAI.cpp': 'void CvArmyAI::write(FDataStream& kStream) const',
    'CvCultureClasses.cpp': 'FDataStream& operator<<(FDataStream& saveTo, const CvPlayerCulture& readFrom)',
    'CvDiplomacyRequests.cpp': 'void CvDiplomacyRequests::Write(FDataStream& kStream) const',
    'CvEconomicAI.cpp': 'void CvEconomicAI::Write(FDataStream& kStream)',
    'CvEspionageClasses.cpp': 'FDataStream& operator<<(FDataStream& saveTo, const CvPlayerEspionage& readFrom)',
    'CvPopupReturn.cpp': 'void PopupReturn::write(FDataStream& kStream) const',
    'CvReplayInfo.cpp': 'void CvReplayInfo::write(FDataStream& kStream) const',
    'CvReplayMessage.cpp': 'void CvReplayMessage::write(FDataStream& kStream) const',
}
SITES = {
    'CvArmyAI.cpp': [('int', 'iNumFormationEntries', 'm_FormationEntries.size()', True)],
    'CvCultureClasses.cpp': [('int', 'iNumDigCompletePlots', 'readFrom.m_aDigCompletePlots.size()', False)],
    'CvDiplomacyRequests.cpp': [('uint', 'uiNumRequests', 'm_aRequests.size()', False)],
    'CvEconomicAI.cpp': [('int', 'iNumRequestedSavings', 'm_RequestedSavings.size()', True)],
    'CvEspionageClasses.cpp': [
        ('int', 'iNumSpyNames', 'readFrom.m_aiSpyListNameOrder.size()', False),
        ('int', 'aiHeistLocationCounts[uiCiv]', 'readFrom.m_aHeistLocations[uiCiv].size()', False),
        ('int', 'iNumSpyNotificationMessages', 'readFrom.m_aSpyNotificationMessages.size()', False),
        ('int', 'iNumIntrigueNotificationMessages', 'readFrom.m_aIntrigueNotificationMessages.size()', False)],
    'CvPopupReturn.cpp': [
        ('int', 'iNumSelectedRadioButtons', 'm_aiSelectedRadioButton.size()', False),
        ('int', 'iNumBitFields', 'm_aiBitField.size()', False),
        ('int', 'iNumEditBoxStrings', 'm_aszEditBoxString.size()', False),
        ('int', 'iNumSpinnerWidgetValues', 'm_aiSpinnerWidgetValues.size()', False),
        ('int', 'iNumPulldownIDs', 'm_aiPulldownID.size()', False),
        ('int', 'iNumListBoxIDs', 'm_aiListBoxID.size()', False),
        ('int', 'iNumSpinBoxIDs', 'm_aiSpinBoxID.size()', False),
        ('int', 'iNumButtonIDs', 'm_aiButtonID.size()', False)],
    'CvReplayInfo.cpp': [('uint', 'uiNumReplayMessages', 'm_listReplayMessages.size()', False)],
    'CvReplayMessage.cpp': [('int', 'iNumPlots', 'm_Plots.size()', True)],
}


def compact(text):
    return re.sub(r'\s+', '', text)


def once(text, old, new):
    require(text.count(old) == 1, 'Replacement not unique: ' + repr(old[:100]))
    return text.replace(old, new, 1)


def function(text, signature):
    # These eight copied definitions have column-zero closing braces. Also
    # check brace balance, so a changed layout fails closed instead of guessing.
    require(text.count(signature + '\r\n{\r\n') == 1, 'Writer signature/layout drift')
    start = text.index(signature + '\r\n{\r\n')
    end = text.index('\r\n}', start) + 3
    result = text[start:end]
    require(result.count('{') == result.count('}'), 'Writer brace boundary drift')
    return result


def preflight(name):
    lines = ['\t// Validate every selected count before output; match the original reader width.']
    for typ, local, expression, _ in SITES[name]:
        if '[' in local:
            lines += ['\tint aiHeistLocationCounts[MAX_MAJOR_CIVS];',
                      '\tfor(uint uiCiv = 0; uiCiv < MAX_MAJOR_CIVS; uiCiv++)',
                      '\t{',
                      '\t\taiHeistLocationCounts[uiCiv] = CvChecked::Integer<int>(readFrom.m_aHeistLocations[uiCiv].size());',
                      '\t}']
        else:
            lines.append('\tconst ' + typ + ' ' + local + ' = CvChecked::Integer<' + typ + '>(' + expression + ');')
    return '\r\n'.join(lines) + '\r\n\r\n'


def corrected_function(name, old):
    head = SIGNATURES[name] + '\r\n{\r\n'
    new = once(old, head, head + preflight(name))
    # Replace only the selected count expressions and their iteration bounds.
    # Stream-write comparison below independently checks every other operand.
    stream = 'saveTo' if name in ('CvCultureClasses.cpp', 'CvEspionageClasses.cpp') else 'kStream'
    for typ, local, expression, cast in SITES[name]:
        operand = ('(int)' if cast else '') + expression
        pattern = re.compile(r'(' + stream + r'\s*<<\s*)' + re.escape(operand) + r'(\s*;)')
        require(len(pattern.findall(new)) == 1, 'Selected count write not unique')
        new = pattern.sub(lambda m: m[1] + local + m[2], new, count=1)
    if name == 'CvArmyAI.cpp':
        new = once(new, 'for(uint ui = 0; ui < m_FormationEntries.size(); ui++)',
                   'for(int ui = 0; ui < iNumFormationEntries; ui++)')
    elif name == 'CvCultureClasses.cpp':
        new = once(new, '\tvector<CvPlot *>::const_iterator it;\r\n', '')
        new = once(new, '\tfor(it = readFrom.m_aDigCompletePlots.begin(); it != readFrom.m_aDigCompletePlots.end(); it++)',
                   '\tvector<CvPlot *>::const_iterator it = readFrom.m_aDigCompletePlots.begin();\r\n'
                   '\tfor(int iPlot = 0; iPlot < iNumDigCompletePlots; iPlot++, it++)')
    elif name == 'CvDiplomacyRequests.cpp':
        new = once(new, '\tfor(RequestList::const_iterator i = m_aRequests.begin(); i != m_aRequests.end(); ++i)',
                   '\tRequestList::const_iterator i = m_aRequests.begin();\r\n'
                   '\tfor(uint ui = 0; ui < uiNumRequests; ++ui, ++i)')
    elif name == 'CvEconomicAI.cpp':
        new = once(new, 'for(uint ui = 0; ui < m_RequestedSavings.size(); ui++)',
                   'for(int ui = 0; ui < iNumRequestedSavings; ui++)')
    elif name == 'CvEspionageClasses.cpp':
        for _, local, expression, _ in SITES[name]:
            new = once(new, 'for(uint ui = 0; ui < ' + expression + '; ui++)',
                       'for(int ui = 0; ui < ' + local + '; ui++)')
    elif name == 'CvPopupReturn.cpp':
        new = once(new, '\tunsigned int iI;\r\n', '\tint iI;\r\n')
        for _, local, expression, _ in SITES[name]:
            new = once(new, 'for(iI = 0; iI < ' + expression + '; iI++)',
                       'for(iI = 0; iI < ' + local + '; iI++)')
    elif name == 'CvReplayInfo.cpp':
        new = once(new, '\tfor(ReplayMessageList::const_iterator it = m_listReplayMessages.begin(); it != m_listReplayMessages.end(); ++it)',
                   '\tReplayMessageList::const_iterator it = m_listReplayMessages.begin();\r\n'
                   '\tfor(uint ui = 0; ui < uiNumReplayMessages; ++ui, ++it)')
    elif name == 'CvReplayMessage.cpp':
        new = once(new, '\tfor(PlotPositionList::const_iterator it = m_Plots.begin(); it != m_Plots.end(); ++it)',
                   '\tPlotPositionList::const_iterator it = m_Plots.begin();\r\n'
                   '\tfor(int iPlot = 0; iPlot < iNumPlots; ++iPlot, ++it)')
    writes = lambda text: [compact(m[0]) for m in re.finditer(r'(?:kStream|saveTo)\s*<<[^;]*;', text)]
    mapping = {compact(stream+'<<'+('(int)' if cast else '')+expression+';'): compact(stream+'<<'+local+';')
               for _, local, expression, cast in SITES[name]}
    require(writes(new) == [mapping.get(item, item) for item in writes(old)], 'Unrelated stream operand changed')
    first = re.search(r'(?:kStream|saveTo)\s*<<', old).start()
    first_new = re.search(r'(?:kStream|saveTo)\s*<<', new).start()
    old_prefix = old[len(head):first]
    new_prefix = new[len(head):first_new]
    require(new_prefix == preflight(name) + old_prefix, 'Original pre-write prefix was changed')
    if name == 'CvReplayMessage.cpp':
        require(writes(new)[0] == 'kStream<<m_iTurn;', 'ReplayMessage has no version word')
    return new


def inventories():
    a, b = json.loads(INVENTORY_A.read_bytes()), json.loads(INVENTORY_B.read_bytes())
    rows = []
    for site in a['sites']:
        rows.append(dict(cpp=site['cpp'], line=site['ported_line'], statement=site['statement'],
                         classification=site['classification'], reader=site['original_read'], inventory='A'))
    for site in b['sites']:
        rows.append(dict(cpp=site['source'].split(':', 1)[1], line=site['cpp_line'], statement=site['expression'],
                         classification=site['classification'], reader=site['original_reader'], inventory='B'))
    require(len(rows) == 58, 'Finite inventory length changed')
    return rows


def protected_inputs(rows):
    paths = {INVENTORY_A, INVENTORY_B, PRIOR_HELPER, PROJECT/'Source/Porting/CvCheckedNarrow.h'}
    for name in BASELINES:
        paths.add(ORIGINAL/name)
    for row in rows:
        if row['cpp'] not in BASELINES:
            paths.add(PORT/row['cpp'])
    return sorted(paths, key=str)


def proposed():
    require(not sys.flags.optimize, 'Optimization would suppress Python assertions')
    for path, expected in INPUT_HASHES.items():
        require(digest(path.read_bytes()) == expected, 'Reviewed metadata/inventory baseline changed: ' + path.name)
    old_spec, old_manifest = PATCHES.read_bytes(), MANIFEST.read_bytes()
    specification, manifest = json.loads(old_spec), json.loads(old_manifest)
    require(len(specification['patches']) == 702 and len(manifest) == 1105, 'Registry/manifest baseline row count changed')
    rows = inventories()
    selected = [r for r in rows if r['classification'] in ('NATIVE_SIZE_T_WIDTH_MISMATCH', 'UNCHECKED_NARROWING_ONLY')]
    require(len(selected) == 18 and sum(r['classification'] == 'NATIVE_SIZE_T_WIDTH_MISMATCH' for r in selected) == 15,
            'Selected eighteen-site baseline changed')
    preserved = [r for r in rows if r not in selected]
    require(sum(r['classification'] == 'ALREADY_FIXED_UNSIGNED_WIDTH' for r in preserved) == 39 and
            sum(r['classification'] == 'CHECKED_FIXED_WIDTH' for r in preserved) == 1, 'Preserved forty-site baseline changed')
    outputs, additions, file_plans, diffs, before = {}, [], [], [], []
    for name, expected in BASELINES.items():
        target = PORT/name
        guarded(target)
        raw = target.read_bytes()
        require(digest(raw) == expected, 'Reviewed source changed: ' + name)
        before.append(artifact(target))
        relative = 'CvGameCoreDLL_Expansion2/' + name
        baseline, previous = replay(specification, relative)
        require(baseline == raw, 'Existing RAM replay differs: ' + name)
        entry = [r for r in manifest if r['relative_path'] == relative]
        require(len(entry) == 1 and entry[0]['port_sha256'] == expected and entry[0]['patch_ids'] == previous,
                'Existing manifest row differs: ' + name)
        original_raw = (ORIGINAL/name).read_bytes()
        text = raw.decode('latin1')
        old_function = function(text, SIGNATURES[name])
        require(function(original_raw.decode('latin1'), SIGNATURES[name]) == old_function,
                'Selected original/ported writer function was already different')
        new_function = corrected_function(name, old_function)
        source_hash = digest(original_raw)
        def patch(identifier, old, new, reason):
            additions.append(dict(id=identifier, file=relative, source_sha256=source_hash,
                                  old=old, new=new, count=1, reason=reason))
        stem = name.removesuffix('.cpp').lower()
        include_added = '#include "CvCheckedNarrow.h"' not in text
        if include_added:
            old_include = '#include "CvGameCoreDLLPCH.h"\r\n'
            new_include = old_include + '#include "CvCheckedNarrow.h"\r\n'
            text = once(text, old_include, new_include)
            patch(stem + '_direct_count_checked_include', old_include, new_include,
                  'Provide the existing checked integer policy for exact original reader count widths.')
        text = once(text, old_function, new_function)
        patch(stem + '_direct_count_entry_preflight', old_function, new_function,
              'Check all selected counts before the first output; emit and iterate the same checked int32/uint32 bounds while preserving payload and versions.')
        candidate = text.encode('latin1')
        require(candidate.replace(b'\r\n', b'').count(b'\n') == 0, 'SDK CRLF encoding changed')
        outputs[target] = candidate
        count_plans = []
        for typ, local, expression, cast in SITES[name]:
            matching = [r for r in selected if r['cpp'] == name and compact(expression) in compact(r['statement'])]
            require(len(matching) == 1, 'Planned site absent from reviewed inventories')
            row = dict(matching[0], checked_type=typ, local=local, size_expression=expression,
                       array_extent='MAX_MAJOR_CIVS=22' if '[' in local else None,
                       cast_range_only=cast)
            count_plans.append(row)
        for row in (r for r in preserved if r['cpp'] == name):
            line = raw.decode('latin1').splitlines()[row['line']-1]
            require(compact(line) == compact(row['statement']), 'Preserved site baseline line drift')
            old_hits = sum(compact(line) == compact(x) for x in raw.decode('latin1').splitlines())
            new_hits = sum(compact(line) == compact(x) for x in text.splitlines())
            require(old_hits == new_hits, 'Preserved FStatic/checked statement changed')
        file_plans.append(dict(cpp=name, signature=SIGNATURES[name], before_sha256=expected,
                               after_sha256=digest(candidate), before_bytes=len(raw), after_bytes=len(candidate),
                               add_checked_include=include_added, preflight=preflight(name), sites=count_plans,
                               original_prewrite_prefix_unchanged=True, noncount_stream_operands_unchanged=True))
        diffs.append(''.join(difflib.unified_diff(raw.decode('latin1').splitlines(keepends=True),
                      text.splitlines(keepends=True), fromfile=name+'.before', tofile=name+'.after')))
    require(sum(len(r['sites']) for r in file_plans) == 18 and len(additions) == 12,
            'Unexpected source/recipe scope')
    require(not ({r['id'] for r in additions} & {r['id'] for r in specification['patches']}), 'Patch ID collision')
    updated_specification = dict(specification, patches=specification['patches'] + additions)
    nl = '\r\n' if b'\r\n' in old_spec else '\n'
    closing = (nl + '  ]' + nl + '}').encode()
    position = old_spec.rfind(closing)
    require(position > 0, 'Registry append layout changed')
    rendered = '\n'.join('  ' + line for line in json.dumps(additions, ensure_ascii=False, indent=2).splitlines()[1:-1])
    inserted = (',' + nl + rendered.replace('\n', nl)).encode('utf-8')
    new_spec = old_spec[:position] + inserted + old_spec[position:]
    require(json.loads(new_spec) == updated_specification and new_spec[:position] + new_spec[position+len(inserted):] == old_spec,
            'Existing patch registry bytes changed')
    outputs[PATCHES] = new_spec
    mn = '\r\n' if b'\r\n' in old_manifest else '\n'
    row_bytes = lambda row: mn.join('  ' + line for line in json.dumps(row, ensure_ascii=False, indent=2).splitlines()).encode()
    new_manifest, replacements = old_manifest, []
    for name in BASELINES:
        relative = 'CvGameCoreDLL_Expansion2/' + name
        generated, ids = replay(updated_specification, relative)
        require(generated == outputs[PORT/name], 'Proposed RAM replay differs: ' + name)
        row = next(r for r in manifest if r['relative_path'] == relative)
        updated = dict(row, port_sha256=digest(generated), patch_ids=ids)
        old_row, new_row = row_bytes(row), row_bytes(updated)
        require(new_manifest.count(old_row) == 1, 'Manifest row replacement not unique')
        new_manifest = new_manifest.replace(old_row, new_row, 1)
        replacements.append((old_row, new_row))
    restored = new_manifest
    for old_row, new_row in replacements:
        restored = once(restored, new_row, old_row)
    require(restored == old_manifest, 'Other manifest bytes changed')
    after_rows = json.loads(new_manifest)
    require(len(after_rows) == 1105 and sum(a != b for a, b in zip(manifest, after_rows)) == 8,
            'Unexpected manifest scope')
    outputs[MANIFEST] = new_manifest
    before += [artifact(PATCHES), artifact(MANIFEST)]
    for row in preserved:
        if row['cpp'] not in BASELINES:
            require((PORT/row['cpp']).is_file(), 'Preserved source missing')
    plan = dict(format=1, status='REVIEWED_FINITE_DIRECT_COUNT_PLAN', helper_sha256=digest(Path(__file__).read_bytes()),
                inventories=[artifact(INVENTORY_A), artifact(INVENTORY_B)], before=before,
                protected=[artifact(p) for p in protected_inputs(rows)],
                file_plans=file_plans, static_sites=18, native_width_fixes=15, cast_range_fixes=3,
                preserved_unsigned_sites=39, preserved_checked_sites=1,
                preserved_sites=preserved, new_patch_ids=[r['id'] for r in additions],
                patch_count_before=702, patch_count_after=714, manifest_rows=1105, manifest_rows_changed=8,
                proposed_outputs=[dict(path=str(p), bytes=len(raw), sha256=digest(raw)) for p, raw in outputs.items()],
                native_executed=False, installed_original_accessed=False, user_saves_accessed=False)
    return plan, outputs, ''.join(diffs).encode('utf-8')


def write_new(path, raw):
    guarded(path)
    require(not path.exists(), 'Evidence output already exists: ' + path.name)
    with path.open('xb') as stream:
        stream.write(raw)


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def verify():
    receipt = json.loads(RECEIPT.read_bytes())
    require(receipt['status'] == 'PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED', 'Patch publication not complete')
    for row in receipt['after'] + receipt['protected'] + receipt['evidence']:
        require(artifact(Path(row['path'])) == row, 'Published artifact content/identity changed: ' + row['path'])
    specification, manifest = json.loads(PATCHES.read_bytes()), json.loads(MANIFEST.read_bytes())
    for name in BASELINES:
        relative = 'CvGameCoreDLL_Expansion2/' + name
        generated, ids = replay(specification, relative)
        require(generated == (PORT/name).read_bytes(), 'Current source RAM replay differs')
        selected = [r for r in manifest if r['relative_path'] == relative]
        require(len(selected) == 1 and selected[0]['port_sha256'] == digest(generated) and selected[0]['patch_ids'] == ids,
                'Current source manifest differs')
    print(json.dumps(dict(status='PASS_FINITE_DIRECT_COUNT_PATCH_REPLAY', changed_cpp_files=8, static_sites=18,
                          native_width_fixes=15, cast_range_fixes=3, manifest_rows_changed=8,
                          native_executed=False, game_or_user_saves_accessed=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--apply', action='store_true')
    modes.add_argument('--verify', action='store_true')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.verify:
        require(args.plan_sha256 is None, 'Unexpected plan argument')
        verify()
        return
    require(not RECEIPT.exists(), 'Patch receipt already exists; use --verify')
    plan, outputs, diff = proposed()
    plan_raw = encoded(plan)
    if args.prepare:
        require(args.plan_sha256 is None, 'Unexpected plan argument')
        write_new(PLAN, plan_raw)
        write_new(DIFF, diff)
        print(json.dumps(dict(status='FINITE_DIRECT_COUNT_PLAN_READY', plan=str(PLAN), plan_sha256=digest(plan_raw),
                              diff_bytes=len(diff), changed_cpp_files=8, static_sites=18, mutable_sources_changed=False)))
        return
    require(args.plan_sha256 and digest(PLAN.read_bytes()) == args.plan_sha256 and PLAN.read_bytes() == plan_raw,
            'Reviewed plan/content/identities changed')
    require(DIFF.read_bytes() == diff, 'Reviewed source diff changed')
    backups = []
    for row in plan['before']:
        path = Path(row['path'])
        raw = path.read_bytes()
        require(artifact(path) == row, 'Baseline identity changed before backup')
        backup = STAGE/(path.name + '.before.gz')
        compressed = gzip.compress(raw, mtime=0)
        require(gzip.decompress(compressed) == raw, 'Backup roundtrip failed')
        write_new(backup, compressed)
        backups.append(dict(**artifact(backup), original_path=str(path), original_bytes=len(raw),
                            original_sha256=digest(raw), roundtrip_verified=True))
    report = dict(format=1, status='BACKED_UP_TRACKING_PENDING', created_utc=datetime.now(timezone.utc).isoformat(),
                  scope='Eight copied SDK translation units; fifteen native size_t wire widths and three checked signed cast ranges.',
                  before=plan['before'], protected=plan['protected'], backups=backups,
                  plan_sha256=args.plan_sha256, added_patch_ids=plan['new_patch_ids'],
                  generator_semantics='Copied SDK snapshot + ordered Latin1 exact replacements in RAM; no whole generator invoked.',
                  static_sites=18, native_width_fixes=15, cast_range_fixes=3, preserved_unsigned_sites=39,
                  preserved_checked_sites=1, manifest_rows_changed=8, full_generate_port_called=False,
                  installed_original_accessed=False, full_sdk_built=False, native_or_game_executed=False,
                  host_gamecore_or_hwnd_executed=False, user_saves_accessed=False,
                  full_player_verified=False, complete_save_verified=False, ruleset_compatibility_verified=False,
                  restore_approved=False)
    write_new(RECEIPT, encoded(report))
    baseline_by_path = {row['path']: row['sha256'] for row in plan['before']}
    for path, raw in outputs.items():
        atomic(path, raw, baseline_by_path[str(path)])
    for row in plan['protected']:
        require(artifact(Path(row['path'])) == row, 'Protected input changed during publication')
    report['after'] = [artifact(path) for path in outputs]
    report['evidence'] = [artifact(Path(__file__)), artifact(PLAN), artifact(DIFF), artifact(PRIOR_HELPER)]
    report['logical_delta_bytes'] = sum(r['bytes'] for r in report['after']) - sum(r['bytes'] for r in report['before'])
    report['retained_backups_bytes'] = sum(r['bytes'] for r in backups)
    report['status'] = 'PORT_PATCH_TRACKING_RAM_REGEN_VERIFIED'
    current = digest(RECEIPT.read_bytes())
    atomic(RECEIPT, encoded(report), current)
    verify()


if __name__ == '__main__':
    main()
