#include "SdkDatabaseIncludes.h"
#include <atomic>
#include <thread>
#include <new>
static std::atomic<unsigned long> checks(0);
static void require(bool value) { ++checks;if(!value)throw std::runtime_error("database hardening check"); }
struct Logger:Database::IDatabaseLogger {
    std::vector<std::string> messages;
    void Log(const char* message,LogTypes) { messages.push_back(message?message:"<null>"); }
};
static void lifetime() {
    SYSTEM_INFO info;GetSystemInfo(&info);void* page=VirtualAlloc(NULL,info.dwPageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);require(page!=NULL);
    Database::Connection* owner=::new(page) Database::Connection(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE);
    Database::Results* first=new Database::Results;require(owner->Execute(*first,"SELECT 7 AS Value"));require(first->Step());
    Database::Results* copy=new Database::Results(*first);require(copy->Step());
    Database::ResultsCache* cache=new Database::ResultsCache(*owner);Database::Results* cached=cache->Prepare("a","SELECT 9");require(cached!=NULL);require(cached->Step());
    require(owner->StatementCount()==3);owner->~Connection();DWORD previous=0;require(VirtualProtect(page,info.dwPageSize,PAGE_NOACCESS,&previous)!=0);
    for(Database::Results* r:{first,copy,cached}) {
        require(!r->Step());require(!r->Execute());require(!r->TryExecute());require(!r->Reset());require(!r->TryReset());
        require(!r->Bind(1,2));require(!r->BindNULL(1));require(r->ColumnCount()==0);require(r->GetText(0)==NULL);require(r->GetInt(0)==0);
    }
    delete first;delete copy;delete cache;require(VirtualFree(page,0,MEM_RELEASE)!=0);
    Database::Connection db(":memory:",6);Database::Results r;require(db.Execute(r,"SELECT 8"));db.Close();db.Close();require(!r.Step());require(db.Open(":memory:",6));require(db.Execute(r,"SELECT 9"));require(r.Step());require(r.GetInt(0)==9);
    printf("LIFETIME|owner_page_inaccessible|3_detached_results|reopen_pass\n");
}
static void boundaries() {
    Database::Connection db(":memory:",6);Logger* logger=new Logger;db.SetLogger(logger);Database::Results r;
    require(db.Execute("CREATE TABLE \"odd \"\" table\"(\"key \"\" name\" TEXT, R REAL)"));
    require(db.Execute("INSERT INTO \"odd \"\" table\" VALUES('a''; DROP TABLE x; --',3.25)"));
    require(db.SelectAt(r,"odd \" table","key \" name","a'; DROP TABLE x; --"));require(r.Step());require(r.GetDouble(1)==3.25);r.Release();
    require(db.SelectAt(r,"odd \" table","R",3.25));require(r.Step());require(r.GetDouble(1)==3.25);require(!r.Step());r.Release();
    Database::SingleResult single;require(db.SelectAt(single,"odd \" table","R",3.25));require(single.GetDouble(1)==3.25);
    require(db.Count("odd \" table")==1);db.ClearCountCache();
    require(db.Execute(r,"SELECT ?1"));require(!r.Bind(1,reinterpret_cast<const wchar_t*>(1),INT_MAX,true));require(r.BindNULL(1));require(r.Step());require(r.GetText(0)==NULL);r.Release();
    SYSTEM_INFO info;GetSystemInfo(&info);char* region=static_cast<char*>(VirtualAlloc(NULL,info.dwPageSize*2,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));require(region!=NULL);
    DWORD previous=0;require(VirtualProtect(region+info.dwPageSize,info.dwPageSize,PAGE_NOACCESS,&previous)!=0);
    char* sql=region+info.dwPageSize-7;memcpy(sql,"BAD SQL",7);require(!db.Execute(r,sql,7));require(!logger->messages.empty());require(logger->messages.back()=="In Query - BAD SQL");
    require(VirtualFree(region,0,MEM_RELEASE)!=0);require(db.Execute(r,"SELECT 1"));require(r.Step());
    printf("BOUNDARIES|quoted_identifiers|bound_double|wide_length_overflow|bounded_error_sql\n");
}
static void foreignKeys() {
    Database::Connection db(":memory:",6);
    require(db.ExecuteMultiple("CREATE TABLE P(A INT,B INT,PRIMARY KEY(A,B));INSERT INTO P VALUES(1,2);INSERT INTO P VALUES(3,4);CREATE TABLE C(A INT,B INT,FOREIGN KEY(A,B) REFERENCES P(A,B));INSERT INTO C VALUES(1,2);"));
    require(db.ValidateFKConstraints());require(db.Execute("INSERT INTO C VALUES(1,4)"));require(!db.ValidateFKConstraints());
    require(db.Execute("DELETE FROM C WHERE B=4"));require(db.Execute("INSERT INTO C VALUES(NULL,99)"));require(db.ValidateFKConstraints());
    require(db.ExecuteMultiple("CREATE TABLE I(A INT,B INT,FOREIGN KEY(A,B) REFERENCES P);INSERT INTO I VALUES(3,4);"));require(db.ValidateFKConstraints());
    require(db.Execute("INSERT INTO I VALUES(3,2)"));require(!db.ValidateFKConstraints());
    printf("FOREIGN_KEYS|composite_pair|implicit_parent_key|nullable_pair\n");
}
static void concurrent() {
    const unsigned workers=8,rows=512;std::atomic<unsigned> ready(0),failures(0);HANDLE start=CreateEventW(NULL,TRUE,FALSE,NULL);require(start!=NULL);
    std::vector<std::thread> threads;
    for(unsigned worker=0;worker<workers;++worker)threads.emplace_back([&,worker] {
        ++ready;WaitForSingleObject(start,INFINITE);
        try {
            for(unsigned round=0;round<8;++round) {
                Database::Connection db(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE|Database::OPEN_FULLMUTEX);
                require(db.Execute("CREATE TABLE T(ID INT PRIMARY KEY,V INT)"));Database::Results insert;require(db.Execute(insert,"INSERT INTO T VALUES(?1,?2)"));db.BeginTransaction();
                __int64 sum=0;for(unsigned i=0;i<rows;++i) { const int value=static_cast<int>(worker*10000+round*1000+i);sum+=value;
                    require(insert.Bind(1,static_cast<int>(i)));require(insert.Bind(2,value));require(insert.Execute());require(insert.Reset()); }
                db.EndTransaction();insert.Release();Database::SingleResult aggregate;
                require(db.Execute(aggregate,"SELECT COUNT(*),SUM(V) FROM T"));require(aggregate.GetInt(0)==static_cast<int>(rows));require(aggregate.GetInt64(1)==sum);
                db.Close();require(!aggregate.Step());
            }
        }catch(...) { ++failures; }
    });
    while(ready.load()!=workers)SwitchToThread();require(SetEvent(start)!=0);for(auto& thread:threads)thread.join();CloseHandle(start);require(failures.load()==0);
    printf("CONCURRENCY|%u|%u|%u|fresh_sqlite_initialization\n",workers,workers*8,workers*8*rows);
}
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try { require(argc==2);if(!strcmp(argv[1],"hardening")) { lifetime();boundaries();foreignKeys(); }else if(!strcmp(argv[1],"concurrency"))concurrent();else require(false);
        printf("PASS|%lu\n",checks.load());return 0; }
    catch(const std::exception& e) { fprintf(stderr,"FAILED|%lu|%s\n",checks.load(),e.what());return 1; }
}
