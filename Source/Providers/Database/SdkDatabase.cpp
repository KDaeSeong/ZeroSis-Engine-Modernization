#define CvGameDatabaseAPI __declspec(dllexport)
#include "SdkDatabaseIncludes.h"
#include "sqlite3.h"
#include "SdkDatabaseLifetime.h"
#include <mutex>
#include <cstdarg>
#include <map>
#include <list>

namespace {
struct SqlText {
    char* value;
    explicit SqlText(char* p):value(p) { if(!p)throw std::bad_alloc(); }
    ~SqlText() { sqlite3_free(value); }
private: SqlText(const SqlText&);SqlText& operator=(const SqlText&);
};
std::string format(const char* pattern,...) {
    va_list args;va_start(args,pattern);char* p=sqlite3_vmprintf(pattern,args);va_end(args);
    SqlText text(p);return std::string(text.value);
}
std::string identifier(const char* name) {
    if(!name)throw std::invalid_argument("null database identifier");
    return format("\"%w\"",name);
}
}

namespace Database {
namespace {
struct LiveCommands { std::mutex mutex;std::map<const Connection*,std::list<Command*> > owners; };
LiveCommands& liveCommands() { static LiveCommands live;return live; }
}
void TrackCommand(const Connection* owner,Command* command) {
    LiveCommands& live=liveCommands();std::lock_guard<std::mutex> lock(live.mutex);
    const auto inserted=live.owners.emplace(owner,std::list<Command*>());
    try {
        if(std::find(inserted.first->second.begin(),inserted.first->second.end(),command)!=inserted.first->second.end())throw std::logic_error("Duplicate database command registration");
        inserted.first->second.push_back(command);
    }
    catch(...) { if(inserted.second)live.owners.erase(inserted.first);throw; }
}
void UntrackCommand(const Connection* owner,Command* command) {
    LiveCommands& live=liveCommands();std::lock_guard<std::mutex> lock(live.mutex);
    const auto found=live.owners.find(owner);if(found!=live.owners.end()) { found->second.remove(command);if(found->second.empty())live.owners.erase(found); }
}
void SwapCommands(Command& left,Command& right) {
    LiveCommands& live=liveCommands();std::lock_guard<std::mutex> lock(live.mutex);
    std::list<Command*>::iterator leftNode,rightNode;
    if(left.stmt) {
        const auto owner=live.owners.find(left.connection);if(owner==live.owners.end())throw std::logic_error("Left command owner missing");
        leftNode=std::find(owner->second.begin(),owner->second.end(),&left);if(leftNode==owner->second.end())throw std::logic_error("Left command missing");
    }
    if(right.stmt) {
        const auto owner=live.owners.find(right.connection);if(owner==live.owners.end())throw std::logic_error("Right command owner missing");
        rightNode=std::find(owner->second.begin(),owner->second.end(),&right);if(rightNode==owner->second.end())throw std::logic_error("Right command missing");
    }
    // Updating existing list-node values cannot allocate. Both iterators are located
    // before either value changes, including two commands owned by the same connection.
    if(left.stmt)*leftNode=&right;if(right.stmt)*rightNode=&left;std::swap(left,right);
}
void DetachCommands(const Connection* owner) {
    LiveCommands& live=liveCommands();
    for(;;) {
        sqlite3_stmt* stmt=NULL;
        { std::lock_guard<std::mutex> lock(live.mutex);const auto found=live.owners.find(owner);if(found==live.owners.end())break;
          Command* command=*found->second.begin();stmt=command->stmt;command->stmt=NULL;command->connection=NULL;
          found->second.erase(found->second.begin());if(found->second.empty())live.owners.erase(found); }
        if(stmt)sqlite3_finalize(stmt);
    }
}
bool Connection::ms_bMemoryManagerInitialized=false;
char Connection::ms_pPageCacheBuffer[DB_PAGECACHE_SIZE*DB_NUM_PAGES]={};
char Connection::ms_pScratchBuffer[DB_PAGECACHE_SIZE*DB_NUM_THREADS*6]={};
void Connection::InitMemoryManagement() {
    static std::once_flag once;
    std::call_once(once,[] { if(sqlite3_initialize()!=SQLITE_OK)throw std::runtime_error("SQLite initialization failed"); });
}
Connection::Connection():m_db(NULL) { InitMemoryManagement(); }
Connection::Connection(const char* filename,int flags):m_db(NULL) { InitMemoryManagement();Open(filename,flags); }
Connection::~Connection() { try { Close(); }catch(...) {} }
bool Connection::Open(const char* filename,int flags) {
    Close();if(m_db)return false;
    sqlite3* candidate=NULL;const int rc=sqlite3_open_v2(filename,&candidate,flags,NULL);
    if(rc!=SQLITE_OK) { LogError(candidate?sqlite3_errmsg(candidate):NULL);if(candidate)sqlite3_close(candidate);return false; }
    m_db=candidate;return true;
}
void Connection::Close() {
    DetachCommands(this);ClearCountCache();if(m_db) { const int rc=sqlite3_close(m_db);if(rc==SQLITE_OK)m_db=NULL;else Report(rc); }
}
sqlite3* Connection::GetSQLite3() const { return m_db; }
bool Connection::Report(int rc) const { if(rc==SQLITE_OK)return true;LogError(ErrorMessage());return false; }
int Connection::ErrorCode() const { return m_db?sqlite3_errcode(m_db):-1; }
const char* Connection::ErrorMessage() const { return m_db?sqlite3_errmsg(m_db):NULL; }
void Connection::SetLogger(IDatabaseLogger* logger) { if(m_pkDatabaseLogger.get()!=logger)m_pkDatabaseLogger.reset(logger); }
void Connection::LogMessage(const char* text) const { if(m_pkDatabaseLogger.get())m_pkDatabaseLogger->Log(text,IDatabaseLogger::TYPE_MESSAGE); }
void Connection::LogWarning(const char* text) const { if(m_pkDatabaseLogger.get())m_pkDatabaseLogger->Log(text,IDatabaseLogger::TYPE_WARNING); }
void Connection::LogError(const char* text) const { if(m_pkDatabaseLogger.get())m_pkDatabaseLogger->Log(text,IDatabaseLogger::TYPE_ERROR); }
void Connection::BeginTransaction() { Execute("SAVEPOINT _;"); }
void Connection::EndTransaction() { Execute("RELEASE _;"); }
void Connection::RollbackTransaction() { Execute("ROLLBACK;"); }
void Connection::BeginDeferredTransaction() { Execute("BEGIN DEFERRED TRANSACTION"); }
void Connection::BeginImmediateTransaction() { Execute("BEGIN IMMEDIATE TRANSACTION"); }
void Connection::BeginExclusiveTransaction() { Execute("BEGIN EXCLUSIVE TRANSACTION"); }
void Connection::CommitTransaction() { Execute("COMMIT"); }
bool Connection::SetSavePoint(const char* name) { return Execute(("SAVEPOINT "+identifier(name)).c_str()); }
bool Connection::RollbackToSavePoint(const char* name) { return Execute(("ROLLBACK TO "+identifier(name)).c_str()); }
bool Connection::AcquireCommand(Command& command,const char* sql,int length) {
    if(!command.connection||command.stmt||!sql)return false;
    const bool prepared=command.connection->Report(sqlite3_prepare_v2(command.connection->m_db,sql,length,&command.stmt,NULL));
    if(prepared&&command.stmt)return true;
    const std::string attempted=length<0?std::string(sql):std::string(sql,static_cast<size_t>(length));
    command.connection->LogMessage(("In Query - "+attempted).c_str());return false;
}
void Connection::ReleaseCommand(Command& command) {
    const Connection* owner=command.connection;UntrackCommand(owner,&command);
    sqlite3_stmt* stmt=command.stmt;command.stmt=NULL;command.connection=NULL;
    if(stmt) { const int rc=sqlite3_finalize(stmt);if(owner)owner->Report(rc); }
}
bool Connection::Execute(Results& results,const char* sql,int length) const {
    Command command(this);if(!AcquireCommand(command,sql,length))return false;
    try { return results.SetCommand(command); } catch(...) { ReleaseCommand(command);throw; }
}
bool Connection::Execute(const char* sql,int length) const {
    if(!sql)return false;
    sqlite3_stmt* stmt=NULL;if(!Report(sqlite3_prepare_v2(m_db,sql,length,&stmt,NULL)))return false;if(!stmt)return false;
    int rc;do { rc=sqlite3_step(stmt); } while(rc==SQLITE_ROW||rc==SQLITE_OK);
    Report(sqlite3_finalize(stmt));if(rc!=SQLITE_DONE)LogError(ErrorMessage());return rc==SQLITE_DONE;
}
bool Connection::ExecuteMultiple(const char* sql,int length) const {
    if(!sql)return false;if(length<0) { const size_t n=strlen(sql);if(n>INT_MAX)return false;length=static_cast<int>(n); }
    while(length>0) {
        sqlite3_stmt* stmt=NULL;const char* tail=NULL;
        if(!Report(sqlite3_prepare_v2(m_db,sql,length,&stmt,&tail)))return false;
        if(!tail||tail<=sql) { if(stmt)sqlite3_finalize(stmt);return false; }
        length-=static_cast<int>(tail-sql);sql=tail;
        if(stmt) { int rc;do { rc=sqlite3_step(stmt); } while(rc==SQLITE_ROW||rc==SQLITE_OK);
            Report(sqlite3_finalize(stmt));if(rc!=SQLITE_DONE) { LogError(ErrorMessage());return false; } }
    }
    return true;
}
int Connection::Count(const char* table,bool cache) {
    if(!m_db||!table)return -1;
    const auto value=m_hshCountValues.find(table);
    if(value!=m_hshCountValues.end()&&sqlite3_changes(m_db)==0)return value->second;
    sqlite3_stmt* stmt=NULL;bool temporary=false;const auto found=m_hshCountStatements.find(table);
    if(found!=m_hshCountStatements.end()) { stmt=found->second;Report(sqlite3_reset(stmt)); }
    else {
        const std::string sql="select count(*) from "+identifier(table);
        if(!Report(sqlite3_prepare_v2(m_db,sql.c_str(),-1,&stmt,NULL)))return -1;
        if(cache) { try { m_hshCountStatements[table]=stmt; } catch(...) { sqlite3_finalize(stmt);throw; } }else temporary=true;
    }
    if(sqlite3_step(stmt)!=SQLITE_ROW) { if(temporary)sqlite3_finalize(stmt);return -1; }
    const int count=sqlite3_column_int(stmt,0);
    try { m_hshCountValues[table]=count; } catch(...) { if(temporary)sqlite3_finalize(stmt);else sqlite3_reset(stmt);throw; }
    if(temporary)Report(sqlite3_finalize(stmt));else { Report(sqlite3_reset(stmt));Report(sqlite3_clear_bindings(stmt)); }
    return count;
}
void Connection::ClearCountCache() { for(auto& item:m_hshCountStatements)sqlite3_finalize(item.second);m_hshCountStatements.clear();m_hshCountValues.clear(); }
bool Connection::SelectAll(Results& r,const char* table) { return Execute(r,("select "+std::string(r.GetColumns())+" from "+identifier(table)+" ").c_str()); }
bool Connection::SelectWhere(Results& r,const char* table,const char* condition) {
    if(!condition)return false;return Execute(r,("select "+std::string(r.GetColumns())+" from "+identifier(table)+" where "+condition).c_str());
}
bool Connection::SelectAt(Results& r,const char* table,int rowID) {
    const std::string sql="select "+std::string(r.GetColumns())+" from "+identifier(table)+" where ROWID = "+format("%d",rowID)+" LIMIT 1";
    return Execute(r,sql.c_str());
}
bool Connection::SelectAt(Results& r,const char* table,const char* column,const char* value) {
    const std::string sql="select "+std::string(r.GetColumns())+" from "+identifier(table)+" where "+identifier(column)+" = "+format("%Q",value)+(r.SingleQuery()?" LIMIT 1":" ");
    return Execute(r,sql.c_str());
}
bool Connection::SelectAt(Results& r,const char* table,const char* column,int value) {
    const std::string sql="select "+std::string(r.GetColumns())+" from "+identifier(table)+" where "+identifier(column)+" = "+format("%d",value)+(r.SingleQuery()?" LIMIT 1":" ");
    return Execute(r,sql.c_str());
}
bool Connection::SelectAt(Results& r,const char* table,const char* column,double value) {
    const std::string sql="select "+std::string(r.GetColumns())+" from "+identifier(table)+" where "+identifier(column)+" = ?1"+(r.SingleQuery()?" LIMIT 1":" ");
    Command command(this);if(!AcquireCommand(command,sql.c_str()))return false;
    if(!Report(sqlite3_bind_double(command.stmt,1,value))) { ReleaseCommand(command);return false; }
    try { return r.SetCommand(command); }catch(...) { ReleaseCommand(command);throw; }
}
int Connection::TotalChanges() const { return m_db?sqlite3_changes(m_db):0; }
void Connection::Analyze() const { Execute("ANALYZE"); }
void Connection::Vacuum() const { Execute("VACUUM"); }
int Connection::StatementCount() const { if(!m_db)return 0;int count=0;for(sqlite3_stmt* s=sqlite3_next_stmt(m_db,NULL);s;s=sqlite3_next_stmt(m_db,s))++count;return count; }
const char* Connection::StatementSQL(int index) const { if(!m_db||index<0)return NULL;for(sqlite3_stmt* s=sqlite3_next_stmt(m_db,NULL);s;s=sqlite3_next_stmt(m_db,s))if(index--==0)return sqlite3_sql(s);return NULL; }
bool Connection::SetBusyTimeout(int ms) { return m_db&&Report(sqlite3_busy_timeout(m_db,ms)); }
const char* Connection::CalculateMemoryStats() {
    int used=0,high=0,cache=0,cacheHigh=0,schema=0,schemaHigh=0,stmt=0,stmtHigh=0;
    sqlite3_status(SQLITE_STATUS_MEMORY_USED,&used,&high,0);
    if(m_db) { sqlite3_db_status(m_db,SQLITE_DBSTATUS_CACHE_USED,&cache,&cacheHigh,0);sqlite3_db_status(m_db,SQLITE_DBSTATUS_SCHEMA_USED,&schema,&schemaHigh,0);sqlite3_db_status(m_db,SQLITE_DBSTATUS_STMT_USED,&stmt,&stmtHigh,0); }
    m_strMemoryStats=format("SQLite memory: %d bytes; peak: %d bytes; cache: %d bytes; schema: %d bytes; statements: %d bytes",used,high,cache,schema,stmt);
    return m_strMemoryStats.c_str();
}
bool Connection::ValidateFKConstraints(bool allowNULL) const {
    (void)allowNULL;LogMessage("Validating Foreign Key Constraints...");bool valid=true;Results tables;
    if(!Execute(tables,"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"))return false;
    while(tables.Step()) {
        const std::string table=tables.GetText(0);Results keys;
        if(!Execute(keys,("PRAGMA foreign_key_list("+identifier(table.c_str())+")").c_str()))return false;
        struct Key { std::string parent,from,to; };std::map<int,std::vector<Key> > groups;
        while(keys.Step()) { Key k={keys.GetText(2),keys.GetText(3),keys.GetText(4)?keys.GetText(4):""};groups[keys.GetInt(0)].push_back(k); }
        for(const auto& group:groups) {
            const auto& list=group.second;std::vector<std::string> primary;
            for(const auto& key:list)if(key.to.empty()) {
                Results columns;if(!Execute(columns,("PRAGMA table_info("+identifier(key.parent.c_str())+")").c_str()))return false;
                std::map<int,std::string> ordered;while(columns.Step())if(columns.GetInt(5)>0)ordered[columns.GetInt(5)]=columns.GetText(1);
                for(const auto& col:ordered)primary.push_back(col.second);break;
            }
            std::string projection,nonnull,match;
            for(size_t i=0;i<list.size();++i) {
                const auto& k=list[i];const std::string local="c."+identifier(k.from.c_str());
                if(i) { projection+=",";nonnull+=" AND ";match+=" AND "; }
                projection+=local;nonnull+=local+" IS NOT NULL";
                if(k.to.empty()&&i>=primary.size()) { LogError("Foreign key parent primary key is missing");valid=false;match.clear();break; }
                const std::string& target=k.to.empty()?primary[i]:k.to;
                match+="p."+identifier(target.c_str())+" = "+local;
            }
            if(match.empty())continue;
            const std::string sql="SELECT "+projection+" FROM "+identifier(table.c_str())+" c WHERE "+nonnull+" AND NOT EXISTS (SELECT 1 FROM "+identifier(list[0].parent.c_str())+" p WHERE "+match+")";
            Results missing;if(!Execute(missing,sql.c_str())) { valid=false;continue; }
            while(missing.Step()) { valid=false;for(size_t i=0;i<list.size();++i) {
                const auto& k=list[i];const char* value=missing.GetText(static_cast<int>(i));
                LogError(format("Invalid Reference on %s.%s - \"%s\" does not exist in %s",table.c_str(),k.from.c_str(),value?value:"NULL",k.parent.c_str()).c_str());
            } }
        }
    }
    LogMessage(valid?"Passed Validation.":"Failed Validation.");return valid;
}
void* Connection::operator new(size_t size) { return ::operator new(size); }
void Connection::operator delete(void* p) { ::operator delete(p); }
}
