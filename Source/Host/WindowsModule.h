#pragma once
#include "GameCoreSession.h"

namespace ZeroSisHost {
class WindowsModule final : public ModuleBackend {
public:
    explicit WindowsModule(std::wstring path):path_(std::move(path)){}
    void Open() override {
        if(module_)throw std::logic_error("GameCore module is already loaded");
        module_=LoadLibraryExW(path_.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        if(!module_)throw std::runtime_error("Cannot load the verified x64 GameCore module; Windows error "+std::to_string(GetLastError()));
        getContext_=Resolve<GetContextFn>("DllGetGameContext");
        shutdown_=Resolve<ShutdownFn>("ZeroSisShutdownGameCore");
        if(!getContext_ || !shutdown_)throw std::runtime_error("Required GameCore lifecycle exports are missing");
    }
    ICvGameContext1* GetContext() override {
        if(!getContext_)throw std::logic_error("GameCore context export is unavailable");return getContext_();
    }
    bool ShutdownCore() override {return shutdown_ && shutdown_()!=FALSE;}
    bool Close() override {
        if(!module_)return true;
        if(!FreeLibrary(module_))return false;
        module_=nullptr;getContext_=nullptr;shutdown_=nullptr;return true;
    }
private:
    template<class Function> Function Resolve(const char* name) {
        const FARPROC address=GetProcAddress(module_,name);Function result=nullptr;
        static_assert(sizeof(result)==sizeof(address),"Windows function pointer size differs");
        std::memcpy(&result,&address,sizeof(result));return result;
    }
    using GetContextFn=ICvGameContext1*(*)();
    using ShutdownFn=BOOL(*)();
    std::wstring path_;
    HMODULE module_=nullptr;
    GetContextFn getContext_=nullptr;
    ShutdownFn shutdown_=nullptr;
};
}
