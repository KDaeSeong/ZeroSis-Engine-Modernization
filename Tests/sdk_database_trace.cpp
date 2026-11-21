#include "SdkDatabaseIncludes.h"
static unsigned int checks=0,loggerDestroyed=0;
static void require(bool value) { ++checks;if(!value) { fprintf(stderr,"FAILED|%u\n",checks);throw std::runtime_error("database check"); } }
static void text(const char* name,const char* value) {
    if(!value) { printf("%s|NULL\n",name);return; }
    const size_t size=strlen(value);printf("%s|%u|",name,static_cast<unsigned int>(size));
    for(size_t i=0;i<size;++i)printf("%02x",static_cast<unsigned char>(value[i]));printf("\n");
}
struct Logger: Database::IDatabaseLogger {
    unsigned int messages,warnings,errors;
    Logger():messages(0),warnings(0),errors(0) {}
    ~Logger() { ++loggerDestroyed; }
    void Log(const char* message,LogTypes type) {
        if(type==TYPE_MESSAGE)++messages;else if(type==TYPE_WARNING)++warnings;else if(type==TYPE_ERROR)++errors;
        printf("LOGTYPE|%d\n",static_cast<int>(type));text("LOG",message);
    }
};
static void dump(Database::Results& result) {
    printf("COLUMNS|%d\n",result.ColumnCount());
    for(int i=0;i<result.ColumnCount();++i) {
        text("COLUMN",result.ColumnName(i));text("DECLTYPE",result.ColumnTypeName(i));
        const int type=static_cast<int>(result.ColumnType(i));const bool boolean=result.GetBool(i);
        const __int64 integer=result.GetInt64(i);const double number=result.GetDouble(i);
        printf("VALUE|%d|%d|%I64d|%.17g\n",type,boolean,integer,number);
        text("TEXT",result.GetText(i));
    }
}
static void query(Database::Connection& db,const char* sql) {
    Database::Results result;const bool prepared=db.Execute(result,sql);printf("PREPARED|%d|%d\n",prepared,db.ErrorCode());
    if(prepared) { while(result.Step())dump(result);printf("DONE|%d\n",db.ErrorCode()); }
}
static void probe() {
    Database::Connection db;Logger* logger=new Logger;db.SetLogger(logger);
    printf("OPEN_DEFAULT|%d\n",db.Open(":memory:"));
    const bool opened=db.Open(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);printf("OPEN|%d\n",opened);require(opened);
    query(db,"SELECT sqlite_version() AS version,sqlite_source_id() AS source");
    query(db,"PRAGMA compile_options");
    printf("CREATE|%d\n",db.Execute("CREATE TABLE T(ID INTEGER PRIMARY KEY,Name TEXT,Flag BOOLEAN,Amount REAL,Maybe INTEGER)"));
    printf("INSERT|%d\n",db.Execute("INSERT INTO T VALUES(7,'Alpha',2,1.25,NULL)"));
    Database::Results rows;printf("COLUMNS_DEFAULT|%d\n",rows.SingleQuery());text("PROJECTION",rows.GetColumns());
    const bool selected=db.SelectAll(rows,"T");printf("SELECT|%d|%d\n",selected,rows.ColumnCount());
    printf("STEP|%d\n",rows.Step());dump(rows);
    printf("LOOKUP|%d|%d|%d|%d|%d\n",rows.ColumnPosition("ID"),rows.ColumnPosition("id"),rows.ColumnPosition("absent"),rows.HasColumn("ID"),rows.HasColumn("id"));
    text("MISSING_TEXT",rows.GetText("absent"));printf("MISSING_VALUES|%d|%d|%.9g\n",rows.GetInt("absent"),rows.GetBool("absent"),rows.GetFloat("absent"));
    const bool ended=rows.Step();printf("STEP_END|%d|%d\n",ended,db.ErrorCode());printf("STEP_AGAIN|%d\n",rows.Step());
    printf("RESET|%d\n",rows.Reset());const bool stepped=rows.Step();printf("STEP_RESET|%d|%d\n",stepped,rows.GetInt(0));rows.Release();
    Database::SingleResult one;printf("SINGLE|%d|%d\n",one.SingleQuery(),db.SelectAt(one,"T",7));dump(one);
    printf("SINGLE_STEP|%d\n",one.Step());one.Release();
    printf("SINGLE_MISSING|%d\n",db.SelectAt(one,"T",99));printf("SINGLE_MISSING_COLUMNS|%d\n",one.ColumnCount());
    printf("COUNT|%d\n",db.Count("T"));require(db.Execute("INSERT INTO T VALUES(8,'Beta',0,2.5,9)"));
    printf("COUNT_CACHED|%d\n",db.Count("T"));printf("COUNT_REFRESH|%d\n",db.Count("T",false));printf("COUNT_AFTER_REFRESH|%d\n",db.Count("T"));
    db.ClearCountCache();printf("COUNT_CLEAR|%d\n",db.Count("T"));printf("COUNT_MISSING|%d\n",db.Count("missing"));
    Database::Results prepared;require(db.Execute(prepared,"SELECT ?1 AS I,?2 AS S,?3 AS W,?4 AS Z"));
    printf("BIND|%d|%d|%d|%d\n",prepared.Bind(1,123),prepared.Bind(2,"ABCD",2,true),prepared.Bind(3,L"WXYZ",2,true),prepared.BindNULL(4));
    printf("BOUND_STEP|%d\n",prepared.Step());dump(prepared);printf("BOUND_RESET|%d\n",prepared.Reset());
    printf("BOUND_CLEARED|%d\n",prepared.Step());dump(prepared);
    printf("LOG_COUNTS|%u|%u|%u\n",logger->messages,logger->warnings,logger->errors);
}
static void semantics() {
    Database::Connection db(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);Logger* logger=new Logger;db.SetLogger(logger);
    const char* setup="CREATE TABLE Parent(ID INTEGER PRIMARY KEY); CREATE TABLE Child(ID INTEGER,ParentID INTEGER REFERENCES Parent(ID)); INSERT INTO Parent VALUES(1); INSERT INTO Child VALUES(1,1);";
    printf("MULTIPLE|%d\n",db.ExecuteMultiple(setup));
    printf("FK_VALID|%d\n",db.ValidateFKConstraints());require(db.Execute("INSERT INTO Child VALUES(2,99)"));printf("FK_INVALID|%d\n",db.ValidateFKConstraints());
    require(db.Execute("DELETE FROM Child WHERE ID=2"));require(db.Execute("INSERT INTO Child VALUES(3,NULL)"));
    printf("FK_NULL_ALLOWED|%d\n",db.ValidateFKConstraints(true));printf("FK_NULL_REJECTED|%d\n",db.ValidateFKConstraints(false));
    db.BeginTransaction();require(db.Execute("INSERT INTO Parent VALUES(2)"));db.RollbackTransaction();printf("ROLLBACK|%d\n",db.Count("Parent",false));
    db.BeginDeferredTransaction();require(db.Execute("INSERT INTO Parent VALUES(3)"));db.EndTransaction();printf("COMMIT|%d\n",db.Count("Parent",false));
    printf("SAVEPOINT|%d\n",db.SetSavePoint("save_a"));require(db.Execute("INSERT INTO Parent VALUES(4)"));
    printf("ROLLBACK_SAVEPOINT|%d\n",db.RollbackToSavePoint("save_a"));printf("AFTER_SAVEPOINT|%d\n",db.Count("Parent",false));db.CommitTransaction();
    Database::Results rows("ID");printf("SELECTWHERE|%d\n",db.SelectWhere(rows,"Parent","ID >= 1 ORDER BY ID"));while(rows.Step())dump(rows);
    printf("SELECTINT|%d\n",db.SelectAt(rows,"Parent","ID",3));while(rows.Step())dump(rows);
    printf("SELECTTEXT|%d\n",db.SelectAt(rows,"Parent","ID","1"));while(rows.Step())dump(rows);
    rows.Release();printf("INVALID_SQL|%d\n",db.Execute("not a sql statement"));printf("ERROR|%d\n",db.ErrorCode());text("ERROR_TEXT",db.ErrorMessage());
    Database::Results insert;require(db.Execute(insert,"INSERT INTO Parent VALUES(?1)"));
    require(insert.Bind(1,1));const bool tried=insert.TryExecute();printf("CONSTRAINT|%d|%d\n",tried,db.ErrorCode());printf("TRY_RESET|%d\n",insert.TryReset());
    require(insert.Bind(1,1));const bool executed=insert.Execute();printf("CONSTRAINT_REPORT|%d|%d\n",executed,db.ErrorCode());printf("RESET_ERROR|%d\n",insert.Reset());
    require(insert.Bind(1,5));printf("EXECUTE_INSERT|%d\n",insert.Execute());printf("CHANGES|%d\n",db.TotalChanges());
    insert.Release();printf("STATEMENTS|%d\n",db.StatementCount());
    Database::ResultsCache cache(db);Database::Results* cached=cache.Prepare("p","SELECT ID FROM Parent ORDER BY ID");require(cached!=NULL);
    printf("CACHE_SAME|%d\n",cached==cache.Get("p"));printf("CACHE_MISSING|%d\n",cache.Get("missing")==NULL);
    while(cached->Step())printf("CACHE_ROW|%d\n",cached->GetInt(0));cache.Clear("p");printf("CACHE_CLEARED|%d\n",cache.Get("p")==NULL);
}
static void doubleSelect() {
    Database::Connection db(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);
    require(db.Execute("CREATE TABLE T(ID INTEGER PRIMARY KEY)"));require(db.Execute("INSERT INTO T VALUES(3)"));
    Database::Results rows;printf("BEFORE_DOUBLE_SELECT\n");
    printf("SELECTREAL|%d\n",db.SelectAt(rows,"T","ID",3.0));while(rows.Step())dump(rows);
}
static void types() {
    Database::Connection db(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);
    query(db,"SELECT 0 AS A,1 AS B,-1 AS C,4294967296 AS D,1.0 AS E,0.5 AS F,NULL AS G,'' AS H,'true' AS I,'TRUE' AS J,'turtle' AS K,'false' AS L,'1' AS M,x'410042' AS N");
    Database::Results r;require(db.Execute(r,"SELECT 17 AS X,18 AS X,19 AS x"));require(r.Step());
    printf("DUPLICATE_COLUMNS|%d|%d\n",r.ColumnPosition("X"),r.ColumnPosition("x"));
    int value=77;r.GetValue("missing",value);printf("MISSING_GETVALUE|%d\n",value);
    r.Release();printf("RELEASED|%d|%d|%d|%d\n",r.ColumnCount(),r.ColumnPosition("X"),r.Reset(),r.Step());
    require(db.Execute(r,"SELECT 3 AS Other"));printf("NEW_COLUMNS|%d|%d\n",r.ColumnPosition("X"),r.ColumnPosition("Other"));
}
static void contracts() {
    Database::Connection db(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);Logger* logger=new Logger;db.SetLogger(logger);
    require(db.Execute("CREATE TABLE T(ID INTEGER PRIMARY KEY, B boolean, U BOOLEAN)"));
    require(db.Execute("INSERT INTO T VALUES(1,1,1)"));query(db,"SELECT * FROM T");
    Database::Results r;require(db.Execute(r,"SELECT 1 AS A"));printf("EXECUTE_ROW|%d\n",r.Execute());r.Release();
    require(db.Execute(r,"SELECT 1 AS A"));printf("TRY_EXECUTE_ROW|%d\n",r.TryExecute());r.Release();
    printf("EMPTY_EXECUTE|%d\n",db.Execute(""));printf("EMPTY_PREPARE|%d\n",db.Execute(r,""));
    printf("MULTI_SPACE|%d\n",db.ExecuteMultiple("  ; -- comment\n"));
    require(db.Execute(r,"SELECT ?1 AS Value"));printf("BIND_BAD|%d|%d\n",r.Bind(0,5),r.Bind(2,5));
    char borrowed[]="abc";require(r.Bind(1,borrowed,false));borrowed[0]='z';require(r.Step());text("BORROWED",r.GetText(0));require(r.Reset());
    char copied[]="def";require(r.Bind(1,copied,true));copied[0]='z';require(r.Step());text("COPIED",r.GetText(0));require(r.Reset());
    const wchar_t wide[]={0xd55c,0xae00,0xd83c,0xdf00,0};require(r.Bind(1,wide));require(r.Step());text("UTF8",r.GetText(0));
    const wchar_t* roundtrip=r.GetText16(0);printf("UTF16|%04x|%04x|%04x|%04x\n",roundtrip[0],roundtrip[1],roundtrip[2],roundtrip[3]);
    Database::Results copy(r);printf("COPY_COLUMNS|%d|%d\n",copy.ColumnCount(),copy.ColumnPosition("Value"));require(copy.Step());dump(copy);copy.Release();
    require(r.Reset());require(r.Bind(1,81));require(r.Step());require(r.GetInt(0)==81);r.Release();
    char projection[]="ID";r.SetColumns(projection);projection[0]='X';text("OWNED_PROJECTION",r.GetColumns());
    Database::Results projected(r);r.Release();text("COPIED_PROJECTION",projected.GetColumns());
    const char bounded[]={'S','E','L','E','C','T',' ','4','2'};
    require(db.Execute(r,bounded,sizeof(bounded)));require(r.Step());printf("BOUNDED_SQL|%d\n",r.GetInt(0));r.Release();
    require(db.ExecuteMultiple("INSERT INTO T VALUES(2,0,0);INSERT INTO T VALUES(3,1,1);"));
    printf("CACHED_COUNT_INITIAL|%d\n",db.Count("T"));require(db.Execute("UPDATE T SET B=0 WHERE ID=-1"));printf("CACHED_ZERO_CHANGE|%d\n",db.Count("T"));
    db.ClearCountCache();printf("COUNT_STATEMENTS|%d\n",db.StatementCount());
    db.BeginTransaction();require(db.Execute("INSERT INTO T VALUES(4,0,0)"));db.BeginTransaction();require(db.Execute("INSERT INTO T VALUES(5,0,0)"));db.EndTransaction();db.EndTransaction();
    printf("NESTED|%d\n",db.Count("T",false));
    Database::ResultsCache cache(db);require(cache.Prepare("same","SELECT 11")!=NULL);Database::Results* second=cache.Prepare("same","SELECT 22");require(second!=NULL);require(second->Step());printf("CACHE_REPREPARE|%d\n",second->GetInt(0));
    printf("CACHE_BAD_PREPARE|%d\n",cache.Prepare("same","bad sql")==NULL);
    Database::Results* retained=cache.Get("same");printf("CACHE_AFTER_ERROR|%d\n",retained!=NULL);if(retained) { printf("CACHE_RESET|%d\n",retained->Reset());if(retained->Step())printf("CACHE_RETAINED_VALUE|%d\n",retained->GetInt(0)); }
}
static void bulk() {
    Database::Connection db(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);
    require(db.Execute("CREATE TABLE T(ID INTEGER PRIMARY KEY,I INTEGER,R REAL,S TEXT,W TEXT,Z INTEGER)"));
    Database::Results insert;require(db.Execute(insert,"INSERT INTO T VALUES(?1,?2,?3,?4,?5,?6)"));db.BeginTransaction();
    for(int i=0;i<1024;++i) {
        const __int64 integer=static_cast<__int64>(i-512)*4294967296LL+i;char string[64];sprintf(string,"row_%04d_'_\xec\x84\xb8\xea\xb3\x84",i);
        const wchar_t wide[]={0xc138,0xacc4,static_cast<wchar_t>(0xac00+i),0};
        require(insert.Bind(1,i));require(insert.Bind(2,integer));require(insert.Bind(3,(i-512)*0.125));require(insert.Bind(4,string));require(insert.Bind(5,wide));
        require(i%3?insert.Bind(6,i):insert.BindNULL(6));require(insert.Execute());require(insert.Reset());
    }
    db.EndTransaction();insert.Release();require(db.Count("T")==1024);db.ClearCountCache();
    Database::Results rows;require(db.Execute(rows,"SELECT * FROM T ORDER BY ID"));int n=0;
    while(rows.Step()) { require(rows.GetInt(0)==n);require(rows.GetInt64(1)==static_cast<__int64>(n-512)*4294967296LL+n);require(rows.GetDouble(2)==(n-512)*0.125);dump(rows);++n; }
    require(n==1024);rows.Release();printf("BULK_STATEMENTS|%d\n",db.StatementCount());
}
static void fileDatabase(const char* path,bool write) {
    Database::Connection db;require(db.Open(path,write?6:Database::OPEN_READONLY));
    if(write) {
        require(db.Execute("CREATE TABLE T(ID INTEGER PRIMARY KEY,I INTEGER,S TEXT)"));require(db.Execute("PRAGMA user_version=17"));
        Database::Results insert;require(db.Execute(insert,"INSERT INTO T VALUES(?1,?2,?3)"));db.BeginTransaction();
        for(int i=0;i<257;++i) { char value[32];sprintf(value,"file_row_%d",i);require(insert.Bind(1,i));require(insert.Bind(2,static_cast<__int64>(i-128)*8589934592LL));require(insert.Bind(3,value));require(insert.Execute());require(insert.Reset()); }
        db.EndTransaction();
    }
    Database::SingleResult integrity;require(db.Execute(integrity,"PRAGMA integrity_check"));require(!strcmp(integrity.GetText(0),"ok"));integrity.Release();
    require(db.Execute(integrity,"PRAGMA user_version"));require(integrity.GetInt(0)==17);integrity.Release();
    Database::Results rows;require(db.Execute(rows,"SELECT ID,I,S FROM T ORDER BY ID"));int n=0;
    while(rows.Step()) { require(rows.GetInt(0)==n);require(rows.GetInt64(1)==static_cast<__int64>(n-128)*8589934592LL);dump(rows);++n; }
    require(n==257);rows.Release();require(db.StatementCount()==0);printf("FILE_INTEGRITY|257|17|ok\n");
}
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try { require(argc>=2);if(!strcmp(argv[1],"writefile")||!strcmp(argv[1],"readfile")) { require(argc==3);fileDatabase(argv[2],!strcmp(argv[1],"writefile")); }
        else { require(argc==2);if(!strcmp(argv[1],"probe"))probe();else if(!strcmp(argv[1],"semantics"))semantics();else if(!strcmp(argv[1],"types"))types();else if(!strcmp(argv[1],"double"))doubleSelect();else if(!strcmp(argv[1],"contracts"))contracts();else if(!strcmp(argv[1],"bulk"))bulk();else require(false); }
        printf("PASS|%u|%u\n",checks,loggerDestroyed);return 0; }
    catch(const std::exception& error) { fprintf(stderr,"EXCEPTION|%s\n",error.what());return 1; }
}
