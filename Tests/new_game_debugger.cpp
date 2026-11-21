// Bounded local debugger for a private new-game candidate, never an installed game.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <dbghelp.h>
#include <cstdio>
#include <cstdint>
#include <string>
#include <vector>

struct ModuleRecord {DWORD64 base;DWORD size;std::vector<RUNTIME_FUNCTION> functions;};
static std::vector<ModuleRecord> modules;
static DWORD64 CALLBACK ModuleBase(HANDLE,DWORD64 address){
    for(const auto& item:modules)if(address>=item.base && address-item.base<item.size)return item.base;
    return 0;
}
static void* CALLBACK FunctionTable(HANDLE,DWORD64 address){
    for(auto& item:modules)if(address>=item.base && address-item.base<item.size){
        const DWORD64 rva=address-item.base;
        for(auto& function:item.functions)if(rva>=function.BeginAddress && rva<function.EndAddress)return &function;
    }
    return nullptr;
}
static bool Read(HANDLE process,DWORD64 address,void* target,SIZE_T bytes){
    SIZE_T read=0;return ReadProcessMemory(process,reinterpret_cast<const void*>(address),target,bytes,&read) && read==bytes;
}
static void Module(HANDLE process,HANDLE file,void* base){
    const auto address=reinterpret_cast<DWORD64>(base);IMAGE_DOS_HEADER dos{};IMAGE_NT_HEADERS64 headers{};
    if(Read(process,address,&dos,sizeof(dos)) && dos.e_magic==IMAGE_DOS_SIGNATURE && dos.e_lfanew>0 &&
        Read(process,address+static_cast<DWORD>(dos.e_lfanew),&headers,sizeof(headers)) && headers.Signature==IMAGE_NT_SIGNATURE &&
        headers.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC){
        ModuleRecord item{address,headers.OptionalHeader.SizeOfImage,{}};
        const auto& directory=headers.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
        if(directory.Size && directory.Size<16*1024*1024 && directory.VirtualAddress<item.size && directory.Size<=item.size-directory.VirtualAddress){
            item.functions.resize(directory.Size/sizeof(RUNTIME_FUNCTION));
            if(!Read(process,address+directory.VirtualAddress,item.functions.data(),item.functions.size()*sizeof(RUNTIME_FUNCTION)))item.functions.clear();
        }
        modules.push_back(std::move(item));
    }
    std::vector<wchar_t> path(32768);
    const DWORD length=file?GetFinalPathNameByHandleW(file,path.data(),static_cast<DWORD>(path.size()),FILE_NAME_NORMALIZED):0;
    if(length && length<path.size()){
        std::printf("DEBUG_MODULE base=%016llX path=",static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(base)));
        const int bytes=WideCharToMultiByte(CP_UTF8,0,path.data(),static_cast<int>(length),nullptr,0,nullptr,nullptr);
        std::vector<char> utf8(static_cast<std::size_t>(bytes));
        WideCharToMultiByte(CP_UTF8,0,path.data(),static_cast<int>(length),utf8.data(),bytes,nullptr,nullptr);
        std::fwrite(utf8.data(),1,utf8.size(),stdout);std::putchar('\n');
        SymLoadModuleExW(process,file,path.data(),nullptr,reinterpret_cast<DWORD64>(base),0,nullptr,0);
    }
    if(file)CloseHandle(file);
}

static void Stack(HANDLE process,DWORD threadId){
    HANDLE thread=OpenThread(THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,threadId);
    if(!thread)return;
    CONTEXT context{};context.ContextFlags=CONTEXT_FULL;
    if(GetThreadContext(thread,&context)){
        STACKFRAME64 frame{};
        frame.AddrPC.Offset=context.Rip;frame.AddrPC.Mode=AddrModeFlat;
        frame.AddrStack.Offset=context.Rsp;frame.AddrStack.Mode=AddrModeFlat;
        frame.AddrFrame.Offset=context.Rbp;frame.AddrFrame.Mode=AddrModeFlat;
        for(unsigned index=0;index<64 && frame.AddrPC.Offset;++index){
            std::printf("DEBUG_STACK index=%u pc=%016llX module=%016llX\n",index,
                static_cast<unsigned long long>(frame.AddrPC.Offset),
                static_cast<unsigned long long>(ModuleBase(process,frame.AddrPC.Offset)));
            if(!StackWalk64(IMAGE_FILE_MACHINE_AMD64,process,thread,&frame,&context,nullptr,
                FunctionTable,ModuleBase,nullptr))break;
        }
    }else std::printf("DEBUG_CONTEXT_ERROR=%lu\n",GetLastError());
    CloseHandle(thread);
}

int wmain(int argc,wchar_t** argv){
    std::setvbuf(stdout,nullptr,_IONBF,0);
    if(argc!=2)return 2;
    const std::wstring executable=argv[1];
    if(executable.find(L"NewGameRuntime")==std::wstring::npos || executable.find(L'\"')!=std::wstring::npos)return 2;
    std::wstring command=L"\""+executable+L"\" --check-new-game en_US";
    STARTUPINFOW startup{};startup.cb=sizeof(startup);startup.dwFlags=STARTF_USESTDHANDLES;
    startup.hStdInput=GetStdHandle(STD_INPUT_HANDLE);startup.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);startup.hStdError=GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION info{};SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    if(!CreateProcessW(executable.c_str(),&command[0],nullptr,nullptr,TRUE,DEBUG_ONLY_THIS_PROCESS|CREATE_NO_WINDOW,
        nullptr,nullptr,&startup,&info)){std::printf("DEBUG_CREATE_ERROR=%lu\n",GetLastError());return 3;}
    SymSetOptions(SYMOPT_DEFERRED_LOADS|SYMOPT_FAIL_CRITICAL_ERRORS|SYMOPT_NO_PROMPTS|SYMOPT_IGNORE_NT_SYMPATH);
    SymInitializeW(info.hProcess,L"",FALSE);
    const ULONGLONG deadline=GetTickCount64()+90000;bool exited=false;DWORD exitCode=0;
    while(!exited && GetTickCount64()<deadline){
        DEBUG_EVENT event{};
        if(!WaitForDebugEvent(&event,1000)){if(GetLastError()==ERROR_SEM_TIMEOUT)continue;break;}
        DWORD action=DBG_CONTINUE;
        switch(event.dwDebugEventCode){
            case CREATE_PROCESS_DEBUG_EVENT:
                Module(info.hProcess,event.u.CreateProcessInfo.hFile,event.u.CreateProcessInfo.lpBaseOfImage);
                if(event.u.CreateProcessInfo.hProcess!=info.hProcess)CloseHandle(event.u.CreateProcessInfo.hProcess);
                if(event.u.CreateProcessInfo.hThread!=info.hThread)CloseHandle(event.u.CreateProcessInfo.hThread);
                break;
            case LOAD_DLL_DEBUG_EVENT:Module(info.hProcess,event.u.LoadDll.hFile,event.u.LoadDll.lpBaseOfDll);break;
            case UNLOAD_DLL_DEBUG_EVENT:SymUnloadModule64(info.hProcess,reinterpret_cast<DWORD64>(event.u.UnloadDll.lpBaseOfDll));break;
            case CREATE_THREAD_DEBUG_EVENT:CloseHandle(event.u.CreateThread.hThread);break;
            case EXCEPTION_DEBUG_EVENT:{
                const auto& exception=event.u.Exception;const DWORD code=exception.ExceptionRecord.ExceptionCode;
                if(code==EXCEPTION_BREAKPOINT && exception.dwFirstChance)break;
                std::printf("DEBUG_EXCEPTION code=%08lX first=%lu address=%016llX\n",code,exception.dwFirstChance,
                    static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(exception.ExceptionRecord.ExceptionAddress)));
                if(code==EXCEPTION_ACCESS_VIOLATION || code==0xC0000374 || code==0xE06D7363 || code==0xC0000409 || !exception.dwFirstChance)Stack(info.hProcess,event.dwThreadId);
                action=DBG_EXCEPTION_NOT_HANDLED;break;
            }
            case EXIT_PROCESS_DEBUG_EVENT:exitCode=event.u.ExitProcess.dwExitCode;exited=true;break;
        }
        if(!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,action))break;
    }
    if(!exited){TerminateProcess(info.hProcess,0xDEAD);WaitForSingleObject(info.hProcess,5000);std::puts("DEBUG_TIMEOUT_OR_FAILURE");}
    SymCleanup(info.hProcess);CloseHandle(info.hThread);CloseHandle(info.hProcess);
    std::printf("DEBUG_EXIT=%08lX\n",exitCode);return exited?0:4;
}
