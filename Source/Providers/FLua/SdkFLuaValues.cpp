#include "SdkFLuaIncludes.h"

namespace {
void RequireIndex(lua_State* state, int index) {
    if (!state) throw std::invalid_argument("FLua value requires a live Lua state");
    const int top = lua_gettop(state);
    if (index == 0 || index > top || index < lua_upvalueindex(255)
        || (index < 0 && index > LUA_REGISTRYINDEX && index < -top))
        throw std::out_of_range("FLua value stack index is absent");
    if (index == LUA_ENVIRONINDEX || index < LUA_GLOBALSINDEX) {
        lua_Debug frame = {};
        if (!lua_getstack(state, 0, &frame) || !lua_getinfo(state, "Su", &frame)
            || (index < LUA_GLOBALSINDEX && (std::strcmp(frame.what, "C") != 0
                || LUA_GLOBALSINDEX-index > frame.nups)))
            throw std::out_of_range("FLua pseudo-index has no active owner");
    }
    if (lua_type(state, index) == LUA_TNONE)
        throw std::out_of_range("FLua value stack index is absent");
}
int Capture(lua_State* state, int index) {
    RequireIndex(state, index);
    if (!lua_checkstack(state, 1)) throw std::length_error("FLua value stack has no capacity");
    lua_pushvalue(state, index);
    return luaL_ref(state, LUA_REGISTRYINDEX);
}
}

namespace FLua {
bool SharedLuaRegistry::sm_bAllowed = false;
FCriticalSection ms_CriticalSection;
Value::Value() : m_pkLuaState(NULL), m_iRef(LUA_NOREF) {}
Value::Value(lua_State* state, int index) : m_pkLuaState(NULL), m_iRef(LUA_NOREF) {
    const int reference = Capture(state, index);
    m_pkLuaState = state; m_iRef = reference;
}
Value::Value(const StackValue& source) : m_pkLuaState(NULL), m_iRef(LUA_NOREF) {
    const int reference = Capture(source.GetLuaState(), source.GetIndex());
    m_pkLuaState = source.GetLuaState(); m_iRef = reference;
}
Value::Value(const Value& source) : m_pkLuaState(source.m_pkLuaState), m_iRef(LUA_NOREF) {
    if (source.Valid()) {
        if (!source.Push()) throw std::length_error("FLua copy stack has no capacity");
        m_iRef = luaL_ref(m_pkLuaState, LUA_REGISTRYINDEX);
    }
}
Value::~Value() { Unref(); }
void Value::LuaStateDestroyed() { m_pkLuaState = NULL; m_iRef = LUA_NOREF; }
void Value::Unref() {
    if (Valid()) luaL_unref(m_pkLuaState, LUA_REGISTRYINDEX, m_iRef);
    LuaStateDestroyed();
}
void Value::Swap(Value& other) {
    lua_State* state = m_pkLuaState; const int reference = m_iRef;
    m_pkLuaState = other.m_pkLuaState; m_iRef = other.m_iRef;
    other.m_pkLuaState = state; other.m_iRef = reference;
}
const Value& Value::operator=(const Value& other) {
    if (this != &other) { Value replacement(other); Swap(replacement); }
    return *this;
}
void Value::Set(lua_State* state, int index) {
    Value replacement(state, index);
    Swap(replacement);
}
bool Value::Push() const {
    if (!Valid() || !lua_checkstack(m_pkLuaState, 1)) return false;
    lua_rawgeti(m_pkLuaState, LUA_REGISTRYINDEX, m_iRef);
    return true;
}
Type Value::GetType() const {
    if (!Push()) return TYPE_NONE;
    const Type type = static_cast<Type>(lua_type(m_pkLuaState, -1));
    lua_pop(m_pkLuaState, 1); return type;
}
const char* Value::GetTypeName() const {
    return m_pkLuaState ? lua_typename(m_pkLuaState, GetType()) : "Invalid";
}
bool Value::IsNil() const {
    if (!Push()) return true;
    const bool result = lua_isnil(m_pkLuaState, -1) != 0;
    lua_pop(m_pkLuaState, 1); return result;
}
const void* Value::ToPointer() const {
    if (!Push()) return NULL;
    const void* pointer = lua_topointer(m_pkLuaState, -1);
    lua_pop(m_pkLuaState, 1); return pointer;
}
const bool Value::operator==(const Value& other) const {
    if (m_pkLuaState != other.m_pkLuaState) return false;
    if (!m_pkLuaState) return true;
    if (!Valid() || !other.Valid()) return Valid() == other.Valid();
    if (!lua_checkstack(m_pkLuaState, 2)) throw std::length_error("FLua equality stack has no capacity");
    lua_rawgeti(m_pkLuaState, LUA_REGISTRYINDEX, m_iRef);
    lua_rawgeti(m_pkLuaState, LUA_REGISTRYINDEX, other.m_iRef);
    const bool equal = lua_equal(m_pkLuaState, -1, -2) != 0;
    lua_pop(m_pkLuaState, 2); return equal;
}
bool Table::Push() const {
    if (!m_kLuaVal.Push()) return false;
    if (lua_istable(GetLuaState(), -1)) return true;
    lua_pop(GetLuaState(), 1); return false;
}
bool Table::Valid() const {
    if (!Push()) return false;
    lua_pop(GetLuaState(), 1); return true;
}
void ErrorHandler::operator()(const TCHAR* message) const {
    if (m_pkClass) (m_pkClass->*m_pfnFunc)(message);
    else Details::UnsafeCast<ErrorHandlerStaticFunc>(m_pfnFunc)(message);
}
namespace Details {
void LockAccess() { ms_CriticalSection.Enter(); }
void UnlockAccess() { ms_CriticalSection.Leave(); }
namespace {
struct AccessGuard {
    AccessGuard() { LockAccess(); }
    ~AccessGuard() { UnlockAccess(); }
};
struct StackGuard {
    lua_State* state; int top;
    explicit StackGuard(lua_State* input) : state(input), top(lua_gettop(input)) {}
    ~StackGuard() { lua_settop(state, top); }
};
struct ProtectedCall {
    lua_CFunction function; void* data; char exception[1024];
};
int InvokeProtected(lua_State* state) {
    ProtectedCall* call = static_cast<ProtectedCall*>(lua_touserdata(state, 1));
    lua_pushlightuserdata(state, call->data); lua_replace(state, 1);
    try { return call->function(state); }
    catch (const std::exception& error) {
        strncpy_s(call->exception, sizeof(call->exception), error.what(), _TRUNCATE);
    } catch (...) {
        strcpy_s(call->exception, "Unknown C++ exception in Lua callback");
    }
    // End the C++ catch before any Lua operation can longjmp out of this frame.
    lua_pushstring(state, call->exception);
    return lua_error(state);
}
}
bool CCallWithErrorHandling(lua_State* state, lua_CFunction function, void* data) {
    if (!state || !function) throw std::invalid_argument("FLua protected call requires a state and function");
    AccessGuard access;
    StackGuard stack(state);
    ProtectedCall call = { function, data, {0} };
    const int status = lua_cpcall(state, InvokeProtected, &call);
    if (status == 0) return true;
    // Non-string errors are valid Lua values; do not invoke allocating tostring here.
    const char* message = lua_type(state, -1) == LUA_TSTRING ? lua_tostring(state, -1) : "(non-string Lua error)";
    const char* format = status == LUA_ERRRUN ? "Runtime Error: %s" : status == LUA_ERRMEM ? "Memory Allocation Error: %s" : status == LUA_ERRERR ? "Error Handler Error: %s" : "Error: %s";
    Error(format, message);
    return false;
}
void Error(const char* format, ...) {
    if (!format) throw std::invalid_argument("FLua error format is null");
    va_list args; va_start(args, format);
    va_list count; va_copy(count, args);
    const int length = _vscprintf(format, count);
    va_end(count);
    if (length < 0) { va_end(args); throw std::runtime_error("FLua error format is invalid"); }
    std::vector<char> buffer;
    try { buffer.resize(static_cast<size_t>(length) + 1); }
    catch (...) { va_end(args); throw; }
    const int written = vsprintf_s(&buffer[0], buffer.size(), format, args);
    va_end(args);
    if (written < 0) throw std::runtime_error("FLua error formatting failed");
    GetErrorHandler()(&buffer[0]);
}
}
}
