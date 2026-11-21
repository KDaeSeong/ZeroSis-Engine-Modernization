#pragma once
#include "ScriptArguments.h"
#include "ScriptCatalog.h"
extern "C" {
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
}
#include <array>
#include <cstdio>
#include <cstring>
#include <limits>
#include <set>

namespace ZeroSisHost {
class ScriptSystem final : public ICvEngineScriptSystem1 {
public:
    explicit ScriptSystem(lua_Alloc allocator=nullptr,void* allocatorData=nullptr,std::shared_ptr<const ScriptCatalog> catalog=nullptr)
        :allocator_(allocator),allocatorData_(allocatorData),catalog_(std::move(catalog)){}
    ~ScriptSystem(){if(!Close())std::terminate();}
    ScriptSystem(const ScriptSystem&)=delete;
    ScriptSystem& operator=(const ScriptSystem&)=delete;
    bool IsOwner() const noexcept{return owner_==GetCurrentThreadId();}
    const char* LastError() const {if(!IsOwner())throw std::logic_error("Script diagnostics require owner thread");return error_.data();}
    unsigned ForeignCalls() const noexcept{return foreignCalls_.load();}
    std::size_t ThreadCount() const{Owner();return states_.size();}
    std::size_t ArgumentCount() const{Owner();return arguments_.size();}
    bool IsQuiescent() const {
        Owner();if(dispatchDepth_ || closing_ || initializing_)return false;
        for(const auto& vm:states_)if(vm->active)return false;return true;
    }
    bool IsClosed() const{Owner();return closed_;}
    const ScriptCatalog* Catalog() const noexcept{return catalog_.get();}
    bool GameLibrariesBound() const{Owner();return library_!=nullptr;}
    void BindGameLibraries(ICvScriptSystemUtility1* library,ICvEngineUtility4* engine){
        Owner();if(!library || !engine || closed_ || !IsQuiescent() || !states_.empty() || library_)
            throw std::logic_error("Game script libraries require an open, empty, quiescent service");
        if(!engine->IsGameCoreThread() || !engine->HasGameCoreLock())
            throw std::logic_error("Game library binding requires the GameCore owner lock");
        library_=library;libraryEngine_=engine;
    }
    bool Close() noexcept {
        if(!OwnerOrReject())return false;
        if(closed_)return true;
        if(!IsQuiescent()){Error("Script close during an active callback");return false;}
        if(libraryEngine_ && !libraryEngine_->HasGameCoreLock()){Error("Game script close requires the GameCore lock");return false;}
        closing_=true;
        // All callbacks are quiescent before borrowed Lua states and arguments disappear.
        while(!states_.empty())states_.pop_back();
        arguments_.clear();library_=nullptr;libraryEngine_=nullptr;closing_=false;closed_=true;return true;
    }
    lua_State* CreateLuaThread(const char* name) override {
        Owner();if(!name || !*name)throw std::invalid_argument("Script thread name missing");
        if(dispatchDepth_ || closing_ || closed_ || initializing_)throw std::logic_error("Cannot create a script thread during dispatch, registration or after close");
        if(libraryEngine_ && !libraryEngine_->HasGameCoreLock())throw std::logic_error("Game script creation requires the GameCore lock");
        std::unique_ptr<VM> vm(new VM);vm->name=name;
        vm->state=allocator_?lua_newstate(allocator_,allocatorData_):luaL_newstate();
        if(!vm->state)throw std::bad_alloc();
        Initializing initialization(*this,vm);
        if(lua_cpcall(vm->state,&Initialize,this)!=0){LuaError(vm->state,0);throw std::runtime_error(error_.data());}
        if(library_){
            CFunctionCall call={&RegisterGameLibraries,library_};
            if(lua_cpcall(vm->state,&CFunctionThunk,&call)!=0){LuaError(vm->state,0);throw std::runtime_error(error_.data());}
        }
        lua_State* state=vm->state;states_.push_back(std::move(vm));return state;
    }
    void FreeLuaThread(lua_State* state) override {
        if(!OwnerOrReject() || !state)return;
        if(libraryEngine_ && !libraryEngine_->HasGameCoreLock()){Error("Game script release requires the GameCore lock");return;}
        if(dispatchDepth_ || closing_){Error("Cannot free a script thread during dispatch or close");return;}
        for(auto found=states_.begin();found!=states_.end();++found)if((*found)->state==state){
            if((*found)->active){Error("Cannot free an active script thread");return;}
            closing_=true;states_.erase(found);closing_=false;return;
        }
        Error("Unknown or already released script thread");
    }
    ICvEngineScriptSystemArgs1* CreateArgs() override{return CreateArgs(0);}
    ICvEngineScriptSystemArgs1* CreateArgs(unsigned reserve) override {
        Owner();if(closing_ || closed_)throw std::logic_error("Cannot create arguments after script close");
        std::unique_ptr<ScriptArguments> args(new ScriptArguments(reserve));auto* result=args.get();
        arguments_.emplace(result,std::move(args));return result;
    }
    void DestroyArgs(ICvEngineScriptSystemArgs1* args) override {
        if(!OwnerOrReject() || !args)return;
        if(arguments_.erase(args)==0)Error("Unknown or already released script arguments");
    }
    void RegisterFile(std::string name,std::string contents){
        Owner();if(closing_ || closed_)throw std::logic_error("Cannot register files after script close");
        if(name.find('\0')!=std::string::npos)throw std::invalid_argument("NUL in script file name");
        files_[ScriptCatalog::Key(name.c_str())]=std::move(contents);
    }
    bool LoadFile(lua_State* state,const char* name) override {
        if(!OwnerOrReject())return false;
        try{
            VM* vm=Find(state);if(!vm){Error("Invalid script file target");return false;}
            auto key=ScriptCatalog::Key(name);const auto found=files_.find(key);std::string contents;
            if(found!=files_.end())contents=found->second;
            else{
                const auto* file=catalog_?catalog_->Resolve(key.c_str()):nullptr;
                if(!file){Error("Script file is not registered");return false;}key=file->path;contents=file->contents;
            }
            // Own the complete text while Lua may collect objects and reenter RegisterFile.
            if(!vm->loading.insert(key).second){Error("Circular script include");return false;}
            Loading loading(*vm,key);const char* data=contents.data();auto length=contents.size();
            if(length>=3 && std::memcmp(data,"\xef\xbb\xbf",3)==0){data+=3;length-=3;}
            return Execute(state,data,length,key.c_str());
        }catch(const std::exception& e){Error(e.what());return false;}
    }
    bool Execute(lua_State* state,const char* code,std::size_t length,const char* name="host") noexcept {
        if(!OwnerOrReject())return false;
        VM* vm=Find(state);if(!vm || (!code && length) || !name){Error("Invalid script execution input");return false;}
        Activity activity(*vm);const int base=lua_gettop(state);CodeCall call={code?code:"",length,name};
        if(lua_cpcall(state,&ExecuteThunk,&call)!=0){LuaError(state,base);return false;}
        lua_settop(state,base);return true;
    }
    bool RegisterFunction(lua_State* state,const char* name,lua_CFunction function) noexcept {
        if(!OwnerOrReject())return false;
        VM* vm=Find(state);if(!vm || !name || !function){Error("Invalid native script function");return false;}
        Activity activity(*vm);RegisterCall call={name,function};const int base=lua_gettop(state);
        if(lua_cpcall(state,&RegisterThunk,&call)!=0){LuaError(state,base);return false;}return true;
    }
    bool CallCFunction(lua_State* state,lua_CFunction function,void* args) override {
        if(!OwnerOrReject())return false;
        VM* vm=Find(state);if(!vm || !function){Error("Invalid protected C call");return false;}
        Activity activity(*vm);CFunctionCall call={function,args};const int base=lua_gettop(state);
        if(lua_cpcall(state,&CFunctionThunk,&call)!=0){LuaError(state,base);return false;}
        lua_settop(state,base);return true;
    }
    bool CallFunction(lua_State* state,unsigned args,unsigned returns) override {
        if(!OwnerOrReject())return false;
        VM* vm=Find(state);if(!vm || args>static_cast<unsigned>(INT_MAX) || returns>static_cast<unsigned>(INT_MAX)){
            Error("Invalid protected Lua call");return false;
        }
        const int top=lua_gettop(state);
        if(args>=static_cast<unsigned>(top) || !lua_isfunction(state,top-static_cast<int>(args))){Error("Script function/arguments missing");return false;}
        Activity activity(*vm);const int base=top-static_cast<int>(args)-1;
        if(!ReserveStack(state,static_cast<int>(returns)))return false;
        if(lua_pcall(state,static_cast<int>(args),static_cast<int>(returns),0)!=0){LuaError(state,base);return false;}return true;
    }
    bool CallHook(const char* name,ICvEngineScriptSystemArgs1* args,bool& value) override{return BooleanEvent(name,args,value,"hook");}
    bool CallTestAll(const char* name,ICvEngineScriptSystemArgs1* args,bool& value) override{return BooleanEvent(name,args,value,"all");}
    bool CallTestAny(const char* name,ICvEngineScriptSystemArgs1* args,bool& value) override{return BooleanEvent(name,args,value,"any");}
    bool CallAccumulator(const char* name,ICvEngineScriptSystemArgs1* args,int& value) override {
        double candidate=0;if(!Event(name,args,"int",candidate))return false;
        if(!std::isfinite(candidate) || candidate<INT_MIN || candidate>INT_MAX || std::floor(candidate)!=candidate){Error("Integer script accumulator overflow or fraction");return false;}
        value=static_cast<int>(candidate);return true;
    }
    bool CallAccumulator(const char* name,ICvEngineScriptSystemArgs1* args,float& value) override {
        double candidate=0;if(!Event(name,args,"float",candidate))return false;
        if(!std::isfinite(candidate) || std::abs(candidate)>(std::numeric_limits<float>::max)()){Error("Float script accumulator overflow");return false;}
        value=static_cast<float>(candidate);return true;
    }
private:
    struct VM {lua_State* state=nullptr;unsigned active=0;std::string name;std::set<std::string> loading;~VM(){if(state)lua_close(state);}};
    struct Initializing {
        Initializing(ScriptSystem& system,std::unique_ptr<VM>& vm):system_(system),vm_(vm){system_.initializing_=vm.get();}
        ~Initializing(){
            if(vm_){system_.closing_=true;vm_.reset();system_.closing_=false;}
            system_.initializing_=nullptr;
        }
        ScriptSystem& system_;std::unique_ptr<VM>& vm_;
    };
    struct Loading {
        Loading(VM& vm,const std::string& key):vm_(vm),key_(key){}
        ~Loading(){vm_.loading.erase(key_);}VM& vm_;const std::string& key_;
    };
    struct Activity {explicit Activity(VM& vm):vm_(vm){++vm_.active;}~Activity(){--vm_.active;}VM& vm_;};
    struct Dispatch {explicit Dispatch(ScriptSystem& system):system_(system){++system_.dispatchDepth_;}~Dispatch(){--system_.dispatchDepth_;}ScriptSystem& system_;};
    struct CFunctionCall {lua_CFunction function;void* args;};
    struct RegisterCall {const char* name;lua_CFunction function;};
    struct CodeCall {const char* code;std::size_t length;const char* name;};
    struct EventCall {const char* name;const char* mode;const std::vector<ScriptValue>* args;int reference=LUA_NOREF;double result=0;};
    struct EventFrame {
        lua_State* state;EventCall call;
        ~EventFrame(){if(call.reference>=0){
            // Prepare reserves two caller slots and both free-list entries already exist.
            // No allocation or user callback occurs while releasing the snapshot.
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_REFS");
            luaL_unref(state,-1,call.reference);lua_pop(state,1);
        }}
    };
    void Owner() const{if(!IsOwner())throw std::logic_error("Script VM requires its owner thread");}
    bool OwnerOrReject() noexcept{if(IsOwner())return true;foreignCalls_.fetch_add(1);return false;}
    void Error(const char* text) noexcept{
        if(!text)text="Unknown script error";std::size_t n=0;while(n<error_.size()-1 && text[n])++n;
        std::memmove(error_.data(),text,n);error_[n]=0;
    }
    void LuaError(lua_State* state,int base) noexcept{
        Error(lua_type(state,-1)==LUA_TSTRING?lua_tostring(state,-1):"Lua failed with a non-string error");lua_settop(state,base);
    }
    VM* Find(lua_State* state) noexcept{
        if(closing_ || closed_)return nullptr;
        if(initializing_ && initializing_->state==state)return initializing_;
        for(auto& vm:states_)if(vm->state==state)return vm.get();return nullptr;
    }
    static int ReserveThunk(lua_State* state){
        const int count=*static_cast<int*>(lua_touserdata(state,1));
        if(!lua_checkstack(state,count))return luaL_error(state,"Script stack capacity exceeded");return 0;
    }
    bool ReserveStack(lua_State* state,int count) noexcept {
        const int base=lua_gettop(state);
        if(lua_cpcall(state,&ReserveThunk,&count)!=0){LuaError(state,base);return false;}
        // Lua 5.1 cpcall retained the grown backing stack. No allocation/callback/GC
        // occurs between that protected reserve and extending the caller frame limit.
        if(!lua_checkstack(state,count)){Error("Script caller stack capacity exceeded");return false;}return true;
    }
    static int ProtectedCallback(lua_State* state,lua_CFunction function){
        char failure[1024]={};bool failed=false;
        try{return function(state);}catch(const std::exception& e){std::snprintf(failure,sizeof(failure),"C++ script callback: %s",e.what());failed=true;}
        catch(...){std::snprintf(failure,sizeof(failure),"Unknown C++ script callback exception");failed=true;}
        if(failed){lua_pushstring(state,failure);return lua_error(state);}return 0;
    }
    static int SafeCallback(lua_State* state){
        auto* function=static_cast<lua_CFunction*>(lua_touserdata(state,lua_upvalueindex(1)));
        return ProtectedCallback(state,*function);
    }
    static int RegisterThunk(lua_State* state){
        auto* call=static_cast<RegisterCall*>(lua_touserdata(state,1));
        auto* function=static_cast<lua_CFunction*>(lua_newuserdata(state,sizeof(lua_CFunction)));*function=call->function;
        lua_pushcclosure(state,&SafeCallback,1);lua_setglobal(state,call->name);return 0;
    }
    static int CFunctionThunk(lua_State* state){
        auto* call=static_cast<CFunctionCall*>(lua_touserdata(state,1));lua_settop(state,0);lua_pushlightuserdata(state,call->args);
        return ProtectedCallback(state,call->function);
    }
    static int ExecuteThunk(lua_State* state){
        auto* call=static_cast<CodeCall*>(lua_touserdata(state,1));lua_settop(state,0);
        if(luaL_loadbuffer(state,call->code,call->length,call->name)!=0)return lua_error(state);
        lua_call(state,0,0);return 0;
    }
    static int RegisterGameLibraries(lua_State* state){
        auto* library=static_cast<ICvScriptSystemUtility1*>(lua_touserdata(state,1));lua_settop(state,0);
        library->RegisterScriptLibraries(state);return 0;
    }
    static int Include(lua_State* state){
        auto* system=static_cast<ScriptSystem*>(lua_touserdata(state,lua_upvalueindex(1)));
        if(lua_type(state,1)!=LUA_TSTRING)return luaL_error(state,"include requires a file name");
        if(!lua_isnoneornil(state,2) && (lua_type(state,2)!=LUA_TBOOLEAN || lua_toboolean(state,2)))
            return luaL_error(state,"Pattern/optional include is not implemented");
        std::size_t length=0;const char* name=lua_tolstring(state,1,&length);
        if(std::strlen(name)!=length)return luaL_error(state,"NUL in include file name");
        // LoadFile owns its C++ text/guard outside nested protected Lua calls. It
        // returns normally before this Lua frame raises an error; no RAII is skipped.
        if(!system->LoadFile(state,name))return luaL_error(state,"include failed: %s",system->LastError());
        return 0;
    }
    static int Initialize(lua_State* state){
        auto* system=static_cast<ScriptSystem*>(lua_touserdata(state,1));
        const luaL_Reg libraries[]={{"",luaopen_base},{LUA_TABLIBNAME,luaopen_table},{LUA_STRLIBNAME,luaopen_string},{LUA_MATHLIBNAME,luaopen_math},{nullptr,nullptr}};
        for(const luaL_Reg* library=libraries;library->func;++library){lua_pushcfunction(state,library->func);lua_pushstring(state,library->name);lua_call(state,1,0);}
        lua_pushnil(state);lua_setglobal(state,"dofile");lua_pushnil(state);lua_setglobal(state,"loadfile");
        lua_pushlightuserdata(state,system);lua_pushcclosure(state,&Include,1);lua_setglobal(state,"include");
        const char* bootstrap=R"lua(
local events = {}
GameEvents = setmetatable({}, {__index=function(self, name)
  if type(name) ~= 'string' then error('Event name must be a string') end
  local handlers = {}; events[name] = handlers
  local event = {}
  event.Add = function(fn)
    if type(fn) ~= 'function' then error('Event listener must be a function') end
    handlers[#handlers + 1] = fn
  end
  event.Remove = function(fn)
    for i=#handlers,1,-1 do if handlers[i] == fn then table.remove(handlers,i) end end
  end
  rawset(self,name,event); return event
end})
return function(name)
  local handlers = events[name]
  if not handlers or #handlers == 0 then return nil end
  local snapshot = {}; for i=1,#handlers do snapshot[i]=handlers[i] end; return snapshot
end, function(snapshot, mode, ...)
  local value = mode=='all' and true or false
  if mode=='int' or mode=='float' then value=0 end
  for i=1,#snapshot do
    local result = snapshot[i](...)
    if mode=='int' or mode=='float' then
      if type(result)~='number' then error('Numeric event listener must return a number') end
      value=value+result
    elseif mode=='all' then value=value and not not result
    else value=value or not not result end
  end
  return value
end
)lua";
        if(luaL_loadbuffer(state,bootstrap,std::strlen(bootstrap),"ZeroSis-GameEvents")!=0)return lua_error(state);
        lua_call(state,0,2);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_DISPATCH");
        lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_SNAPSHOT");
        lua_newtable(state);lua_pushinteger(state,0);lua_rawseti(state,-2,0);
        lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_REFS");return 0;
    }
    static int SnapshotThunk(lua_State* state){
        auto* call=static_cast<EventCall*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_REFS");
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_SNAPSHOT");lua_pushstring(state,call->name);
        lua_call(state,1,1);call->reference=luaL_ref(state,1);return 0;
    }
    static int EventThunk(lua_State* state){
        auto* call=static_cast<EventCall*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!lua_checkstack(state,static_cast<int>(call->args->size())+4))return luaL_error(state,"Too many script arguments");
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_DISPATCH");
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_EVENT_REFS");lua_rawgeti(state,-1,call->reference);lua_remove(state,-2);
        lua_pushstring(state,call->mode);
        for(const auto& arg:*call->args)switch(arg.type){
            case ICvEngineScriptSystemArgs1::ARGTYPE_NULL:lua_pushnil(state);break;
            case ICvEngineScriptSystemArgs1::ARGTYPE_BOOL:lua_pushboolean(state,arg.boolean);break;
            case ICvEngineScriptSystemArgs1::ARGTYPE_INT:lua_pushinteger(state,arg.integer);break;
            case ICvEngineScriptSystemArgs1::ARGTYPE_FLOAT:lua_pushnumber(state,arg.number);break;
            case ICvEngineScriptSystemArgs1::ARGTYPE_STRING:lua_pushlstring(state,arg.text.data(),arg.text.size());break;
            default:return luaL_error(state,"Invalid script argument type");
        }
        lua_call(state,static_cast<int>(call->args->size())+2,1);
        call->result=(call->mode[0]=='i' || call->mode[0]=='f')?lua_tonumber(state,-1):static_cast<double>(lua_toboolean(state,-1)!=0);
        return 0;
    }
    bool BooleanEvent(const char* name,ICvEngineScriptSystemArgs1* args,bool& value,const char* mode){
        double result=0;if(!Event(name,args,mode,result))return false;value=result!=0;return true;
    }
    bool Event(const char* name,ICvEngineScriptSystemArgs1* args,const char* mode,double& output) noexcept {
        if(!OwnerOrReject())return false;
        try{
            if(!name || !*name || closing_ || closed_ || initializing_){Error("Invalid, registering or closed script event");return false;}
            std::vector<ScriptValue> values;
            if(args){const auto found=arguments_.find(args);if(found==arguments_.end()){Error("Foreign script arguments");return false;}values=found->second->Snapshot();}
            if(values.size()>static_cast<std::size_t>(INT_MAX-4)){Error("Too many event arguments");return false;}
            Dispatch dispatch(*this);bool handled=false;double aggregate=mode[0]=='a'&&mode[1]=='l'?1.0:0.0;
            std::vector<std::unique_ptr<EventFrame>> frames;frames.reserve(states_.size());
            // Every VM snapshot is prepared before the first listener can mutate any VM.
            for(auto& vm:states_){
                Activity active(*vm);if(!ReserveStack(vm->state,2))return false;
                frames.emplace_back(new EventFrame{vm->state,{name,mode,&values}});
                const int base=lua_gettop(vm->state);
                if(lua_cpcall(vm->state,&SnapshotThunk,&frames.back()->call)!=0){LuaError(vm->state,base);return false;}
            }
            for(auto& frame:frames){
                auto& call=frame->call;if(call.reference<0)continue;handled=true;
                VM& vm=*Find(frame->state);Activity active(vm);const int base=lua_gettop(vm.state);
                if(lua_cpcall(vm.state,&EventThunk,&call)!=0){LuaError(vm.state,base);return false;}
                lua_settop(vm.state,base);
                if(mode[0]=='i' || mode[0]=='f')aggregate+=call.result;
                else if(mode[0]=='a'&&mode[1]=='l')aggregate=(aggregate!=0 && call.result!=0)?1.0:0.0;
                else aggregate=(aggregate!=0 || call.result!=0)?1.0:0.0;
            }
            if(handled)output=aggregate;return handled;
        }catch(const std::exception& e){Error(e.what());return false;}catch(...){Error("Unknown script event exception");return false;}
    }
    const DWORD owner_=GetCurrentThreadId();
    lua_Alloc allocator_;void* allocatorData_;
    const std::shared_ptr<const ScriptCatalog> catalog_;
    ICvScriptSystemUtility1* library_=nullptr;ICvEngineUtility4* libraryEngine_=nullptr;
    VM* initializing_=nullptr;
    std::vector<std::unique_ptr<VM>> states_;
    std::map<ICvEngineScriptSystemArgs1*,std::unique_ptr<ScriptArguments>> arguments_;
    std::map<std::string,std::string> files_;
    unsigned dispatchDepth_=0;bool closing_=false,closed_=false;
    std::array<char,2048> error_{};
    std::atomic<unsigned> foreignCalls_{0};
};
}
