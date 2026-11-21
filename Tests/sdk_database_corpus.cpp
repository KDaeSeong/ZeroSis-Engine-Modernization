#include "SdkDatabaseIncludes.h"
#include <bcrypt.h>
static unsigned long checks=0;
static void require(bool value) { ++checks;if(!value)throw std::runtime_error("database corpus check"); }
struct Digest {
    BCRYPT_ALG_HANDLE algorithm;BCRYPT_HASH_HANDLE hash;std::vector<unsigned char> object;
    Digest():algorithm(NULL),hash(NULL) {
        require(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,NULL,0)>=0);
        DWORD size=0,got=0;require(BCryptGetProperty(algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&size),sizeof(size),&got,0)>=0);
        object.resize(size);require(BCryptCreateHash(algorithm,&hash,&object[0],size,NULL,0,0)>=0);
    }
    ~Digest() { if(hash)BCryptDestroyHash(hash);if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0); }
    void bytes(const void* data,size_t size) {
        const unsigned char* p=static_cast<const unsigned char*>(data);
        while(size) { const ULONG chunk=static_cast<ULONG>((std::min)(size,static_cast<size_t>(1048576)));require(BCryptHashData(hash,const_cast<PUCHAR>(p),chunk,0)>=0);p+=chunk;size-=chunk; }
    }
    void number(unsigned __int64 value) { unsigned char data[8];for(unsigned i=0;i<8;++i)data[i]=static_cast<unsigned char>(value>>(i*8));bytes(data,8); }
    void text(const char* value) { if(!value) { number(~static_cast<unsigned __int64>(0));return; }const size_t size=strlen(value);number(size);bytes(value,size); }
    void finish() { unsigned char out[32];require(BCryptFinishHash(hash,out,sizeof(out),0)>=0);for(unsigned i=0;i<32;++i)printf("%02x",out[i]); }
private: Digest(const Digest&);Digest& operator=(const Digest&);
};
static std::string identifier(const std::string& name) { std::string out="\"";for(size_t i=0;i<name.size();++i) { if(name[i]=='\"')out+='\"';out+=name[i]; }return out+'\"'; }
static void run(const char* path) {
    Database::Connection db;require(db.Open(path,Database::OPEN_READONLY));Database::SingleResult integrity;
    require(db.Execute(integrity,"PRAGMA integrity_check"));require(integrity.GetText(0)&&!strcmp(integrity.GetText(0),"ok"));integrity.Release();
    Database::Results names;require(db.Execute(names,"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"));
    std::vector<std::string> tables;while(names.Step())tables.push_back(names.GetText(0));names.Release();unsigned __int64 totalRows=0,totalValues=0;
    for(size_t t=0;t<tables.size();++t) {
        const std::string table=identifier(tables[t]);Database::Results columns;require(db.Execute(columns,("SELECT * FROM "+table+" LIMIT 0").c_str()));
        const int count=columns.ColumnCount();std::string sql="SELECT _rowid_,*";
        for(int i=0;i<count;++i)sql+=",hex("+identifier(columns.ColumnName(i))+")";
        sql+=" FROM "+table+" ORDER BY _rowid_";columns.Release();
        Database::Results rows;require(db.Execute(rows,sql.c_str()));require(rows.ColumnCount()==1+count*2);Digest digest;digest.text(tables[t].c_str());digest.number(count);
        for(int i=0;i<=count;++i)digest.text(rows.ColumnName(i));unsigned __int64 n=0;
        while(rows.Step()) {
            for(int i=0;i<=count;++i) {
                digest.number(rows.ColumnType(i));digest.number(rows.GetBool(i));digest.number(rows.GetInt(i));digest.number(rows.GetInt64(i));
                const double value=rows.GetDouble(i);unsigned __int64 bits=0;memcpy(&bits,&value,8);digest.number(bits);digest.text(rows.GetText(i));
            }
            // SQL hex() covers complete BLOB/text bytes including embedded NULs,
            // in addition to the SDK typed getter trace above.
            for(int i=count+1;i<rows.ColumnCount();++i)digest.text(rows.GetText(i));++n;
        }
        require(db.ErrorCode()==101);rows.Release();printf("TABLE|%s|%d|%I64u|",tables[t].c_str(),count,n);digest.finish();printf("\n");totalRows+=n;totalValues+=n*count;
    }
    require(db.StatementCount()==0);printf("CORPUS|%u|%I64u|%I64u|integrity_ok\n",static_cast<unsigned>(tables.size()),totalRows,totalValues);
}
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try { require(argc==2);run(argv[1]);printf("PASS|%lu\n",checks);return 0; }
    catch(const std::exception& e) { fprintf(stderr,"FAILED|%lu|%s\n",checks,e.what());return 1; }
}
