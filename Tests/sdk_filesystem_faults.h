#pragma once
#include "SdkFileSystem.h"
#include <algorithm>
#include <climits>
enum class FsFault { None, Open, Read, ReadZero, ReadOver, Write, WriteZero, WriteOver, Flush, Close, Commit };
class FaultFileApi final : public ZeroSisFileSystem::FileApi {
public:
    FsFault fault=FsFault::None;
    DWORD chunk=UINT_MAX;
    unsigned failAfter=0,calls=0,commits=0,live=0;
    bool Trip(FsFault f) noexcept {
        if(fault!=f || calls++<failAfter) return false;
        fault=FsFault::None; SetLastError(ERROR_DISK_FULL); return true;
    }
    HANDLE Open(const wchar_t* p,DWORD a,DWORD s,DWORD c,DWORD f) noexcept override {
        if(Trip(FsFault::Open)) return INVALID_HANDLE_VALUE;
        HANDLE h=FileApi::Open(p,a,s,c,f); if(h!=INVALID_HANDLE_VALUE) ++live; return h;
    }
    BOOL Read(HANDLE h,void* p,DWORD n,DWORD* done) noexcept override {
        if(Trip(FsFault::Read)) { *done=0; return FALSE; }
        if(Trip(FsFault::ReadZero)) { *done=0; return TRUE; }
        if(Trip(FsFault::ReadOver)) { *done=n+1; return TRUE; }
        return FileApi::Read(h,p,(std::min)(chunk,n),done);
    }
    BOOL Write(HANDLE h,const void* p,DWORD n,DWORD* done) noexcept override {
        if(Trip(FsFault::Write)) { *done=0; return FALSE; }
        if(Trip(FsFault::WriteZero)) { *done=0; return TRUE; }
        if(Trip(FsFault::WriteOver)) { *done=n+1; return TRUE; }
        return FileApi::Write(h,p,(std::min)(chunk,n),done);
    }
    BOOL Flush(HANDLE h) noexcept override { return Trip(FsFault::Flush) ? FALSE : FileApi::Flush(h); }
    BOOL Close(HANDLE h) noexcept override {
        if(Trip(FsFault::Close)) return FALSE;
        BOOL ok=FileApi::Close(h); if(ok) --live; return ok;
    }
    BOOL Commit(const wchar_t* a,const wchar_t* b) noexcept override {
        ++commits; return Trip(FsFault::Commit) ? FALSE : FileApi::Commit(a,b);
    }
};

