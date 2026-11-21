"""Make directly owned startup storage survive throwing constructors correctly."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'construction_callers_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_024/sdk_x64_patches.json'
GAME = 'CvGameCoreDLL_Expansion2/CvGame.cpp'
MAP = 'CvGameCoreDLL_Expansion2/CvMap.cpp'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == relative:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Constructor baseline drift: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def patches():
    result = []
    def add(name, relative, old, new, reason):
        if baseline_text(relative).count(old) != 1:
            raise RuntimeError('Constructor patch match changed: ' + name)
        result.append({'id': PREFIX + name, 'file': relative,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / relative),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    game = baseline_text(GAME)
    newline = '\r\n' if '\r\n' in game else '\n'
    add('memory_include', GAME, '#include <sstream>', '#include <sstream>' + newline + '#include <memory>',
        'Declare scoped array ownership explicitly without changing CvGame layout.')
    old = body(game, 'CvGame::CvGame()')
    owned = re.findall(r'\t(m_ai\w+) = (FNEW\(int\[(MAX_\w+)\], c_eCiv5GameplayDLL, 0\));[^\r\n]*', old)
    if len(owned) != 7:
        raise RuntimeError('Expected seven directly owned CvGame constructor arrays')
    new = old
    for field, allocation, _ in owned:
        statement = field + ' = ' + allocation + ';'
        replacement = ('std::unique_ptr<int[]> owned_' + field + '(' + allocation + ');' + newline
                       + '\t' + field + ' = owned_' + field + '.get();')
        new = new.replace(statement, replacement)
    release = newline.join('\towned_' + field + '.release();' for field, _, _ in owned)
    end = '\treset(NO_HANDICAP, true);'
    if new.count(end) != 1:
        raise RuntimeError('CvGame constructor completion changed')
    new = new.replace(end, end + newline + newline
                      + '\t// Publish ownership only after timer/reset callbacks have completed.' + newline + release)
    add('game_owned_arrays', GAME, old, new,
        'Keep seven arrays scoped through every allocation, timer and reset call; transfer ownership only when construction completes.')
    old = body(baseline_text(MAP), 'CvMap::CvMap()')
    newline = '\r\n' if '\r\n' in old else '\n'
    end = '\treset(&defaultMapData);'
    if old.count(end) != 1:
        raise RuntimeError('CvMap constructor reset changed')
    replacement = '''\ttry
\t{
\t\treset(&defaultMapData);
\t}
\tcatch(...)
\t{
\t\t// A throwing constructor will not run ~CvMap().
\t\tuninit();
\t\t--sgCvMapInstanceCount;
\t\tthrow;
\t}'''.replace('\n', newline)
    add('map_partial_cleanup', MAP, old, old.replace(end, replacement),
        'Release partial reset storage and restore the live-map counter if construction throws, preserving the original exception.')
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    base = json.loads(BASE.read_text(encoding='utf-8'))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 553:
        raise RuntimeError('Accepted 553 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('host_callers_', 'db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [
        x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_construction_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/construction'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_CONSTRUCTION_CALLERS_DECLARED', 'baseline': ledger['unchanged_construction_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)},
              'previous_patches': 553, 'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': sorted({p['file'] for p in added}), 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
