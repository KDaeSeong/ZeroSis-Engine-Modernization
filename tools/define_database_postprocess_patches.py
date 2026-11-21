"""Make actual GameCore database postprocessing report and roll back failures."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest
from build_bootstrap_component import body

PREFIX = 'db_postprocess_'
BASE = PROJECT / 'evidence/sdk_x64/attempts/attempt_026/sdk_x64_patches.json'
TARGET = 'CvGameCoreDLL_Expansion2/CvDllDatabaseUtility.cpp'


def baseline_text(relative):
    text = (PROJECT / 'Source/SDK_BNW_Original' / relative).read_bytes().decode('latin1')
    for patch in json.loads(BASE.read_text(encoding='utf-8'))['patches']:
        if patch['file'] == relative:
            if text.count(patch['old']) != patch['count']:
                raise RuntimeError('Postprocessing baseline drift: ' + patch['id'])
            text = text.replace(patch['old'], patch['new'])
    return text


def patches():
    text = baseline_text(TARGET)
    helper = '''namespace
{
// A private savepoint preserves a transaction already owned by the caller.
// Connection/Results operations require a single serialized owner.
class ZeroSisPostProcessTransaction
{
public:
    explicit ZeroSisPostProcessTransaction(Database::Connection& db) : db_(db), active_(false) {}
    ~ZeroSisPostProcessTransaction() { if(active_) { try { Rollback(); } catch(...) {} } }
    bool Begin()
    {
        active_ = db_.Execute("SAVEPOINT ZeroSis_GameCore_PostProcess");
        return active_;
    }
    bool Commit()
    {
        if(!db_.Execute("RELEASE SAVEPOINT ZeroSis_GameCore_PostProcess")) return false;
        active_ = false;
        return true;
    }
    bool Rollback()
    {
        if(!active_) return true;
        if(!db_.Execute("ROLLBACK TO SAVEPOINT ZeroSis_GameCore_PostProcess")) return false;
        if(!db_.Execute("RELEASE SAVEPOINT ZeroSis_GameCore_PostProcess")) return false;
        active_ = false;
        return true;
    }
private:
    ZeroSisPostProcessTransaction(const ZeroSisPostProcessTransaction&);
    ZeroSisPostProcessTransaction& operator=(const ZeroSisPostProcessTransaction&);
    Database::Connection& db_;
    bool active_;
};
}

bool InsertGameDefine(Database::Results& kInsertDefine, const char* szValue, int iValue)
{
    return kInsertDefine.Bind(1, szValue) && kInsertDefine.Bind(2, iValue)
        && kInsertDefine.Execute() && kInsertDefine.Reset();
}'''
    operation = '''bool CvDllDatabaseUtility::PerformDatabasePostProcessing()
{
    Database::Connection* db = GC.GetGameDatabase();
    if(db == NULL) return false;
    ZeroSisPostProcessTransaction transaction(*db);
    if(!transaction.Begin()) return false;
    const bool success = [&]() -> bool
    {
        Database::Results kInsert;
        Database::Results kPostDefines;
        if(!db->Execute(kInsert, "INSERT OR REPLACE INTO Defines(Name, Value) VALUES(?, ?)")) return false;
        if(!db->SelectAll(kPostDefines, "PostDefines") || !kPostDefines.HasColumn("Name")
            || !kPostDefines.HasColumn("Key") || !kPostDefines.HasColumn("Table")) return false;
        while(kPostDefines.Step())
        {
            const char* name = kPostDefines.GetText("Name");
            const char* key = kPostDefines.GetText("Key");
            const char* table = kPostDefines.GetText("Table");
            if(name == NULL || *name == '\\0' || key == NULL || table == NULL || *table == '\\0') return false;
            std::string sql("SELECT ROWID FROM \\\"");
            for(const char* p = table; *p; ++p)
            {
                sql += *p;
                if(*p == '\\"') sql += '\\"';
            }
            sql += "\\\" WHERE Type = ? LIMIT 1";
            Database::Results lookup;
            if(!db->Execute(lookup, sql.c_str()) || !lookup.Bind(1, key)) return false;
            if(lookup.Step())
            {
                if(!InsertGameDefine(kInsert, name, lookup.GetInt(0))) return false;
            }
            // SQLite's DONE (101) means an absent optional key, not an SQL error.
            // Preserve the original behavior of leaving that define unchanged.
            else if(db->ErrorCode() != 101) return false;
        }
        if(db->ErrorCode() != 101) return false;
        kPostDefines.Release();
        kInsert.Release();
        if(!db->Execute("UPDATE Resources SET ResourceUsage = 1 WHERE EXISTS (SELECT * FROM Unit_ResourceQuantityRequirements WHERE ResourceType = Type)")) return false;
        if(!db->Execute("UPDATE Resources SET ResourceUsage = 2 where Happiness > 0")) return false;
        Database::Results kInsertDefine;
        if(!db->Execute(kInsertDefine, "INSERT OR REPLACE INTO Defines(Name, Value) VALUES(?, ?);")) return false;
CONSTANT_INSERTS
        return true;
    }();
    if(success && transaction.Commit()) return true;
    if(!transaction.Rollback()) throw std::runtime_error("GameCore postprocessing rollback failed; discard this database connection");
    return false;
}'''
    constants = ('MAX_CIV_PLAYERS', 'MAX_CIV_TEAMS', 'MAX_MAJOR_CIVS', 'MAX_MINOR_CIVS',
                 'MAX_PLAYERS', 'MAX_TEAMS', 'BARBARIAN_PLAYER', 'BARBARIAN_TEAM',
                 'NUM_CITY_PLOTS', 'CITY_HOME_PLOT', 'CITY_PLOTS_RADIUS', 'CITY_PLOTS_DIAMETER')
    operation = operation.replace('CONSTANT_INSERTS', '\n'.join(
        '        if(!InsertGameDefine(kInsertDefine, "' + key + '", ' + key + ')) return false;' for key in constants))
    result = []
    for name, old, new, reason in (
        ('includes', '#include <algorithm>', '#include <algorithm>\n#include <string>\n#include <stdexcept>', 'Use bounded strings and explicit irrecoverable rollback failure.'),
        ('transaction_and_insert', body(text, 'void InsertGameDefine('), helper, 'Use a caller-preserving savepoint and check every bind/execute/reset result.'),
        ('checked_operation', body(text, 'bool CvDllDatabaseUtility::PerformDatabasePostProcessing()'), operation,
         'Preserve valid rules and optional absent-key behavior, quote table identifiers, bind keys, reject malformed metadata, and commit only the complete operation.')):
        if text.count(old) != 1:
            raise RuntimeError('Postprocess patch mismatch: ' + name)
        new = new.replace('\r\n', '\n')
        if '\r\n' in text:
            new = new.replace('\n', '\r\n')
        result.append({'id': PREFIX + name, 'file': TARGET,
                       'source_sha256': digest(PROJECT / 'Source/SDK_BNW_Original' / TARGET),
                       'old': old, 'new': new, 'count': 1, 'reason': reason})
    return result


def main():
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    retained = [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    if retained != base['patches'] or len(retained) != 560:
        raise RuntimeError('Accepted 560 SDK patches changed')
    added = patches()
    later = [p for p in plan['patches'] if p['id'].startswith(('db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
    plan['patches'] = retained + added + later
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    ledger_path = PROJECT / 'evidence/numeric_boundaries/edit_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256'] = digest(path)
    ledger['supplemental_non_numeric_patches'] = [x for x in ledger['supplemental_non_numeric_patches'] if not x.startswith((PREFIX, 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] + [p['id'] for p in added + later]
    ledger['unchanged_database_postprocess_baseline'] = {'path': str(BASE), 'sha256': digest(BASE)}
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    root = PROJECT / 'evidence/database_postprocess'
    root.mkdir(parents=True, exist_ok=True)
    report = {'status': 'SDK_DATABASE_POSTPROCESS_CALLERS_DECLARED', 'baseline': ledger['unchanged_database_postprocess_baseline'],
              'recipe': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__).resolve())},
              'patch_specification': {'path': str(path), 'sha256': digest(path)}, 'previous_patches': 560,
              'added_patches': len(added), 'total_patches': len(plan['patches']), 'files': [TARGET], 'patches': added,
              'gamecore_loaded': False, 'game_launched': False}
    (root / 'caller_patch_plan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'added_patches', 'total_patches')}))


if __name__ == '__main__':
    main()
