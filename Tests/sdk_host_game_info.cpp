#include "HostServices.h"
#include "GameInfoDatabase.h"
#include <thread>
#include <cstdlib>
using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value,int line){++checks;if(!value){std::fprintf(stderr,"GAME_INFO_FAILED line=%d\n",line);std::exit(1);}}
#define CHECK(value) Check((value),__LINE__)
static thread_local int budget=-1;
static std::atomic<long long> allocations{0};
void* operator new(std::size_t size){if(budget>=0 && budget--==0){budget=-1;throw std::bad_alloc();}
    void* result=std::malloc(size?size:1);if(!result)throw std::bad_alloc();++allocations;return result;}
void operator delete(void* pointer) noexcept{if(pointer){--allocations;std::free(pointer);}}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete[](void* pointer) noexcept{::operator delete(pointer);}
void operator delete(void* pointer,std::size_t) noexcept{::operator delete(pointer);}
void operator delete[](void* pointer,std::size_t) noexcept{::operator delete(pointer);}
struct Memory {
    int budget=-1;std::size_t bytes=0,blocks=0;
    static void* Allocate(void* context,void* pointer,std::size_t oldSize,std::size_t newSize){
        auto& self=*static_cast<Memory*>(context);
        if(!newSize){if(pointer){self.bytes-=oldSize;--self.blocks;std::free(pointer);}return nullptr;}
        if(newSize>oldSize && self.budget>=0 && self.budget--==0)return nullptr;
        void* result=std::realloc(pointer,newSize);
        if(result){if(!pointer)++self.blocks;self.bytes=self.bytes-oldSize+newSize;}return result;
    }
};
static void Execute(ScriptSystem& scripts,lua_State* vm,const char* code){
    if(!scripts.Execute(vm,code,std::strlen(code))){std::fprintf(stderr,"%s\n",scripts.LastError());CHECK(false);}
    CHECK(lua_gettop(vm)==0);
}
static void Fixture(Database::Connection& db){
    CHECK(db.Open(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE|Database::OPEN_FULLMUTEX));
    CHECK(db.ExecuteMultiple("CREATE TABLE Defines(Name text PRIMARY KEY,Value);"
        "INSERT INTO Defines VALUES('TEST_DEFINE',17);"
        "CREATE TABLE Items(ID integer PRIMARY KEY,Type text UNIQUE,Enabled boolean,Amount integer,Ratio real,Label text,Optional text);"
        "INSERT INTO Items VALUES(0,'ALPHA',0,-2147483648,1.25,CAST(x'EAB0800041' AS TEXT),NULL);"
        "INSERT INTO Items VALUES(7,'BETA',1,2147483647,-0.125,'semi;colon', 'value');"
        "INSERT INTO Items VALUES(-2,'GAMMA',1,42,0.0,'quote''s -- data',NULL);"
        "CREATE TABLE Relations(Owner text,Other text);INSERT INTO Relations VALUES('ALPHA','BETA');"
        "CREATE TABLE Civilization_Start_Region_Priority(CivilizationType text,RegionType text);"
        "INSERT INTO Civilization_Start_Region_Priority VALUES('CIVILIZATION_ALPHA','REGION_COASTAL');"
        "INSERT INTO Civilization_Start_Region_Priority VALUES('CIVILIZATION_ALPHA','REGION_RIVER');"
        "CREATE TABLE Civilization_Start_Region_Avoid(CivilizationType text,RegionType text);"
        "INSERT INTO Civilization_Start_Region_Avoid VALUES('CIVILIZATION_BETA','REGION_DESERT');"
        "CREATE TABLE GameSpeed_Turns(GameSpeedType text,MonthIncrement integer,TurnsPerIncrement integer);"
        "INSERT INTO GameSpeed_Turns VALUES('GAMESPEED_STANDARD',12,75);"
        "INSERT INTO GameSpeed_Turns VALUES('GAMESPEED_STANDARD',6,25);"
        "CREATE TABLE Empty(ID integer,Type text);CREATE VIEW ItemView AS SELECT * FROM Items;"));
}
static const char* query=R"lua(
function runQuery()
  local rows=0
  for row in GameInfo.Items{Enabled=true} do assert(row.Enabled and row.ID~=0); rows=rows+1 end
  assert(rows==2)
  assert(GameInfo.Items[0].Label==string.char(234,176,128,0,65))
  local count=0
  for row in DB.Query('SELECT ID FROM Items WHERE Enabled=? ORDER BY ID',true) do
    assert(row.ID==-2 or row.ID==7);count=count+1
  end
  assert(count==2)
  local priorities=0
  for row in DB.Query('select count(*) as count from Civilization_Start_Region_Priority where CivilizationType = ?', 'CIVILIZATION_ALPHA') do
    assert(row.count==2); priorities=priorities+1
  end
  assert(priorities==1)
end
)lua";
static void Values(){
    Database::Connection db;Fixture(db);Memory memory;
    {
        ScriptSystem scripts(&Memory::Allocate,&memory);scripts.BindRules(std::make_shared<GameInfoDatabase>(db));
        auto* vm=scripts.CreateLuaThread("rules");
        Execute(scripts,vm,R"lua(
assert(GameInfo.Unknown==nil and GameInfo[false]==nil)
assert(GameDefines.TEST_DEFINE==17)
assert(GameInfo['Items; DROP TABLE Items']==nil)
local alpha=GameInfo.Items[0]
assert(alpha.Type=='ALPHA' and alpha.Enabled==false and type(alpha.Enabled)=='boolean')
assert(alpha.Optional==nil and alpha.Amount==-2147483648 and alpha.Ratio==1.25)
assert(alpha.Label==string.char(234,176,128,0,65))
assert(GameInfo.Items.BETA.ID==7 and GameInfo.Items[-2].Type=='GAMMA')
assert(GameInfo.items.BETA.ID==7 and GameInfo.Items{id=7}().Type=='BETA')
assert(GameInfo.Items[99]==nil and GameInfo.Items.MISSING==nil and GameInfo.Items[false]==nil)
assert(GameInfo.Empty()()==nil)
)lua");
        Execute(scripts,vm,R"lua(
local count=0; for a in GameInfo.Items() do for b in GameInfo.Items() do count=count+1 end end; assert(count==9)
local a,b=GameInfo.Items(),GameInfo.Items(); assert(a().ID==b().ID and a().ID==b().ID)
assert(GameInfo.Items{Enabled=false}().ID==0)
assert(GameInfo.Items{ID=7,Type='BETA'}().Amount==2147483647)
assert(GameInfo.Items("Label='semi;colon'")().ID==7)
assert(GameInfo.Items("Label='quote''s -- data'")().ID==-2)
assert(GameInfo.Items{Label=string.char(234,176,128,0,65)}().ID==0)
assert(GameInfo.Relations{Owner='ALPHA'}().Other=='BETA')
assert(GameInfo.ItemView.BETA.Enabled==true)
assert(GameInfo.Items{ID=123}()==nil)
local rows=DB.Query('SELECT ID, Type FROM Items ORDER BY ID')
assert(rows().ID==-2 and rows().ID==0 and rows().ID==7 and rows()==nil)
local empty=DB.Query('SELECT ID FROM Items WHERE ID=?',123)
assert(empty()==nil)
local bound
for row in DB.Query('SELECT ? AS Missing, ? AS Whole, ? AS Fraction, ? AS Flag, ? AS TextValue',nil,7,0.25,true,string.char(65,0,66)) do bound=row end
assert(bound.Missing==nil and bound.Whole==7 and type(bound.Whole)=='number')
assert(bound.Fraction==0.25 and bound.Flag==1 and bound.TextValue==string.char(65,0,66))
local nulLength
for row in DB.Query('SELECT length(CAST(? AS BLOB)) AS ByteCount',string.char(65,0,66)) do nulLength=row.ByteCount end
assert(nulLength==3)
local speeds=DB.Query('SELECT MonthIncrement, TurnsPerIncrement FROM GameSpeed_Turns WHERE GameSpeedType = ? ORDER BY rowid ASC','GAMESPEED_STANDARD')
local firstSpeed=speeds()
local secondSpeed=speeds()
assert(firstSpeed.MonthIncrement==12 and firstSpeed.TurnsPerIncrement==75)
assert(secondSpeed.MonthIncrement==6 and secondSpeed.TurnsPerIncrement==25 and speeds()==nil)
local quoted=DB.Query([[SELECT '; -- ? :not_a_binding' AS TextValue]])
assert(quoted().TextValue=='; -- ? :not_a_binding')
for _,bad in ipairs({
  'DELETE FROM Items','INSERT INTO Items(ID) VALUES(99)','SELECT 1; DROP TABLE Items',
  'SELECT 1 -- hidden comment','SELECT 1 /* hidden comment */','SELECT ?1','SELECT :named',
  'SELECT @named','SELECT $named','SELECT * FROM no_such_table'
}) do assert(not pcall(function() return DB.Query(bad)() end)) end
assert(not pcall(function() return DB.Query('SELECT ?') end))
assert(not pcall(function() return DB.Query('SELECT 1',7) end))
assert(not pcall(function() return DB.Query('SELECT ?',{}) end))
assert(not pcall(function() return DB.Query('SELECT ?',0/0) end))
local row=GameInfo.Items[0]; row.Amount=999; assert(GameInfo.Items[0].Amount==-2147483648)
for _,bad in ipairs({'1; DROP TABLE Items','1 -- comment','1 /* comment */','UnknownColumn=3',"Type='",'ID=?','ID=:id','ID=@id','ID=$id'}) do
  assert(not pcall(function() GameInfo.Items(bad) end))
end
assert(not pcall(function() return GameInfo.Items[0.25] end))
assert(not pcall(function() return GameInfo.Items{NotAColumn=1} end))
assert(not pcall(function() return GameInfo.Items{ID={}} end))
assert(not pcall(function() return GameInfo.Items(true) end))
assert(not pcall(function() return GameInfo.Items{ID=0/0} end))
assert(not pcall(function() return GameInfo.Items('ID=?',0) end))
)lua");
        CHECK(db.StatementCount()==0);
        CHECK(db.Execute("UPDATE Items SET Amount=9007199254740992 WHERE ID=0"));
        Execute(scripts,vm,"assert(not pcall(function() return GameInfo.Items[0] end))");CHECK(db.StatementCount()==0);
        CHECK(db.Execute("UPDATE Items SET Amount=17 WHERE ID=0"));Execute(scripts,vm,"assert(GameInfo.Items[0].Amount==17)");
        Execute(scripts,vm,query);Execute(scripts,vm,"runQuery()");lua_gc(vm,LUA_GCCOLLECT,0);
        const auto live=allocations.load();unsigned luaFailures=0,cppFailures=0;
        // Load and intern the caller before failures. Each attempt runs the same
        // query and must release its native snapshot/statements on every exit.
        lua_getglobal(vm,"runQuery");const int call=luaL_ref(vm,LUA_REGISTRYINDEX);
        for(int n=0;n<1500;++n){
            lua_rawgeti(vm,LUA_REGISTRYINDEX,call);memory.budget=n;
            const bool ok=scripts.CallFunction(vm,0,0);memory.budget=-1;
            CHECK(lua_gettop(vm)==0 || (!ok && lua_gettop(vm)==1 && lua_isfunction(vm,1)));
            lua_settop(vm,0);CHECK(db.StatementCount()==0);lua_gc(vm,LUA_GCCOLLECT,0);CHECK(allocations.load()==live);
            if(ok)break;++luaFailures;CHECK(n<1499);Execute(scripts,vm,"runQuery()");
        }
        for(int n=0;n<1500;++n){
            lua_rawgeti(vm,LUA_REGISTRYINDEX,call);budget=n;
            const bool ok=scripts.CallFunction(vm,0,0);budget=-1;
            CHECK(lua_gettop(vm)==0 || (!ok && lua_gettop(vm)==1 && lua_isfunction(vm,1)));
            lua_settop(vm,0);CHECK(db.StatementCount()==0);lua_gc(vm,LUA_GCCOLLECT,0);CHECK(allocations.load()==live);
            if(ok)break;++cppFailures;CHECK(n<1499);Execute(scripts,vm,"runQuery()");
        }
        CHECK(luaFailures>0 && cppFailures>0);luaL_unref(vm,LUA_REGISTRYINDEX,call);
        std::printf("GAME_INFO_FAILURES lua=%u cpp=%u\n",luaFailures,cppFailures);
        std::thread other([&]{CHECK(!scripts.Execute(vm,"runQuery()",10));});other.join();
        CHECK(scripts.Close() && memory.bytes==0 && memory.blocks==0 && db.StatementCount()==0);
    }
    db.Close();CHECK(db.ErrorCode()==-1);
}
static void CreationFailures(){
    Database::Connection db;Fixture(db);unsigned failures=0;
    for(int n=0;n<1600;++n){
        Memory memory;ScriptSystem scripts(&Memory::Allocate,&memory);scripts.BindRules(std::make_shared<GameInfoDatabase>(db));
        memory.budget=n;bool failed=false;
        try{scripts.CreateLuaThread("rules installation");}catch(const std::exception&){failed=true;}
        memory.budget=-1;
        if(failed){++failures;CHECK(scripts.ThreadCount()==0 && memory.bytes==0 && memory.blocks==0);}
        CHECK(scripts.Close() && memory.bytes==0 && memory.blocks==0 && db.StatementCount()==0);
        if(!failed)break;CHECK(n<1599);
    }
    CHECK(failures>0);std::printf("GAME_INFO_CREATE_FAILURES=%u\n",failures);
}
int main(){
    try{Values();CreationFailures();CHECK(allocations.load()==0);std::printf("HOST_GAME_INFO_PASS checks=%u GAMECORE_LOADED=false\n",checks);return 0;}
    catch(const std::exception& e){std::fprintf(stderr,"GAME_INFO_EXCEPTION %s\n",e.what());return 1;}
}
