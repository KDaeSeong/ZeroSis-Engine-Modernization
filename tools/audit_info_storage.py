"""Record direct rule ownership inventory and source-level teardown dependencies."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from build_bootstrap_component import body
from define_info_cleanup_patches import GLOBALS, HEADER, LOADER, baseline_text, collections


def main():
    root = PROJECT / 'Source/SDK_BNW_x64'
    old = body(baseline_text(GLOBALS), 'void CvGlobals::deleteInfoArrays()')
    current = (root / GLOBALS).read_bytes().decode('latin1')
    cleanup = body(current, 'void CvGlobals::deleteInfoArrays()')
    before = re.findall(r'deleteInfoArray\((m_\w+)\)', old)
    after = re.findall(r'deleteInfoArray\((m_\w+)\)', cleanup)
    declared = collections()
    if len(after) != 40 or set(after) != {name for _, name in declared}:
        raise RuntimeError('Direct rule collection ownership inventory incomplete')
    strings = re.findall(r'CvString\*\s+(m_pasz\w+);', (root / HEADER).read_bytes().decode('latin1'))
    if set(strings) != {'m_paszFlavorTypes', 'm_paszFootstepAudioTags'} or any('SAFE_DELETE_ARRAY(' + name + ')' not in cleanup for name in strings):
        raise RuntimeError('Direct string-array inventory incomplete')
    teardown = []
    owners = {'CvGame.cpp': ('void CvGame::uninit(',), 'CvMap.cpp': ('void CvMap::uninit(',),
              'CvPlayer.cpp': ('void CvPlayer::uninit(',), 'CvTeam.cpp': ('void CvTeam::uninit(',),
              'CvAStar.cpp': ('CvAStar::~CvAStar(', 'CvTwoLayerPathFinder::~CvTwoLayerPathFinder(')}
    for file, sigs in owners.items():
        p = root / 'CvGameCoreDLL_Expansion2' / file
        text = p.read_bytes().decode('latin1')
        for sig in sigs:
            b = body(text, sig)
            teardown.append({'source': artifact(p), 'signature': sig,
                             'direct_gc_or_host_calls': sorted(set(re.findall(r'\b(?:GC\.|gDLL->)\w+', b)))})
    destructors = []
    classes = {kind for kind, _ in declared}
    for p in sorted((root / 'CvGameCoreDLL_Expansion2').glob('*.cpp')):
        text = p.read_bytes().decode('latin1')
        for cls in sorted(classes):
            sig = cls + '::~' + cls + '('
            if sig in text:
                b = body(text, sig)
                destructors.append({'source': artifact(p), 'class': cls, 'body': b.replace('\r\n', '\n'),
                                    'direct_gc_or_host_calls': sorted(set(re.findall(r'\b(?:GC\.|gDLL->)\w+', b)))})
    report = {'status': 'DIRECT_RULE_STORAGE_SOURCE_AUDIT_PASS_NOT_COMPLETE_DESTRUCTOR_CALL_GRAPH',
              'auditor': artifact(Path(__file__).resolve()),
              'sources': [artifact(root / rel) for rel in (GLOBALS, HEADER, LOADER)],
              'direct_pointer_collections': [{'type': cls, 'field': name} for cls, name in declared],
              'original_cleanup_fields': before, 'candidate_cleanup_fields': after,
              'original_missing_collections': sorted({name for _, name in declared} - set(before)),
              'direct_string_arrays': strings, 'selected_borrower_teardown_references': teardown,
              'explicit_out_of_line_info_destructors': destructors,
              'uninit_cleanup_body': body(current, 'void CvGlobals::uninit()').replace('\r\n', '\n'),
              'scope': 'DECLARED_DIRECT_FIELDS_AND_TEXTUAL_REFERENCES_NOT_ALL_TRANSITIVE_BASE_MEMBER_DESTRUCTORS_OR_GAME_RUNTIME',
              'all_concrete_info_destructors_executed': False, 'gamecore_loaded': False, 'game_launched': False}
    out = PROJECT / 'evidence/info_cleanup/source_audit.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'collections': len(after), 'string_arrays': len(strings),
                      'explicit_info_destructors': len(destructors), 'borrower_methods': len(teardown)}))


if __name__ == '__main__':
    main()
