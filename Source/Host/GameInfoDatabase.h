#pragma once
#include "ScriptSystem.h"
#include "GameDefinesDatabase.h"
#include <DatabaseResults.h>
#include <cctype>

namespace ZeroSisHost {
// Borrows the session rules connection. Close all ScriptSystem VMs before closing
// that connection. No statement or game object is retained by a Lua iterator.
class GameInfoDatabase final : public ScriptRules {
public:
    explicit GameInfoDatabase(Database::Connection& database):database_(database){}
    void Install(lua_State* state) override {
        if(owner_!=GetCurrentThreadId())luaL_error(state,"GameInfo requires its owner thread");
        InstallGameDefines(state,database_);
        const char* bootstrap=R"lua(
local read = ...
local function iterate(rows)
  local index=0
  return function() index=index+1; return rows[index] end
end
GameInfo=setmetatable({}, {__index=function(self,name)
  if type(name)~='string' or not read(name,nil,2) then return nil end
  local query=setmetatable({}, {
    __index=function(_,key)
      if type(key)~='string' and type(key)~='number' then return nil end
      return read(name,key,1)[1]
    end,
    __call=function(_,filter,...)
      if select('#',...)~=0 then error('GameInfo accepts one filter argument') end
      return iterate(read(name,filter,0))
    end
  })
  rawset(self,name,query)
  return query
end})
DB = type(DB)=='table' and DB or {}
DB.Query=function(sql,...)
  return iterate(read(sql,nil,3,...))
end
)lua";
        if(luaL_loadbuffer(state,bootstrap,std::strlen(bootstrap),"ZeroSis-GameInfo")!=0)lua_error(state);
        lua_pushlightuserdata(state,this);lua_pushcclosure(state,&Read,1);lua_call(state,1,0);
    }
private:
    struct Value {Database::ColumnTypes type=Database::COLTYPE_NULL;double number=0;__int64 integer=0;bool boolean=false;std::string text;};
    struct Snapshot {int mode=0;bool exists=false;std::vector<std::string> columns;std::vector<std::vector<Value>> rows;};
    struct Filter {std::string column;Value value;};
    static std::string Text(lua_State* state,int index,bool identifier=false) {
        if(lua_type(state,index)!=LUA_TSTRING)throw std::invalid_argument("GameInfo requires a string");
        std::size_t size=0;const char* text=lua_tolstring(state,index,&size);
        if(size>INT_MAX || (identifier && (!size || std::strlen(text)!=size)))
            throw std::invalid_argument("Invalid GameInfo name or SQL condition");
        return std::string(text,size);
    }
    static std::string Quote(const std::string& name){
        std::string result="\"";for(char ch:name){result+=ch;if(ch=='\"')result+='\"';}return result+'\"';
    }
    static Value Argument(lua_State* state,int index) {
        Value value;
        switch(lua_type(state,index)){
            case LUA_TSTRING:value.type=Database::COLTYPE_TEXT;value.text=Text(state,index);break;
            case LUA_TNUMBER:value.type=Database::COLTYPE_FLOAT;value.number=lua_tonumber(state,index);
                if(!std::isfinite(value.number))throw std::invalid_argument("Nonfinite GameInfo filter");break;
            case LUA_TBOOLEAN:value.type=Database::COLTYPE_BOOL;value.boolean=lua_toboolean(state,index)!=0;break;
            default:throw std::invalid_argument("GameInfo filter values must be strings, numbers or booleans");
        }
        return value;
    }
    static Value QueryArgument(lua_State* state,int index) {
        Value value;
        switch(lua_type(state,index)){
            case LUA_TNIL:value.type=Database::COLTYPE_NULL;break;
            case LUA_TSTRING:value.type=Database::COLTYPE_TEXT;value.text=Text(state,index);break;
            case LUA_TNUMBER:{
                value.number=lua_tonumber(state,index);
                if(!std::isfinite(value.number))throw std::invalid_argument("Nonfinite DB.Query parameter");
                if(std::floor(value.number)==value.number && std::abs(value.number)<=9007199254740991.0){
                    value.type=Database::COLTYPE_INT;value.integer=static_cast<__int64>(value.number);
                }else value.type=Database::COLTYPE_FLOAT;
                break;
            }
            case LUA_TBOOLEAN:value.type=Database::COLTYPE_BOOL;value.boolean=lua_toboolean(state,index)!=0;break;
            default:throw std::invalid_argument("DB.Query parameters must be nil, numbers, booleans or strings");
        }
        return value;
    }
    static std::size_t ValidateReadOnlySelect(const std::string& sql){
        if(sql.empty() || sql.find('\0')!=std::string::npos)throw std::invalid_argument("DB.Query requires nonempty SQL without NUL bytes");
        std::size_t first=0;while(first<sql.size() && std::isspace(static_cast<unsigned char>(sql[first])))++first;
        if(first+6>sql.size() || _strnicmp(sql.data()+first,"SELECT",6)!=0 ||
           (first+6<sql.size() && (std::isalnum(static_cast<unsigned char>(sql[first+6])) || sql[first+6]=='_')))
            throw std::invalid_argument("DB.Query accepts a read-only SELECT statement only");
        char quote=0;std::size_t parameters=0;
        for(std::size_t i=0;i<sql.size();++i){
            const char ch=sql[i];
            if(quote){
                if(ch==quote){if(i+1<sql.size() && sql[i+1]==quote)++i;else quote=0;}
                continue;
            }
            if(ch=='\'' || ch=='\"' || ch=='`'){quote=ch;continue;}
            if(ch=='['){quote=']';continue;}
            if(ch==';' || ch==':' || ch=='@' || ch=='$' ||
               (i+1<sql.size() && ((ch=='-' && sql[i+1]=='-') || (ch=='/' && sql[i+1]=='*'))))
                throw std::invalid_argument("DB.Query rejects statement separators, comments and named parameters");
            if(ch=='?'){
                if(i+1<sql.size() && std::isdigit(static_cast<unsigned char>(sql[i+1])))
                    throw std::invalid_argument("DB.Query accepts anonymous question-mark parameters only");
                if(parameters==static_cast<std::size_t>(INT_MAX))throw std::overflow_error("Too many DB.Query parameters");
                ++parameters;
            }
        }
        if(quote)throw std::invalid_argument("DB.Query has an unterminated quoted token");
        return parameters;
    }
    static void Bind(Database::Results& rows,int index,const Value& value){
        bool ok=false;
        switch(value.type){
            case Database::COLTYPE_NULL:ok=rows.BindNULL(index);break;
            case Database::COLTYPE_BOOL:ok=rows.Bind(index,value.boolean?1:0);break;
            case Database::COLTYPE_INT:ok=rows.Bind(index,value.integer);break;
            case Database::COLTYPE_FLOAT:ok=rows.Bind(index,value.number);break;
            case Database::COLTYPE_TEXT:ok=rows.Bind(index,value.text.data(),static_cast<int>(value.text.size()));break;
            default:throw std::invalid_argument("Unsupported DB.Query parameter type");
        }
        if(!ok)throw std::runtime_error("DB.Query parameter binding failed");
    }
    static void Condition(const std::string& condition){
        // A condition is one SQL expression, never a list of statements. Quoted
        // punctuation is data; comments could conceal our closing parenthesis.
        char quote=0;
        for(std::size_t i=0;i<condition.size();++i){
            const char ch=condition[i];
            if(quote){if(ch==quote){if(i+1<condition.size() && condition[i+1]==quote)++i;else quote=0;}continue;}
            if(ch=='\'' || ch=='\"' || ch=='`'){quote=ch;continue;}
            if(ch=='['){quote=']';continue;}
            if(ch==';' || ch=='?' || ch==':' || ch=='@' || ch=='$' ||
               (i+1<condition.size() && ((ch=='-' && condition[i+1]=='-') || (ch=='/' && condition[i+1]=='*'))))
                throw std::invalid_argument("GameInfo condition must be one expression without comments or unbound parameters");
        }
        if(quote)throw std::invalid_argument("Unterminated GameInfo condition quote");
    }
    void Require(bool ok) const {if(!ok)throw std::runtime_error(database_.ErrorMessage()?database_.ErrorMessage():"GameInfo database failure");}
    void Complete() const {
        const int code=database_.ErrorCode();
        if(code!=0 && code!=101)throw std::runtime_error("GameInfo database iteration failed");
    }
    Snapshot Query(lua_State* state,int argumentTop){
        if(owner_!=GetCurrentThreadId())throw std::logic_error("GameInfo requires its owner thread");
        Snapshot result;result.mode=static_cast<int>(lua_tointeger(state,3));
        if(result.mode==3)return QuerySql(state,argumentTop);
        const std::string table=Text(state,1,true);
        {
            Database::Results schema;
            Require(database_.Execute(schema,"SELECT name FROM sqlite_master WHERE name=? COLLATE NOCASE AND type IN ('table','view') AND name NOT GLOB 'sqlite_*'"));
            Require(schema.Bind(1,table.c_str()));result.exists=schema.Step();if(!result.exists)Complete();
        }
        if(result.mode==2)return result;
        if(!result.exists)throw std::invalid_argument("GameInfo table no longer exists");
        {
            Database::Results schema;Require(database_.Execute(schema,("SELECT * FROM "+Quote(table)+" LIMIT 0").c_str()));
            for(int i=0;i<schema.ColumnCount();++i)result.columns.emplace_back(schema.ColumnName(i));
        }
        std::vector<Filter> filters;std::string condition;
        if(result.mode==1){
            auto value=Argument(state,2);
            if(value.type==Database::COLTYPE_FLOAT && (std::floor(value.number)!=value.number || std::abs(value.number)>9007199254740991.0))
                throw std::invalid_argument("GameInfo ID must be an exact integer");
            filters.push_back({value.type==Database::COLTYPE_TEXT?"Type":"ID",std::move(value)});
        }else if(lua_istable(state,2)){
            lua_pushnil(state);
            while(lua_next(state,2)){
                filters.push_back({Text(state,-2,true),Argument(state,-1)});lua_pop(state,1);
            }
            std::sort(filters.begin(),filters.end(),[](const Filter& a,const Filter& b){return a.column<b.column;});
        }else if(lua_type(state,2)==LUA_TSTRING){condition=Text(state,2,true);Condition(condition);}
        else if(!lua_isnoneornil(state,2))throw std::invalid_argument("GameInfo expects a condition table or SQL expression");
        std::string sql="SELECT *";
        // The SDK exposes text without a byte count. SQL supplies byte lengths so
        // UTF-8 and embedded NUL bytes survive the provider/Lua boundary exactly.
        for(const auto& column:result.columns)sql+=",length(CAST("+Quote(column)+" AS BLOB))";
        sql+=" FROM "+Quote(table);
        if(!condition.empty())sql+=" WHERE ("+condition+")";
        for(std::size_t i=0;i<filters.size();++i){
            if(std::find_if(result.columns.begin(),result.columns.end(),[&](const std::string& name){return _stricmp(name.c_str(),filters[i].column.c_str())==0;})==result.columns.end())
                throw std::invalid_argument("Unknown GameInfo filter column");
            sql+=(i?" AND ":" WHERE ")+Quote(filters[i].column)+"=?";
        }
        if(result.mode==1)sql+=" LIMIT 1";
        Database::Results rows;Require(database_.Execute(rows,sql.c_str()));
        for(std::size_t i=0;i<filters.size();++i){
            const auto& value=filters[i].value;const int position=static_cast<int>(i+1);
            if(value.type==Database::COLTYPE_TEXT)Require(rows.Bind(position,value.text.data(),static_cast<int>(value.text.size())));
            else if(value.type==Database::COLTYPE_BOOL)Require(rows.Bind(position,value.boolean?1:0));
            else Require(rows.Bind(position,value.number));
        }
        while(rows.Step()){
            std::vector<Value> row;row.reserve(result.columns.size());
            for(std::size_t i=0;i<result.columns.size();++i){
                const int column=static_cast<int>(i);Value value;value.type=rows.ColumnType(column);
                switch(value.type){
                    case Database::COLTYPE_NULL:break;
                    case Database::COLTYPE_BOOL:value.boolean=rows.GetBool(column);break;
                    case Database::COLTYPE_INT:{const auto n=rows.GetInt64(column);
                        if(n<-9007199254740991LL || n>9007199254740991LL)throw std::overflow_error("GameInfo integer exceeds exact Lua range");
                        value.number=static_cast<double>(n);break;}
                    case Database::COLTYPE_FLOAT:value.number=rows.GetDouble(column);
                        if(!std::isfinite(value.number))throw std::overflow_error("GameInfo nonfinite database number");break;
                    case Database::COLTYPE_TEXT:{
                        const int bytes=rows.GetInt(static_cast<int>(i+result.columns.size()));const char* text=rows.GetText(column);
                        if(bytes<0 || !text)throw std::runtime_error("GameInfo database text conversion failed");
                        value.text.assign(text,static_cast<std::size_t>(bytes));break;}
                    default:throw std::runtime_error("GameInfo binary database fields are unsupported");
                }
                row.push_back(std::move(value));
            }
            if(result.rows.size()>=INT_MAX)throw std::overflow_error("Too many GameInfo rows");
            result.rows.push_back(std::move(row));
        }
        Complete();return result;
    }
    Snapshot QuerySql(lua_State* state,int argumentTop){
        Snapshot result;result.mode=3;
        const std::string sql=Text(state,1);
        const std::size_t parameterCount=ValidateReadOnlySelect(sql);
        const std::size_t argumentCount=static_cast<std::size_t>(argumentTop-3);
        if(parameterCount!=argumentCount)throw std::invalid_argument("DB.Query SQL parameter count does not match its arguments");
        std::vector<Value> arguments;arguments.reserve(argumentCount);
        for(std::size_t i=0;i<argumentCount;++i)arguments.push_back(QueryArgument(state,static_cast<int>(i+4)));

        const std::string source="SELECT * FROM ("+sql+") AS _host_query";
        {
            Database::Results schema;
            Require(database_.Execute(schema,(source+" LIMIT 0").c_str()));
            for(int i=0;i<schema.ColumnCount();++i){
                const char* name=schema.ColumnName(i);
                if(!name)throw std::runtime_error("DB.Query returned an unnamed column");
                for(const auto& prior:result.columns)if(_stricmp(prior.c_str(),name)==0)
                    throw std::invalid_argument("DB.Query result columns must have unique names");
                result.columns.emplace_back(name);
            }
            if(result.columns.empty())throw std::invalid_argument("DB.Query SELECT must return at least one column");
            Complete();
        }

        std::string query="SELECT _host_query.*";
        for(const auto& column:result.columns)
            query+=",length(CAST(_host_query."+Quote(column)+" AS BLOB))";
        query+=" FROM ("+sql+") AS _host_query";
        Database::Results rows;Require(database_.Execute(rows,query.c_str()));
        for(std::size_t i=0;i<arguments.size();++i)Bind(rows,static_cast<int>(i+1),arguments[i]);
        while(rows.Step()){
            std::vector<Value> row;row.reserve(result.columns.size());
            for(std::size_t i=0;i<result.columns.size();++i){
                const int column=static_cast<int>(i);Value value;value.type=rows.ColumnType(column);
                switch(value.type){
                    case Database::COLTYPE_NULL:break;
                    case Database::COLTYPE_BOOL:value.boolean=rows.GetBool(column);break;
                    case Database::COLTYPE_INT:{const __int64 integer=rows.GetInt64(column);
                        if(integer<-9007199254740991LL || integer>9007199254740991LL)throw std::overflow_error("DB.Query integer exceeds exact Lua range");
                        value.number=static_cast<double>(integer);break;}
                    case Database::COLTYPE_FLOAT:value.number=rows.GetDouble(column);
                        if(!std::isfinite(value.number))throw std::overflow_error("DB.Query nonfinite database number");break;
                    case Database::COLTYPE_TEXT:{
                        const __int64 bytes=rows.GetInt64(static_cast<int>(i+result.columns.size()));const char* text=rows.GetText(column);
                        if(bytes<0 || bytes>INT_MAX || (bytes>0 && !text))throw std::runtime_error("DB.Query text conversion failed");
                        value.text.assign(text?text:"",static_cast<std::size_t>(bytes));break;}
                    default:throw std::runtime_error("DB.Query binary database fields are unsupported");
                }
                row.push_back(std::move(value));
            }
            if(result.rows.size()>=static_cast<std::size_t>(INT_MAX))throw std::overflow_error("Too many DB.Query rows");
            result.rows.push_back(std::move(row));
        }
        Complete();return result;
    }
    static int Publish(lua_State* state){
        const auto& data=*static_cast<const Snapshot*>(lua_touserdata(state,1));
        if(data.mode==2){lua_pushboolean(state,data.exists);return 1;}
        lua_createtable(state,static_cast<int>(data.rows.size()),0);
        for(std::size_t i=0;i<data.rows.size();++i){
            lua_createtable(state,0,static_cast<int>(data.columns.size()));
            for(std::size_t j=0;j<data.columns.size();++j){
                const auto& value=data.rows[i][j];
                switch(value.type){
                    case Database::COLTYPE_NULL:lua_pushnil(state);break;
                    case Database::COLTYPE_BOOL:lua_pushboolean(state,value.boolean);break;
                    case Database::COLTYPE_TEXT:lua_pushlstring(state,value.text.data(),value.text.size());break;
                    default:lua_pushnumber(state,value.number);break;
                }
                lua_setfield(state,-2,data.columns[j].c_str());
            }
            lua_rawseti(state,-2,static_cast<int>(i+1));
        }
        return 1;
    }
    static int Read(lua_State* state){
        auto* self=static_cast<GameInfoDatabase*>(lua_touserdata(state,lua_upvalueindex(1)));
        const int base=lua_gettop(state);char failure[1024]={};int status=0;
        if(!lua_checkstack(state,8))return luaL_error(state,"GameInfo stack capacity exceeded");
        // Prepare the protected publisher before any C++ owner exists. Lua's
        // allocator errors must never skip a vector, string or Results destructor.
        lua_pushcfunction(state,&Publish);
        status=PrepareAndPublish(self,state,failure,sizeof(failure));
        if(failure[0]){lua_settop(state,base);lua_pushstring(state,failure);return lua_error(state);}
        if(status)return lua_error(state);
        return 1;
    }
    __declspec(noinline) static int PrepareAndPublish(GameInfoDatabase* self,lua_State* state,char* failure,std::size_t failureSize){
        int status=0;
        try{
            Snapshot data=self->Query(state,lua_gettop(state)-1); // top slot is the protected publisher.
            lua_pushlightuserdata(state,&data);status=lua_pcall(state,1,1,0);
        }catch(const std::exception& e){std::snprintf(failure,failureSize,"GameInfo: %s",e.what());}
        catch(...){std::snprintf(failure,failureSize,"GameInfo: unknown query failure");}
        return status;
    }
    Database::Connection& database_;
    const DWORD owner_=GetCurrentThreadId();
};
}
