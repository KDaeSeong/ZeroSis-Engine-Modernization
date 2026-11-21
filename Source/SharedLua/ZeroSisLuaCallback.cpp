extern "C"
{
#include <lua.h>
}

#include <exception>
#include <cstddef>

namespace
{
    struct CallbackFailure
    {
        char message[1024];
        int failed;
    };

    void Append(char* destination, std::size_t capacity, const char* source)
    {
        std::size_t position = 0;
        while(position + 1 < capacity && destination[position] != '\0')
        {
            ++position;
        }
        if(position + 1 >= capacity || source == 0)
        {
            return;
        }
        while(position + 1 < capacity && *source != '\0')
        {
            destination[position++] = *source++;
        }
        destination[position] = '\0';
    }
}

extern "C" __declspec(dllexport) int ZeroSisLuaInvoke(lua_State* state, lua_CFunction callback)
{
    CallbackFailure failure = {{0}, 0};
    int resultCount = 0;

    if(callback == 0)
    {
        Append(failure.message, sizeof(failure.message), "C++ Lua callback is null");
        failure.failed = 1;
    }
    else
    {
        try
        {
            resultCount = callback(state);
        }
        catch(const std::exception& exception)
        {
            Append(failure.message, sizeof(failure.message), "C++ Lua callback: ");
            Append(failure.message, sizeof(failure.message), exception.what());
            failure.failed = 1;
        }
        catch(...)
        {
            Append(failure.message, sizeof(failure.message), "Unknown C++ Lua callback exception");
            failure.failed = 1;
        }
    }

    if(failure.failed)
    {
        lua_pushstring(state, failure.message);
        return lua_error(state);
    }
    return resultCount;
}
