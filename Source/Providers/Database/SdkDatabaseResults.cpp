#define CvGameDatabaseAPI __declspec(dllexport)
#include "SdkDatabaseIncludes.h"
#include "sqlite3.h"
#include "SdkDatabaseLifetime.h"

namespace {
void reportExecution(const Database::Command& command,int rc,bool expectedRows) {
    if(!command.connection||!command.stmt)return;
    if(!expectedRows&&rc==SQLITE_ROW)command.connection->LogWarning("A row was returned during an Execute command.");
    else command.connection->LogError(command.connection->ErrorMessage());
    const char* sql=sqlite3_sql(command.stmt);const std::string text="While executing - '"+std::string(sql?sql:"")+"'";
    command.connection->LogMessage(text.c_str());
}
}
namespace Database {
Results::Results(const char* columns):m_Command(),m_szColumns(NULL),m_bSingleQuery(false) { SetColumns(columns); }
Results::Results(const Results& other):m_Command(other.m_Command.connection),m_szColumns(NULL),m_bSingleQuery(other.m_bSingleQuery),m_hshColumnPositions(other.m_hshColumnPositions) {
    SetColumns(other.m_szColumns);
    try { if(other.m_Command.stmt) {
        if(!Connection::AcquireCommand(m_Command,sqlite3_sql(other.m_Command.stmt)))throw std::runtime_error("Cannot prepare copied database result");
        TrackCommand(m_Command.connection,&m_Command);
    } }
    catch(...) { Connection::ReleaseCommand(m_Command);sqlite3_free(const_cast<char*>(m_szColumns));throw; }
}
Results::~Results() { try { Release(); }catch(...) { sqlite3_free(const_cast<char*>(m_szColumns));m_szColumns=NULL; } }
Results& Results::operator=(const Results& other) {
    if(this==&other)return *this;
    Results next(other);
    static_assert(noexcept(m_hshColumnPositions.swap(next.m_hshColumnPositions)),"Results commit requires a nonthrowing column-map swap");
    SwapCommands(m_Command,next.m_Command);
    std::swap(m_szColumns,next.m_szColumns);std::swap(m_bSingleQuery,next.m_bSingleQuery);
    m_hshColumnPositions.swap(next.m_hshColumnPositions);return *this;
}
const char* Results::GetColumns() const { return m_szColumns?m_szColumns:"*"; }
void Results::SetColumns(const char* columns) {
    char* next=columns?sqlite3_mprintf("%s",columns):NULL;if(columns&&!next)throw std::bad_alloc();
    sqlite3_free(const_cast<char*>(m_szColumns));m_szColumns=next;
}
bool Results::SetCommand(Command& command) {
    Connection::ReleaseCommand(m_Command);TrackCommand(command.connection,&m_Command);
    m_Command=command;command.stmt=NULL;m_hshColumnPositions.clear();
    return m_bSingleQuery?Step():true;
}
void Results::Release() { Connection::ReleaseCommand(m_Command);sqlite3_free(const_cast<char*>(m_szColumns));m_szColumns=NULL; }
bool Results::Execute() {
    if(!m_Command.stmt||!m_Command.connection)return false;const int rc=sqlite3_step(m_Command.stmt);
    if(rc!=SQLITE_DONE)reportExecution(m_Command,rc,false);return rc==SQLITE_DONE;
}
bool Results::TryExecute() {
    if(!m_Command.stmt||!m_Command.connection)return false;const int rc=sqlite3_step(m_Command.stmt);
    if(rc==SQLITE_DONE||rc==SQLITE_ABORT||rc==SQLITE_CONSTRAINT)return true;
    reportExecution(m_Command,rc,false);return false;
}
bool Results::Step() {
    if(!m_Command.stmt)return false;const int rc=sqlite3_step(m_Command.stmt);
    if(rc!=SQLITE_ROW&&rc!=SQLITE_DONE)reportExecution(m_Command,rc,true);return rc==SQLITE_ROW;
}
bool Results::Reset() { return m_Command.stmt&&sqlite3_reset(m_Command.stmt)==SQLITE_OK&&sqlite3_clear_bindings(m_Command.stmt)==SQLITE_OK; }
bool Results::TryReset() { if(!m_Command.stmt)return false;sqlite3_reset(m_Command.stmt);return sqlite3_clear_bindings(m_Command.stmt)==SQLITE_OK; }
bool Results::Bind(int i,const char* s,int length,bool copy) { return m_Command.stmt&&sqlite3_bind_text(m_Command.stmt,i,s,length,copy?SQLITE_TRANSIENT:SQLITE_STATIC)==SQLITE_OK; }
bool Results::Bind(int i,const char* s,bool copy) { return Bind(i,s,-1,copy); }
bool Results::Bind(int i,const wchar_t* s,int length,bool copy) {
    if(length>INT_MAX/2)return false;
    return m_Command.stmt&&sqlite3_bind_text16(m_Command.stmt,i,s,length<0?-1:length*2,copy?SQLITE_TRANSIENT:SQLITE_STATIC)==SQLITE_OK;
}
bool Results::Bind(int i,const wchar_t* s,bool copy) { return Bind(i,s,-1,copy); }
bool Results::Bind(int i,double n) { return m_Command.stmt&&sqlite3_bind_double(m_Command.stmt,i,n)==SQLITE_OK; }
bool Results::Bind(int i,float n) { return Bind(i,static_cast<double>(n)); }
bool Results::Bind(int i,int n) { return m_Command.stmt&&sqlite3_bind_int(m_Command.stmt,i,n)==SQLITE_OK; }
bool Results::Bind(int i,__int64 n) { return m_Command.stmt&&sqlite3_bind_int64(m_Command.stmt,i,n)==SQLITE_OK; }
bool Results::BindNULL(int i) { return m_Command.stmt&&sqlite3_bind_null(m_Command.stmt,i)==SQLITE_OK; }
int Results::ColumnCount() const { return m_Command.stmt?sqlite3_column_count(m_Command.stmt):0; }
const char* Results::ColumnName(int i) { return m_Command.stmt?sqlite3_column_name(m_Command.stmt,i):NULL; }
ColumnTypes Results::ColumnType(int i) {
    if(!m_Command.stmt)return COLTYPE_NULL;const int type=sqlite3_column_type(m_Command.stmt,i);
    if(type==SQLITE_INTEGER) { const char* decl=sqlite3_column_decltype(m_Command.stmt,i);if(decl&&!strcmp(decl,"boolean"))return COLTYPE_BOOL; }
    return static_cast<ColumnTypes>(type);
}
const char* Results::ColumnTypeName(int i) {
    switch(ColumnType(i)) { case COLTYPE_INT:return "integer";case COLTYPE_FLOAT:return "float";case COLTYPE_TEXT:return "text";case COLTYPE_NULL:return "null";case COLTYPE_BOOL:return "boolean";default:return NULL; }
}
void Results::HashColumnPositions() { for(int i=0;i<ColumnCount();++i) { const char* name=ColumnName(i);if(name)m_hshColumnPositions[name]=i; } }
int Results::ColumnPosition(const char* name) { if(!name)return -1;if(m_hshColumnPositions.empty())HashColumnPositions();const auto found=m_hshColumnPositions.find(name);return found==m_hshColumnPositions.end()?-1:found->second; }
bool Results::HasColumn(const char* name) { return ColumnPosition(name)>=0; }
const char* Results::GetText(int i) { return m_Command.stmt?reinterpret_cast<const char*>(sqlite3_column_text(m_Command.stmt,i)):NULL; }
const wchar_t* Results::GetText16(int i) { return m_Command.stmt?static_cast<const wchar_t*>(sqlite3_column_text16(m_Command.stmt,i)):NULL; }
int Results::GetInt(int i) { return m_Command.stmt?sqlite3_column_int(m_Command.stmt,i):0; }
__int64 Results::GetInt64(int i) { return m_Command.stmt?sqlite3_column_int64(m_Command.stmt,i):0; }
double Results::GetDouble(int i) { return m_Command.stmt?sqlite3_column_double(m_Command.stmt,i):0; }
float Results::GetFloat(int i) { return static_cast<float>(GetDouble(i)); }
bool Results::GetBool(int i) { const ColumnTypes t=ColumnType(i);if(t==COLTYPE_INT||t==COLTYPE_BOOL)return GetInt(i)!=0;if(t==COLTYPE_TEXT) { const char* text=GetText(i);return text&&(text[0]=='t'||text[0]=='T'); }return false; }
#define DATABASE_VALUE(TYPE,GETTER) \
TYPE Results::GETTER(const char* name) { return GETTER(ColumnPosition(name)); } \
void Results::GetValue(int i,TYPE& value) { value=GETTER(i); } \
void Results::GetValue(const char* name,TYPE& value) { value=GETTER(name); }
DATABASE_VALUE(const char*,GetText)
DATABASE_VALUE(const wchar_t*,GetText16)
DATABASE_VALUE(int,GetInt)
DATABASE_VALUE(__int64,GetInt64)
DATABASE_VALUE(float,GetFloat)
DATABASE_VALUE(double,GetDouble)
DATABASE_VALUE(bool,GetBool)
#undef DATABASE_VALUE
bool Results::SingleQuery() const { return m_bSingleQuery; }
void Results::SingleQuery(bool single) { m_bSingleQuery=single; }
SingleResult::SingleResult(const char* columns):Results(columns) { SingleQuery(true); }
void* Results::operator new(size_t size) { return ::operator new(size); }
void Results::operator delete(void* p) { ::operator delete(p); }

ResultsCache::ResultsCache(Database::Connection& db):m_db(db) {}
ResultsCache::~ResultsCache() { Clear(); }
void ResultsCache::Clear() { for(auto& item:m_storedResults)delete item.second;m_storedResults.clear(); }
void ResultsCache::Clear(const std::string& key) { const auto found=m_storedResults.find(key);if(found!=m_storedResults.end()) { delete found->second;m_storedResults.erase(found); } }
Database::Connection& ResultsCache::Connection() { return m_db; }
Results* ResultsCache::Get(const std::string& key) { const auto found=m_storedResults.find(key);return found==m_storedResults.end()?NULL:found->second; }
Results* ResultsCache::Prepare(const std::string& key,const char* sql,int length) {
    std::unique_ptr<Results> next(new Results);if(!m_db.Execute(*next,sql,length))return NULL;
    auto inserted=m_storedResults.insert(std::make_pair(key,static_cast<Results*>(NULL)));delete inserted.first->second;inserted.first->second=next.release();return inserted.first->second;
}
const char* ResultsCache::ErrorMessage() const { return m_db.ErrorMessage(); }
}
