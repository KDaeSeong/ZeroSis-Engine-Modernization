"""Prepare a read-only, explicit Build cleanup manifest. Never deletes files."""
import hashlib,json,re,stat
from datetime import datetime,timezone
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact

BUILD=(PROJECT/'Build').resolve()


def inventory(directory):
    directory=directory.resolve(strict=True)
    if not directory.is_relative_to(BUILD) or directory==BUILD:
        raise RuntimeError('Cleanup target must be strictly inside this project Build directory')
    rows=[]
    for path in sorted(directory.rglob('*')):
        info=path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError('Cleanup tree contains a link/reparse point: '+str(path))
        if path.is_file():
            if not path.resolve(strict=True).is_relative_to(directory):raise RuntimeError('Cleanup file escaped its target')
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            rows.append({'relative_path':str(path.relative_to(directory)),'bytes':info.st_size,
                         'mtime_ns':info.st_mtime_ns,'sha256':digest})
    return {'path':str(directory),'file_count':len(rows),'bytes':sum(row['bytes'] for row in rows),'files':rows}


def absolute_references(value):
    if isinstance(value,dict):
        for item in value.values():yield from absolute_references(item)
    elif isinstance(value,list):
        for item in value:yield from absolute_references(item)
    elif isinstance(value,str):
        try:
            path=Path(value)
            if path.is_absolute() and path.is_relative_to(BUILD):yield path
        except (OSError,ValueError):pass


def main():
    run=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory=PROJECT/'evidence/build_cleanup'/run;directory.mkdir(parents=True,exist_ok=False)
    candidates=[];kept=[];unknown=[]
    for attempt in sorted((BUILD/'SDK_x64').iterdir()):
        if not attempt.is_dir():continue
        match=re.fullmatch(r'attempt_(\d{3})',attempt.name)
        if match and 1<=int(match[1])<=36:
            candidates.append({'group':'historical_sdk_attempts','reason':'Superseded by accepted SDK attempt_037',**inventory(attempt)})
        else:kept.append({'path':str(attempt),'reason':'Current or unclassified SDK build'})
    for attempt in sorted((BUILD/'NewGameRuntime').iterdir()):
        if not attempt.is_dir():continue
        reports=[PROJECT/'evidence'/kind/attempt.name/'result.json' for kind in ('new_game','first_turn')]
        reports=[path for path in reports if path.is_file()]
        if len(reports)!=1:
            unknown.append(str(attempt));continue
        report=json.loads(reports[0].read_text(encoding='utf-8'));status=report['status']
        if status in ('ISOLATED_NEW_GAME_CANDIDATE_FAILED','ISOLATED_FIRST_TURN_ENTRY_FAILED'):
            candidates.append({'group':'failed_isolated_runtime_copies','reason':status,'execution_result':artifact(reports[0]),**inventory(attempt)})
        elif status in ('ISOLATED_NEW_GAME_CANDIDATE_PASS','ISOLATED_FIRST_TURN_ENTRY_PASS'):
            kept.append({'path':str(attempt),'reason':status,'execution_result':artifact(reports[0]),**inventory(attempt)})
        else:unknown.append(str(attempt))
    critical_names=['evidence/sdk_x64/attempts/attempt_037/build_result.json','evidence/sdk_x64/link_analysis.json',
        'evidence/shared_lua_runtime/build_result.json','evidence/new_game_sdk/build_result.json','evidence/host/bundle.json']
    targets=[Path(row['path']) for row in candidates];protected=set();reports=[]
    for name in critical_names:
        path=PROJECT/name;reports.append(artifact(path));data=json.loads(path.read_text(encoding='utf-8'))
        protected.update(absolute_references(data))
    for path in sorted(protected):
        if any(path==target or path.is_relative_to(target) for target in targets):
            raise RuntimeError('Current build references a proposed cleanup target: '+str(path))
    # These frozen link recipes are actual input paths for the next candidate link.
    recipes=[BUILD/'SharedLuaRuntime/GameCore/link.rsp',BUILD/'NewGameSDK/link.rsp']
    for recipe in recipes:
        text=recipe.read_text(encoding='utf-8').casefold()
        if any(str(target).casefold() in text or target.as_posix().casefold() in text for target in targets):
            raise RuntimeError('A current link recipe uses a proposed cleanup target')
        reports.append(artifact(recipe))
    groups={}
    for row in candidates:
        group=groups.setdefault(row['group'],{'directories':0,'files':0,'bytes':0})
        group['directories']+=1;group['files']+=row['file_count'];group['bytes']+=row['bytes']
    report={'status':'PROPOSED_NOT_DELETED','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'project_root':str(PROJECT),'build_root':str(BUILD),'planner':artifact(Path(__file__).resolve()),
        'groups':groups,'total_bytes':sum(row['bytes'] for row in candidates),'targets':candidates,
        'kept':kept,'unclassified_preserved':unknown,'current_dependency_reports':reports,
        'protected_build_paths':len(protected),'dependency_overlap_count':0,
        'scope':'Only superseded SDK Build attempts 001-036 and failed NewGameRuntime execution copies',
        'consequence':'Old deleted executables/intermediates cannot be rerun without rebuilding. Historical evidence logs and source snapshots remain.',
        'excluded':['Source','tools','Tests','docs','Stage','evidence','installed game','MODS','user saves'],
        'deletion_authorized':False,'deleted_files':0}
    output=directory/'plan.json';output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (directory.parent/'latest.json').write_text(json.dumps(artifact(output),indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'plan':str(output),'groups':groups,'gib':report['total_bytes']/1024**3,
        'kept_runtime':[row['path'] for row in kept if 'execution_result' in row],'unclassified_preserved':unknown}))


if __name__=='__main__':main()
