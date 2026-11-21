"""Propagate required rule-cache failures through the real GC database startup phase."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'db_cache_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_029/sdk_x64_patches.json'
UTILITY = 'CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.cpp'
HEADER = 'CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.h'
GLOBALS = 'CvGameCoreDLL_Expansion2/CvGlobals.cpp'
TYPES = 'CvGameCoreDLL_Expansion2/CvTypes.cpp'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for p in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if p['file'] == relative:
            if text.count(p['old']) != p['count']:
                raise RuntimeError('Database cache baseline changed: ' + p['id'])
            text = text.replace(p['old'], p['new'])
    return text


def database_phase(text):
    init = body(text, 'void CvGlobals::init()')
    start = init.find('\tauto_ptr<ICvDLLDatabaseUtility1>')
    if start < 0:
        start = init.index('\tDatabase::Connection* pDB = GetGameDatabase();')
    return init[start:init.index('\tmemcpy(', start)]


def patches():
    result = []
    def add(name, relative, old, new, reason):
        text = baseline_text(relative)
        if text.count(old) != 1:
            raise RuntimeError('Database cache patch mismatch: ' + name)
        new = new.replace('\r\n', '\n')
        if '\r\n' in text:
            new = new.replace('\n', '\r\n')
        result.append({'id': PREFIX + name, 'file': relative,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / relative),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})

    text = baseline_text(HEADER)
    add('checked_prefetch', HEADER, body(text, 'template<class T>\r\nbool CvDllDatabaseUtility::PrefetchCollection('), '''template<class T>
bool CvDllDatabaseUtility::PrefetchCollection(std::vector<T*>& kCollection, const char* szTableName)
{
    cvStopWatch kPerfTest(szTableName, "xml-perf.log");
    // Prepare and inspect the schema before replacing the previous collection.
    Database::Results kResults;
    if(!DB.SelectWhere(kResults, szTableName, "ID > -1 ORDER BY ID") || !kResults.HasColumn("ID")) return false;
    const int idColumn = kResults.ColumnPosition("ID");
    for(typename std::vector<T*>::iterator it = kCollection.begin(); it != kCollection.end(); ++it) delete *it;
    kCollection.clear();
    size_t index = 0;
    CvDatabaseUtility kUtility;
    while(kResults.Step())
    {
        // Do not narrow a malformed ID into a huge size_t gap or publish duplicates.
        if(kResults.ColumnType(idColumn) != Database::COLTYPE_INT) return false;
        const long long rawId = kResults.GetInt64(idColumn);
        if(rawId < 0 || rawId > 2147483647LL) return false;
        const size_t Id = static_cast<size_t>(rawId);
        if(Id < index) return false;
        while(Id > index) { kCollection.push_back(NULL); ++index; }
        std::unique_ptr<T> pkItem(FNEW(T, c_eCiv5GameplayDLL, 0));
        if(!pkItem->CacheResults(kResults, kUtility)) return false;
        kCollection.push_back(pkItem.get());
        pkItem.release();
        ++index;
    }
    // SQLite DONE is normal exhaustion; every other terminal status is failure.
    return DB.ErrorCode() == 101;
}''', 'Check preparation, schema, ID range/order, row-cache result and SQL exhaustion; preserve scoped unpublished ownership and caller-owned partial progress.')

    text = baseline_text(UTILITY)
    add('checked_cache_stages', UTILITY, body(text, 'bool CvDllDatabaseUtility::CacheGameDatabaseData()'), '''bool CvDllDatabaseUtility::CacheGameDatabaseData()
{
    if(m_bGameDatabaseNeedsCaching == false) return true;
    // Existing optional validation remains diagnostic, not a new compatibility gate.
    ValidateGameDatabase();
    GC.infoTypeFromStringReset();
    Database::Results kTables("name");
    if(!DB.SelectAt(kTables, "sqlite_master", "type", "table")) return false;
    while(kTables.Step())
    {
        const char* table = kTables.GetText(0);
        if(table == NULL) return false;
        Database::Results kTypes;
        if(!DB.SelectAll(kTypes, table)) return false;
        // Custom tables without info keys are intentionally outside this lookup.
        if(!kTypes.HasColumn("ID") || !kTypes.HasColumn("Type")) continue;
        while(kTypes.Step())
        {
            const int rowid = kTypes.GetInt("ID");
            const char* szType = kTypes.GetText("Type");
            if(szType) GC.setInfoTypeFromString(szType, rowid);
        }
        if(DB.ErrorCode() != 101) return false;
    }
    if(DB.ErrorCode() != 101) return false;
    if(!LoadGlobalDefines() || !PrefetchGameData() || !UpdatePlayableCivilizationCounts()) return false;
    CvTypes::AcquireTypes(DB);
    if(!SetGlobalActionInfo()) return false;
    DB.ClearCountCache();
    LogMsg("%s", DB.CalculateMemoryStats());
    m_bGameDatabaseNeedsCaching = false;
    return true;
}''', 'Stop on the first required SQL/cache stage failure and publish the cached flag only after all stages complete; keep legacy validation diagnostic.')

    old = body(text, 'bool CvDllDatabaseUtility::PrefetchGameData()')
    new = old.replace('\r\n', '\n')
    new, count = re.subn(r'(?m)^(\s*)PrefetchCollection\((.+)\);$', r'\1if(!PrefetchCollection(\2)) return false;', new)
    if count != 62:
        raise RuntimeError('Expected sixty-two collection calls')
    start = new.index('\t//Copy flavors into string array')
    end = new.index('\tValidatePrefetchProcess();', start)
    new = new[:start] + '\tif(!ZeroSisCacheFlavorTypes()) return false;\n\n' + new[end:]
    helper = '''// Build the flavor array privately so failed reads retain the previous array.
static bool ZeroSisCacheFlavorTypes()
{
    Database::Results maximum;
    if(!DB.Execute(maximum, "SELECT max(rowid) from Flavors") || !maximum.Step()) return false;
    if(maximum.ColumnType(0) != Database::COLTYPE_INT && maximum.ColumnType(0) != Database::COLTYPE_NULL) return false;
    const long long maxRow = maximum.GetInt64(0);
    if(maxRow < -1 || maxRow >= 2147483647LL) return false;
    const int count = static_cast<int>(maxRow + 1); // Preserve SDK MaxRows, including an empty table's one slot.
    if(maximum.Step() || DB.ErrorCode() != 101) return false;
    Database::Results rows;
    if(!DB.SelectWhere(rows, "Flavors", "ID > -1") || !rows.HasColumn("ID") || !rows.HasColumn("Type")) return false;
    const int idColumn = rows.ColumnPosition("ID");
    std::unique_ptr<CvString[]> ready(FNEW(CvString[count], c_eCiv5GameplayDLL, 0));
    std::vector<bool> seen(static_cast<size_t>(count), false);
    while(rows.Step())
    {
        if(rows.ColumnType(idColumn) != Database::COLTYPE_INT) return false;
        const long long id = rows.GetInt64(idColumn);
        const char* type = rows.GetText("Type");
        if(id < 0 || id >= count || type == NULL || seen[static_cast<size_t>(id)]) return false;
        ready[static_cast<size_t>(id)] = type;
        seen[static_cast<size_t>(id)] = true;
    }
    if(DB.ErrorCode() != 101) return false;
    CvString*& flavors = GC.getFlavorTypes();
    std::unique_ptr<CvString[]> previous(flavors);
    flavors = ready.release();
    GC.setNumFlavorTypes(count);
    return true;
}

'''
    add('prefetch_stages_and_flavors', UTILITY, old, helper + new,
        'Propagate each required collection failure and atomically publish the flavor array after checked SQL and ID/type reads.')

    text = baseline_text(TYPES)
    add('types_exception_include', TYPES, '#include "CvTypes.h"', '#include "CvTypes.h"\n#include <stdexcept>',
        'Keep the existing void type acquisition ABI while reporting actual SQL failures by exception.')
    old = body(text, 'void CvTypes::AcquireTypes(')
    new = old.replace('\r\n', '\n')
    for table in ('GreatWorkArtifactClasses', 'GreatWorkSlots', 'Missions'):
        block = body(new, '\t\tif(db.Execute(kResults, "SELECT Type, ID from ' + table + '"))')
        replacement = block.replace('\t\tif(db.Execute(kResults, "SELECT Type, ID from ' + table + '"))',
            '\t\tif(!db.Execute(kResults, "SELECT Type, ID from ' + table + '"))\n\t\t\tthrow std::runtime_error("GameCore type query failed: ' + table + '");')
        replacement = replacement.replace('\t\t\twhile(kResults.Step())\n\t\t\t{',
            '\t\t\twhile(kResults.Step())\n\t\t\t{\n\t\t\t\tif(kResults.GetText(0) == NULL) throw std::runtime_error("GameCore type name is null: ' + table + '");')
        replacement += '\n\t\tif(db.ErrorCode() != 101) throw std::runtime_error("GameCore type iteration failed: ' + table + '");'
        new = new.replace(block, replacement)
    new = new.replace('\t\tif(iNumTypes >= 0)', '\t\tif(iNumTypes < 0) throw std::runtime_error("GameCore mission count failed");\n\t\tif(iNumTypes >= 0)')
    add('checked_type_queries', TYPES, old, new,
        'Reject SQL prepare/step failures and null type names, check mission count, and retain missing-enum diagnostic behavior.')

    text = baseline_text(GLOBALS)
    add('globals_exception_include', GLOBALS, '#include "ZeroSisHostBinding.h"', '#include "ZeroSisHostBinding.h"\n#include <stdexcept>',
        'Declare explicit startup failure without changing the GC interface or object layout.')
    old = database_phase(text)
    new = '''\tDatabase::Connection* pDB = GetGameDatabase();
\tif(pDB == NULL) throw std::runtime_error("GameCore initialization requires a database");
\tZeroSisHostBinding::Owned<ICvDLLDatabaseUtility1> pkLoader(getDatabaseLoadUtility());
\tif(!pkLoader) throw std::runtime_error("GameCore database loader is unavailable");
\tif(!pDB->Execute(m_kGlobalDefinesLookup, "SELECT Value from Defines where Name = ? LIMIT 1"))
\t\tthrow std::runtime_error("GameCore define query preparation failed");
\tif(!pkLoader->PerformDatabasePostProcessing())
\t\tthrow std::runtime_error("GameCore database postprocessing failed");
\tif(!pkLoader->CacheGameDatabaseData())
\t\tthrow std::runtime_error("GameCore database cache failed");

\tCvPlayerAI::initStatics();
\tCvTeam::initStatics();

'''
    add('stop_failed_database_startup', GLOBALS, old, new,
        'Check the database before the loader factory; release the local queried interface through Destroy and stop before player/team creation on required DB failure. Root rollback remains a separate controller.')
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 572:
        raise RuntimeError('Accepted 572 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lp = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(lp.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_database_cache_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    lp.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/database_cache'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_DATABASE_CACHE_CALLERS_DECLARED', 'baseline': ledger['unchanged_database_cache_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)}, 'previous_patches': 572,
              'added_patches': len(added), 'total_patches': len(plan['patches']),
              'files': sorted({p['file'] for p in added}), 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
