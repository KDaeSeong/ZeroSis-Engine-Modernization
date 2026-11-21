#include "SdkDatabaseIncludes.h"
using PlayerTypes = int;
using TeamTypes = int;
#include "database_postprocess_defines.h"

unsigned checks = 0;
void Check(bool ok, unsigned line) {
    ++checks;
    if (!ok) { std::printf("FAIL|%u\n", line); std::fflush(stdout); std::exit(2); }
}
#define CHECK(c) Check(!!(c), __LINE__)
struct Globals {
    Database::Connection* db = nullptr;
    Database::Connection* GetGameDatabase() { return db; }
} GC;
struct CvDllDatabaseUtility { bool PerformDatabasePostProcessing(); } loader;
#include "database_postprocess_fixture.h"

void Exec(Database::Connection& db, const char* sql) { CHECK(db.Execute(sql)); }
std::string Rows(Database::Connection& db, const char* sql) {
    Database::Results rows;
    CHECK(db.Execute(rows, sql));
    std::string result;
    while (rows.Step()) {
        for (int i = 0; i != rows.ColumnCount(); ++i) {
            const char* value = rows.GetText(i);
            CHECK(value != nullptr);
            result += std::to_string(std::strlen(value)); result += ':'; result += value; result += '|';
        }
        result += '\n';
    }
    CHECK(db.ErrorCode() == 101);
    return result;
}
std::string Snapshot(Database::Connection& db) {
    return Rows(db, "SELECT quote(Name),quote(Value) FROM Defines ORDER BY Name,Value")
        + Rows(db, "SELECT quote(Type),quote(ResourceUsage),quote(Happiness) FROM Resources ORDER BY Type");
}
int Scalar(Database::Connection& db, const char* sql) {
    Database::Results rows;
    CHECK(db.Execute(rows, sql) && rows.Step());
    return rows.GetInt(0);
}
void Schema(Database::Connection& db, bool deferred = false) {
    CHECK(db.Open(":memory:", Database::OPEN_READWRITE | Database::OPEN_CREATE)); GC.db = &db;
    if (deferred) {
        Exec(db, "PRAGMA foreign_keys=ON");
        Exec(db, "CREATE TABLE Allowed(Value INTEGER PRIMARY KEY)");
        Exec(db, "INSERT INTO Allowed VALUES(77),(-5),(42),(7)");
        Exec(db, "CREATE TABLE Defines(Name TEXT PRIMARY KEY,Value INTEGER REFERENCES Allowed(Value) DEFERRABLE INITIALLY DEFERRED)");
    } else Exec(db, "CREATE TABLE Defines(Name TEXT PRIMARY KEY,Value INTEGER)");
    Exec(db, "INSERT INTO Defines VALUES('BASE',77),('POST',-5),('MISSING',42)");
    Exec(db, "CREATE TABLE PostDefines(Name TEXT, [Key] TEXT, [Table] TEXT)");
    Exec(db, "INSERT INTO PostDefines VALUES('POST','UNIT_X','Units'),('MISSING','ABSENT','Units')");
    Exec(db, "CREATE TABLE Units(ID INTEGER PRIMARY KEY,Type TEXT)");
    Exec(db, "INSERT INTO Units VALUES(7,'UNIT_X')");
    Exec(db, "CREATE TABLE Resources(Type TEXT PRIMARY KEY,ResourceUsage INTEGER,Happiness INTEGER)");
    Exec(db, "INSERT INTO Resources VALUES('IRON',0,0),('GOLD',0,4),('BOTH',0,3),('BONUS',0,0)");
    Exec(db, "CREATE TABLE Unit_ResourceQuantityRequirements(ResourceType TEXT)");
    Exec(db, "INSERT INTO Unit_ResourceQuantityRequirements VALUES('IRON'),('BOTH')");
}
void NoTransaction(Database::Connection& db) { Exec(db, "BEGIN"); Exec(db, "ROLLBACK"); }

const char* Triggers[] = {
    "CREATE TEMP TRIGGER deny BEFORE INSERT ON Defines WHEN NEW.Name='POST' BEGIN SELECT RAISE(ABORT,'post'); END",
    "CREATE TEMP TRIGGER deny BEFORE UPDATE ON Resources WHEN NEW.ResourceUsage=1 BEGIN SELECT RAISE(ABORT,'strategic'); END",
    "CREATE TEMP TRIGGER deny BEFORE UPDATE ON Resources WHEN NEW.ResourceUsage=2 BEGIN SELECT RAISE(ABORT,'luxury'); END",
    "CREATE TEMP TRIGGER deny BEFORE INSERT ON Defines WHEN NEW.Name='MAX_TEAMS' BEGIN SELECT RAISE(ABORT,'constant'); END"
};
void Normal() {
    Database::Connection db; Schema(db);
    CHECK(loader.PerformDatabasePostProcessing());
    CHECK(Scalar(db, "SELECT Value FROM Defines WHERE Name='POST'") == 7);
    CHECK(Scalar(db, "SELECT Value FROM Defines WHERE Name='MISSING'") == 42);
    CHECK(Scalar(db, "SELECT ResourceUsage FROM Resources WHERE Type='IRON'") == 1);
    CHECK(Scalar(db, "SELECT ResourceUsage FROM Resources WHERE Type='GOLD'") == 2);
    CHECK(Scalar(db, "SELECT ResourceUsage FROM Resources WHERE Type='BOTH'") == 2);
    CHECK(Scalar(db, "SELECT ResourceUsage FROM Resources WHERE Type='BONUS'") == 0);
    const std::string expected = Snapshot(db);
    CHECK(loader.PerformDatabasePostProcessing()); CHECK(Snapshot(db) == expected);
    NoTransaction(db);
    std::puts("NORMAL_BEGIN"); std::printf("%s", expected.c_str()); std::puts("NORMAL_END");
}

#ifndef DATABASE_POSTPROCESS_ORIGINAL
struct ThrowLogger final : Database::IDatabaseLogger {
    bool armed = true;
    void Log(const char*, LogTypes type) override {
        if (type == TYPE_ERROR && armed) { armed = false; throw std::runtime_error("logger failure"); }
    }
};
void Advanced() {
    for (unsigned mode = 0; mode != 5; ++mode) {
        Database::Connection db; Schema(db);
        if (mode == 0) Exec(db, "UPDATE PostDefines SET [Table]='MISSING_TABLE' WHERE Name='POST'");
        if (mode == 1) Exec(db, "UPDATE PostDefines SET Name=NULL WHERE Name='POST'");
        if (mode == 2) Exec(db, "UPDATE PostDefines SET [Key]=NULL WHERE Name='POST'");
        if (mode == 3) Exec(db, "UPDATE PostDefines SET [Table]='' WHERE Name='POST'");
        if (mode == 4) { Exec(db, "DROP TABLE PostDefines"); Exec(db, "CREATE TABLE PostDefines(Wrong TEXT)"); }
        const std::string before = Snapshot(db);
        CHECK(!loader.PerformDatabasePostProcessing()); CHECK(Snapshot(db) == before); NoTransaction(db);
    }
    {
        Database::Connection db; Schema(db);
        Exec(db, "DELETE FROM PostDefines");
        Exec(db, "CREATE TABLE \"odd\"\"table\"(Type TEXT)");
        const std::string key = std::string(2048, 'x') + "'한글";
        Database::Results add;
        CHECK(db.Execute(add, "INSERT INTO \"odd\"\"table\"(rowid,Type) VALUES(123,?)") && add.Bind(1, key.c_str()) && add.Execute());
        add.Release();
        CHECK(db.Execute(add, "INSERT INTO PostDefines VALUES('QUOTED',?,'odd\"table')") && add.Bind(1, key.c_str()) && add.Execute());
        add.Release();
        CHECK(loader.PerformDatabasePostProcessing());
        CHECK(Scalar(db, "SELECT Value FROM Defines WHERE Name='QUOTED'") == 123); NoTransaction(db);
    }
    {
        Database::Connection db; Schema(db);
        Exec(db, "DROP TABLE Unit_ResourceQuantityRequirements");
        const std::string before = Snapshot(db);
        db.SetLogger(new ThrowLogger);
        bool caught = false;
        try { loader.PerformDatabasePostProcessing(); }
        catch (const std::runtime_error& failure) { caught = std::strcmp(failure.what(), "logger failure") == 0; }
        db.SetLogger(nullptr);
        CHECK(caught); CHECK(Snapshot(db) == before); NoTransaction(db);
    }
    {
        Database::Connection db; Schema(db, true);
        const std::string before = Snapshot(db);
        CHECK(!loader.PerformDatabasePostProcessing()); CHECK(Snapshot(db) == before); NoTransaction(db);
    }
    GC.db = nullptr; CHECK(!loader.PerformDatabasePostProcessing());
    Database::Connection closed; GC.db = &closed; CHECK(!loader.PerformDatabasePostProcessing());
    GC.db = nullptr;
    std::puts("EDGE|5_bad_metadata_or_schema|quoted_long_utf8_key|logger_exception_rollback|deferred_commit_failure|null_closed");
}
#endif

int main(int argc, char** argv) {
#ifndef DATABASE_POSTPROCESS_ORIGINAL
    if (argc == 2 && std::strcmp(argv[1], "--rollback-failure") == 0) {
        {
            Database::Connection db; Schema(db);
            const std::string original = Snapshot(db);
            Exec(db, "CREATE TEMP TRIGGER abort_transaction BEFORE INSERT ON Defines WHEN NEW.Name='POST' BEGIN SELECT RAISE(ROLLBACK,'whole transaction canceled'); END");
            Exec(db, "SAVEPOINT outer_owner");
            Exec(db, "UPDATE Defines SET Value=88 WHERE Name='BASE'");
            bool caught = false;
            try { loader.PerformDatabasePostProcessing(); }
            catch (const std::runtime_error& failure) {
                caught = std::strstr(failure.what(), "postprocessing rollback failed") != nullptr;
            }
            CHECK(caught); CHECK(Snapshot(db) == original);
            CHECK(Scalar(db, "SELECT Value FROM Defines WHERE Name='BASE'") == 77);
            NoTransaction(db);
            GC.db = nullptr;
        }
        std::puts("ROLLBACK_FAILURE|explicit_exception|outer_transaction_canceled_by_sqlite|connection_closed");
        std::puts("SCOPE|exact_sdk_postprocessing|same_real_x64_database|no_gamecore_loaded");
        std::printf("PASS|%u\n", checks);
        return 0;
    }
#endif
    if (argc == 2) {
        Database::Connection db;
        CHECK(db.Open(argv[1], Database::OPEN_READWRITE)); GC.db = &db;
        const bool ok = loader.PerformDatabasePostProcessing();
        std::printf("CORPUS_RESULT|%u\n", ok ? 1u : 0u);
        std::printf("%s", Snapshot(db).c_str());
        CHECK(ok); NoTransaction(db);
        GC.db = nullptr;
        return 0;
    }
    Normal();
    unsigned cases = 0;
    for (const char* trigger : Triggers) for (unsigned nested = 0; nested != 2; ++nested) {
        Database::Connection db; Schema(db); Exec(db, trigger);
        if (nested) { Exec(db, "SAVEPOINT outer_owner"); Exec(db, "UPDATE Defines SET Value=88 WHERE Name='BASE'"); }
        const std::string before = Snapshot(db);
        const bool ok = loader.PerformDatabasePostProcessing();
#ifdef DATABASE_POSTPROCESS_ORIGINAL
        CHECK(ok); CHECK(Snapshot(db) != before);
#else
        CHECK(!ok); CHECK(Snapshot(db) == before);
#endif
        if (nested) {
            CHECK(Scalar(db, "SELECT Value FROM Defines WHERE Name='BASE'") == 88);
            Exec(db, "ROLLBACK TO outer_owner"); Exec(db, "RELEASE outer_owner");
            CHECK(Scalar(db, "SELECT Value FROM Defines WHERE Name='BASE'") == 77);
        }
        NoTransaction(db);
#ifndef DATABASE_POSTPROCESS_ORIGINAL
        Exec(db, "DROP TRIGGER deny"); CHECK(loader.PerformDatabasePostProcessing()); NoTransaction(db);
#endif
        ++cases;
    }
#ifdef DATABASE_POSTPROCESS_ORIGINAL
    std::printf("ORIGINAL_DEFECT|%u_failures_reported_success|partial_writes\n", cases);
#else
    Advanced();
    std::printf("CANDIDATE_ATOMIC|%u_trigger_failures_rolled_back|outer_transaction_preserved|retry_success\n", cases);
#endif
    GC.db = nullptr;
    std::puts("SCOPE|exact_sdk_postprocessing|same_real_x64_database|no_gamecore_loaded");
    std::printf("PASS|%u\n", checks);
    return 0;
}
