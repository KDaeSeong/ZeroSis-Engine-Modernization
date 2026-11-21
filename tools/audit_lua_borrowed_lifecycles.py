"""Record native lifetime boundaries and gaps before applying the Lua candidate."""
import json
import re
from collections import Counter
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from build_bootstrap_component import body
from verify_world_builder_map_object import check_artifacts
from define_lua_borrowed_patches import BASE, SCOPED, LUA, LIFECYCLE, patches, baseline_text, candidate_text
from build_lua_borrowed import TYPES


ROOT = 'CvGameCoreDLL_Expansion2/'
BOUNDARIES = {
    'Area': ('CvArea.cpp', ['CvArea::~CvArea()', 'void CvArea::uninit()', 'void CvArea::reset(', 'void CvArea::read(']),
    'City': ('CvCity.cpp', ['CvCity::~CvCity()', 'void CvCity::uninit()', 'void CvCity::reset(', 'void CvCity::read(']),
    'Unit': ('CvUnit.cpp', ['CvUnit::~CvUnit()', 'void CvUnit::uninit()', 'void CvUnit::reset(', 'void CvUnit::read(']),
    'Plot': ('CvPlot.cpp', ['CvPlot::~CvPlot()', 'void CvPlot::uninit()', 'void CvPlot::reset(', 'void CvPlot::read(']),
    'Player': ('CvPlayer.cpp', ['CvPlayer::~CvPlayer()', 'void CvPlayer::uninit()', 'void CvPlayer::reset(', 'void CvPlayer::Read(']),
    'Team': ('CvTeam.cpp', ['CvTeam::~CvTeam()', 'void CvTeam::uninit()', 'void CvTeam::reset(', 'void CvTeam::Read(']),
    'TeamTech': ('CvTechClasses.cpp', ['CvTeamTechs::~CvTeamTechs(', 'void CvTeamTechs::Init(', 'void CvTeamTechs::Uninit()', 'void CvTeamTechs::Reset()', 'void CvTeamTechs::Read(']),
    'Deal': ('CvDealClasses.cpp', ['CvDeal::~CvDeal()', 'CvDeal& CvDeal::operator=(', 'FDataStream& operator>>(FDataStream& loadFrom, CvDeal& writeTo)']),
    'League': ('CvVotingClasses.cpp', ['CvLeague::~CvLeague(', 'FDataStream& operator>>(FDataStream& loadFrom, CvLeague& writeTo)']),
}


def main():
    sdk = PROJECT/'Source/SDK_BNW_x64'
    master = PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(master.read_text(encoding='utf-8'))
    prior = json.loads(BASE.read_text(encoding='utf-8'))
    integrated = plan['patches'] == prior['patches']+patches()
    if not integrated and plan['patches'] != prior['patches']:
        raise RuntimeError('Unexpected active SDK patch plan')
    production_path = PROJECT/'evidence/sdk_x64/build_result.json'
    production = json.loads(production_path.read_text(encoding='utf-8'))
    if integrated and (production['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or
                       production['patch_specification']['sha256'] != digest(master)):
        raise RuntimeError('Integrated lifetime source has not compiled in the current SDK')
    candidate_root = PROJECT/'Build/LuaBorrowed/SDKCandidate/Source'
    root = PROJECT/'evidence/lua_borrowed'
    compiled_path = root/'sdk_candidate/build_result.json'
    compiled = json.loads(compiled_path.read_text(encoding='utf-8'))
    check_artifacts(compiled)
    if compiled['status'] != 'LUA_BORROWED_FULL_SDK_CANDIDATE_COMPILED':
        raise RuntimeError('Native candidate has not compiled')
    files = {}

    def read(source):
        path = sdk/source
        raw = path.read_bytes().decode('latin1')
        if raw != (candidate_text(source) if integrated else baseline_text(source)):
            raise RuntimeError('Accepted SDK source changed: '+source)
        files[source] = artifact(path)
        return baseline_text(source).replace('\r\n', '\n')

    def extract(source, signature):
        text = read(source)
        value = body(text, signature)
        candidate = candidate_text(source)
        candidate_file = candidate_root/source
        if candidate_file.read_bytes().decode('latin1') != candidate:
            raise RuntimeError('Compiled candidate source differs: '+source)
        after = body(candidate.replace('\r\n', '\n'), signature)
        hooks = re.findall(r'^    ZeroSisLuaBorrowed::(\w+) \w+\((.*?)\);\n', after, re.M)
        if hooks and re.sub(r'^    ZeroSisLuaBorrowed::\w+ \w+\(.*?\);\n', '', after, flags=re.M) != value:
            raise RuntimeError('Unexpected native lifecycle change: '+signature)
        return dict(source=source, signature=signature, line=text[:text.index(value)].count('\n')+1,
                    body=value, candidate_body=after, candidate_source=artifact(candidate_file),
                    candidate_hooks=[dict(kind=kind, target=target) for kind, target in hooks],
                    actual_native_execution=False, invalidation_hook_integrated=integrated and bool(hooks))

    bindings = []
    for name in TYPES:
        source = LUA+'CvLua'+name+'.h'
        match = re.search(r'class CvLua'+name+r'\s*:\s*public CvLuaScopedInstance<([^>]+)>', read(source))
        if not match:
            raise RuntimeError('Scoped binding changed: '+name)
        native, signatures = BOUNDARIES[name]
        bindings.append(dict(binding='CvLua'+name, template_types=match[1], header=source,
            boundaries=[extract(ROOT+native, signature) for signature in signatures]))
    derived = extract(ROOT+'CvPlayerAI.cpp', 'CvPlayerAI::~CvPlayerAI()')
    player_header = read(ROOT+'CvPlayerAI.h')
    if not re.search(r'class CvPlayerAI\s*:\s*public CvPlayer\s*\{', player_header):
        raise RuntimeError('PlayerAI inheritance changed')

    wrappers = []
    for name in ('City', 'Unit', 'Plot', 'Deal'):
        header = read(ROOT+'CvDll'+name+'.h')
        member = re.search(r'Cv'+name+r'\*\s+m_p'+name+r';', header)
        if not member:
            raise RuntimeError('Native interface ownership changed: '+name)
        wrappers.append(dict(native_interface='CvDll'+name, member=member[0],
            candidate_member=re.search(r'ZeroSisLuaBorrowed::NativeReference<Cv'+name+r'>\s+m_p'+name+r';',
                candidate_text(ROOT+'CvDll'+name+'.h'))[0],
            getter=extract(ROOT+'CvDll'+name+'.cpp', 'Cv'+name+'* CvDll'+name+'::GetInstance()'),
            lua_boundary=extract(ROOT+'CvDllScriptSystemUtility.cpp', 'void CvDllScriptSystemUtility::PushCv'+name+'Instance(')))

    vector_source = 'FirePlace/include/FireWorks/FFastVector.h'
    vector_text = read(vector_source)
    def excerpt(start, end):
        return dict(source=vector_source, first_line=start, last_line=end,
                    text='\n'.join(vector_text.splitlines()[start-1:end]))
    containers = dict(clear=excerpt(113, 120), destroy=excerpt(215, 223),
                      assignment=excerpt(615, 626), resize_and_erase=excerpt(663, 711), growth=excerpt(740, 810))
    member_calls = []
    scanned = []
    members = ('m_ProposedDeals', 'm_CurrentDeals', 'm_HistoricalDeals', 'm_vActiveLeagues')
    pattern = re.compile(r'\b('+'|'.join(members)+r')\s*\.\s*(\w+)\s*\(')
    for path in sorted((sdk/ROOT).rglob('*')):
        if path.suffix not in ('.cpp', '.h'): continue
        scanned.append(artifact(path))
        raw = path.read_bytes().decode('latin1')
        clean = re.sub(r'/\*.*?\*/|//[^\r\n]*', lambda m:'\n'*m[0].count('\n'), raw, flags=re.S)
        for match in pattern.finditer(clean):
            member_calls.append(dict(source=path.relative_to(sdk).as_posix(),
                line=clean[:match.start()].count('\n')+1, member=match[1], method=match[2]))
    mutations = [row for row in member_calls if row['method'] not in ('begin', 'end', 'size')]
    if {row['method'] for row in mutations} != {'clear', 'push_back'}:
        raise RuntimeError('Unreviewed direct Deal/League container mutation')
    containers.update(scanned_sources=scanned, direct_member_calls=member_calls, mutations=mutations,
        scope='NAMED_MEMBER_CALLS_WITH_COMMENTS_REMOVED_NOT_ALIAS_OR_INDIRECT_CALL_ANALYSIS')
    pch = next(phase for phase in compiled['phases'] if phase['phase'] == 'pch')['log']
    layout = read_text(Path(pch['path']))
    match = re.search(r'class CvPlayerAI\s+size\((\d+)\):\s*\r?\n\s*\+---\s*\r?\n\s*(\d+)\s*\| \+--- \(base class CvPlayer\)', layout)
    if not match or int(match[2]) != 0:
        raise RuntimeError('PlayerAI and Player address identity is unverified')
    player_layout = dict(log=pch, compiler=compiled['compiler'], target='MSVC_X64',
        size=int(match[1]), player_base_offset=int(match[2]), excerpt=match[0])
    accepted_build_path = BASE.parent/'build_result.json'
    accepted_build = json.loads(accepted_build_path.read_text(encoding='utf-8'))
    def warning_locations(phases, base, key):
        result = set()
        for phase in phases:
            for warning in phase[key]:
                start = warning.find(str(base))
                match = re.match(r'(.*?)\((\d+)\): warning (C\d+)', warning[start:]) if start >= 0 else None
                if not match: raise RuntimeError('Unclassified SDK candidate warning: '+warning)
                relative = Path(match[1]).resolve().relative_to(base).as_posix().lower()
                result.add((relative, int(match[2]), match[3]))
        return result
    before_warnings = warning_locations(accepted_build['executions'], sdk, 'unique_warning_lines')
    after_warnings = warning_locations(compiled['phases'], candidate_root, 'warnings')
    removed, added = sorted(before_warnings-after_warnings), sorted(after_warnings-before_warnings)
    if len(added) != 3 or [(f, n+4, c) for f, n, c in removed] != added:
        raise RuntimeError('Candidate SDK warning differences require review')
    warning_review = dict(accepted_build=artifact(accepted_build_path), normalized_locations=len(after_warnings),
        codes=dict(Counter(row[2] for row in after_warnings)), removed_locations=removed, added_locations=added,
        explanation='Three existing CvPlayer C4996 locations move by four inserted lines; normalize .. include paths before counting.')
    handle_source = 'FirePlace/include/FireWorks/FObjectHandle.h'
    handle_text = read(handle_source)
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', handle_text, flags=re.S)
    if re.search(r'^\s*#\s*define\s+TRACK_DESTRUCTION_NOTIFICATION\b', clean, re.M):
        raise RuntimeError('Destruction tracking default changed')
    findings = [
        dict(id='BORROWED-NATIVE-BOUNDARIES', priority='P1', status='HOOKS_NOT_APPLIED',
             detail='34 native lifetime hooks compile in the isolated candidate, but the accepted SDK and Stage still use attempt_036. Whole native-owner execution remains pending.'),
        dict(id='BORROWED-EXTERNAL-NATIVE-PROXIES', priority='P1', status='CANDIDATE_COMPONENT_PASS_HOST_ERROR_BOUNDARY_PENDING',
             detail='Four candidate proxies share the invalidation registry and reject expired access. Real execution of the new host error boundary and owner-thread lifetime locking remains pending.'),
        dict(id='BORROWED-CONTAINER-IDENTITY', priority='P1', status='DIRECT_SITES_AND_CONTAINER_COMPONENT_REVIEWED',
             detail='Observed named-member mutations are clear/push_back. Real SDK containers with instrumented Deal/League elements pass growth, clear/reuse, assignment, pop and destruction tests. This is not an alias analysis or execution of whole gameplay owners; scratch Deal remains mutable.'),
        dict(id='BORROWED-REAL-GAME-LIFECYCLE', priority='P1', status='NOT_EXECUTED',
             detail='Whole GameCore ownership, event callbacks, reset/load failure state and shutdown with live VMs remain unexecuted.'),
    ]
    if integrated:
        findings = [f for f in findings if f['id'] != 'BORROWED-NATIVE-BOUNDARIES']
    component = root/'conformance.json'
    conformance = json.loads(component.read_text(encoding='utf-8'))
    check_artifacts(conformance)
    if any(row['results']['deal_self_copy_losses'] != (0 if row['variant'].startswith('candidate') else 3)
           for row in conformance['runs']):
        raise RuntimeError('Deal self-copy defect has not been reproduced and repaired')
    report = dict(status='BORROWED_LIFECYCLE_SOURCE_AUDIT_WITH_COMPONENT_EVIDENCE',
        auditor=artifact(Path(__file__).resolve()), baseline=artifact(BASE), component=artifact(component),
        source_files=list(files.values()), bindings=bindings, player_derived_destructor=derived,
        native_interfaces=wrappers, container_evidence=containers, candidate_compile=artifact(compiled_path),
        production_compile=artifact(production_path) if integrated else None,
        warning_review=warning_review,
        candidate_native_hooks=sum(map(len, LIFECYCLE.values())), player_layout=player_layout,
        resolved_source_findings=[dict(id='BORROWED-PLAYER-BASE-IDENTITY', status='CURRENT_MSVC_X64_BASE_OFFSET_ZERO',
            detail='The full SDK PCH layout places CvPlayer at offset zero in CvPlayerAI. Both destructors have candidate hooks; future ABI changes require repeating this check.')],
        resolved_component_findings=[dict(id='DEAL-SELF-ASSIGNMENT', status='EXACT_ASSIGNMENT_AND_COPYFROM_BODIES_ADAPTER_PASS',
            detail='The original loses nonempty trade-item lists in three sizes; the candidate keeps all values and existing Lua identity. Ordinary distinct copies agree. The trade-item list and native owners are instrumented.')],
        handle_tracking_define_in_header_active=False, open_findings=findings,
        candidate_applied_to_sdk=integrated, gamecore_loaded=False, game_launched=False)
    (root/'lifecycle_audit.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(status=report['status'], bindings=len(bindings),
        native_boundaries=sum(len(b['boundaries']) for b in bindings)+1,
        raw_native_interfaces=len(wrappers), open_findings=len(findings))))


if __name__ == '__main__':
    main()
