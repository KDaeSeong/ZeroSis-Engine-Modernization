#define ZS_GRANNY_BUILD
#include "GrannyAnimationBridge.h"
#include <Windows.h>
#include <vcclr.h>
#include <algorithm>
#include <cmath>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#using <System.dll>
#using <System.Core.dll>
#using <Firaxis.Framework.dll>
#using <Firaxis.Framework.Granny.dll>

using namespace System;
using namespace System::IO;
using namespace System::Reflection;
using namespace System::Collections::Generic;
using namespace Firaxis::Framework;
using namespace Firaxis::Framework::Granny;

ref class GrannySampler sealed {
    String^ sdk_;
    GrannyContext^ context_;
    VirtualSpace^ space_;
    ProjectConfig^ config_;
    IGrannyFile^ modelFile_;
    IGrannyFile^ animationFile_;
    array<IGrannyTransformTrack^>^ tracks_;
    ResolveEventHandler^ resolver_;
    DWORD owner_;
    float duration_;
    bool spaceAdded_,configAdded_,contextAdded_;
    Assembly^ Resolve(Object^, ResolveEventArgs^ e) {
        String^ name=(gcnew AssemblyName(e->Name))->Name;
        String^ path=Path::Combine(sdk_,name+".dll");
        if(File::Exists(path)) return Assembly::LoadFrom(path);
        return nullptr;
    }
    static void ValidateCurve(IGrannyCurve^ c,int dimension) {
        if(c==nullptr || c->Dimension!=dimension) throw gcnew InvalidDataException("Missing or wrong-dimension Granny curve");
    }
public:
    GrannySampler(String^ sdk,String^ gsd,String^ model,String^ animation) {
        if(!Environment::Is64BitProcess || IntPtr::Size!=8) throw gcnew InvalidOperationException("x64 process required");
        sdk_=Path::GetFullPath(sdk);
        try {
            resolver_=gcnew ResolveEventHandler(this,&GrannySampler::Resolve);
            AppDomain::CurrentDomain->AssemblyResolve += resolver_;
            space_=gcnew VirtualSpace(); space_->BasePaths=gcnew List<String^>(); Context::Add(space_);spaceAdded_=true;
            config_=gcnew ProjectConfig(); Context::Add(config_);configAdded_=true;
            context_=gcnew GrannyContext(); Context::Add(context_);contextAdded_=true;
            context_->LoadStringDatabase(Path::GetFullPath(gsd));
            modelFile_=context_->LoadGrannyFile(Path::GetFullPath(model));
            if(modelFile_==nullptr || modelFile_->Models->Count!=1 || modelFile_->Models[0]->Skeleton==nullptr)
                throw gcnew InvalidDataException("Expected exactly one skeleton model");
            animationFile_=context_->LoadGrannyFile(Path::GetFullPath(animation));
            if(animationFile_==nullptr || animationFile_->Animations->Count!=1) throw gcnew InvalidDataException("Expected exactly one animation");
            IGrannyAnimation^ clip=animationFile_->Animations[0]; duration_=clip->Duration;
            if(Single::IsNaN(duration_) || Single::IsInfinity(duration_) || duration_<=0) throw gcnew InvalidDataException("Invalid animation duration");
            String^ modelName=modelFile_->Models[0]->Name;
            IGrannyTrackGroup^ match=nullptr; int matches=0;
            for each(IGrannyTrackGroup^ g in clip->TrackGroups) if(g->Name==modelName){match=g;++matches;}
            if(matches!=1 || match==nullptr || match->TransformTracks->Count==0 || match->TransformTracks->Count>512)
                throw gcnew InvalidDataException("Animation has no unique matching track group");
            tracks_=gcnew array<IGrannyTransformTrack^>(match->TransformTracks->Count);
            match->TransformTracks->CopyTo(tracks_,0);
            HashSet<String^>^ names=gcnew HashSet<String^>(StringComparer::Ordinal);
            for each(IGrannyTransformTrack^ track in tracks_) {
                if(String::IsNullOrWhiteSpace(track->Name) || !names->Add(track->Name)) throw gcnew InvalidDataException("Invalid or duplicate transform track name");
                ValidateCurve(track->PositionCurve,3); ValidateCurve(track->OrientationCurve,4); ValidateCurve(track->ScaleShearCurve,9);
            }
            owner_=GetCurrentThreadId();
        } catch(Exception^) { ReleaseResources(); throw; } catch(...) { ReleaseResources(); throw; }
    }
    bool IsOwner() { return owner_==GetCurrentThreadId(); }
    int Count() { return tracks_->Length; }
    float Duration() { return duration_; }
    String^ TrackName(int i) { return tracks_[i]->Name; }
    void Sample(int i,float time,float duration,ZSGrannySample* out) {
        if(i<0 || i>=tracks_->Length || Single::IsNaN(time) || Single::IsInfinity(time) || Single::IsNaN(duration) || Single::IsInfinity(duration) ||
           time<0 || time>duration_ || duration<=0 || Math::Abs(duration-duration_)>Math::Max(1e-6f,duration_*1e-6f))
            throw gcnew ArgumentOutOfRangeException("time, duration, or track index");
        IGrannyTransformTrack^ t=tracks_[i];
        array<float>^ p=t->PositionCurve->Sample(time,duration_,false,false,false);
        array<float>^ q=t->OrientationCurve->Sample(time,duration_,true,false,false);
        array<float>^ s=t->ScaleShearCurve->Sample(time,duration_,false,false,false);
        if(p==nullptr||p->Length!=3||q==nullptr||q->Length!=4||s==nullptr||s->Length!=9) throw gcnew InvalidDataException("Sample dimension mismatch");
        for each(float v in p) if(Single::IsNaN(v)||Single::IsInfinity(v)) throw gcnew InvalidDataException("Nonfinite position sample");
        for each(float v in q) if(Single::IsNaN(v)||Single::IsInfinity(v)) throw gcnew InvalidDataException("Nonfinite orientation sample");
        for each(float v in s) if(Single::IsNaN(v)||Single::IsInfinity(v)) throw gcnew InvalidDataException("Nonfinite scale/shear sample");
        for(int n=0;n<3;++n) out->position[n]=p[n];
        for(int n=0;n<4;++n) out->orientation[n]=q[n];
        for(int n=0;n<9;++n) out->scale_shear[n]=s[n];
    }
    void ReleaseResources() {
        if(resolver_!=nullptr){AppDomain::CurrentDomain->AssemblyResolve-=resolver_;resolver_=nullptr;}
        tracks_=nullptr; modelFile_=nullptr; animationFile_=nullptr;
        if(contextAdded_){Context::Remove(context_);contextAdded_=false;}context_=nullptr;
        if(configAdded_){Context::Remove(config_);configAdded_=false;}config_=nullptr;
        if(spaceAdded_){Context::Remove(space_);spaceAdded_=false;}space_=nullptr;
    }
};

struct BridgeState { gcroot<GrannySampler^> sampler; DWORD owner; explicit BridgeState(GrannySampler^ s):sampler(s),owner(GetCurrentThreadId()){} };
static std::mutex g_mutex;
static std::unordered_map<uintptr_t,std::unique_ptr<BridgeState>> g_handles;
static uintptr_t g_next=1;
static DWORD g_owner_thread=0;
static bool g_owner_set=false;
static std::wstring g_error;
struct ZSGrannyBridge {};
static uintptr_t token(ZSGrannyBridge* h){return reinterpret_cast<uintptr_t>(h);}
static int32_t check(ZSGrannyBridge* h){if(!h)return ZS_GRANNY_INVALID_ARGUMENT;std::lock_guard<std::mutex> lock(g_mutex);auto it=g_handles.find(token(h));if(it==g_handles.end())return ZS_GRANNY_INVALID_ARGUMENT;return g_owner_set&&g_owner_thread==GetCurrentThreadId()&&it->second->owner==GetCurrentThreadId()?ZS_GRANNY_OK:ZS_GRANNY_WRONG_THREAD;}
static void set_error(Exception^ e){try{String^ text=e->ToString();pin_ptr<const wchar_t> p=PtrToStringChars(text);std::lock_guard<std::mutex> lock(g_mutex);g_error.assign(p);}catch(...){}}
static int32_t failure(Exception^ e){set_error(e);return ZS_GRANNY_FAILURE;}
static int32_t failure_native(){try{std::lock_guard<std::mutex> lock(g_mutex);g_error=L"native exception";}catch(...){}return ZS_GRANNY_FAILURE;}

extern "C" uint32_t __cdecl ZSGrannyBridge_GetAbiVersion(){return ZS_GRANNY_BRIDGE_ABI_VERSION;}
extern "C" int32_t __cdecl ZSGrannyBridge_Open(const wchar_t* gsd,const wchar_t* model,const wchar_t* animation,ZSGrannyBridge** out){
    if(out)*out=nullptr;
    GrannySampler^ sampler=nullptr;
    try{
        if(!out||!gsd||!model||!animation||!*gsd||!*model||!*animation)return ZS_GRANNY_INVALID_ARGUMENT;
        {std::lock_guard<std::mutex> lock(g_mutex);
         if(g_owner_set&&g_owner_thread!=GetCurrentThreadId())return ZS_GRANNY_WRONG_THREAD;
         if(!g_owner_set){g_owner_thread=GetCurrentThreadId();g_owner_set=true;}
         if(g_next==0||g_next>static_cast<uintptr_t>(UINTPTR_MAX-16))return ZS_GRANNY_FAILURE;}
        String^ module=Path::GetDirectoryName(Assembly::GetExecutingAssembly()->Location);
        sampler=gcnew GrannySampler(module,gcnew String(gsd),gcnew String(model),gcnew String(animation));
        std::lock_guard<std::mutex> lock(g_mutex);uintptr_t id=g_next++;g_handles.emplace(id,std::make_unique<BridgeState>(sampler));*out=reinterpret_cast<ZSGrannyBridge*>(id);g_error.clear();return ZS_GRANNY_OK;
    }catch(Exception^ e){if(sampler!=nullptr)try{sampler->ReleaseResources();}catch(...){}return failure(e);}
     catch(...){if(sampler!=nullptr)try{sampler->ReleaseResources();}catch(...){}return failure_native();}
}
extern "C" int32_t __cdecl ZSGrannyBridge_GetInfo(ZSGrannyBridge* h,uint32_t* count,float* duration){
    if(count)*count=0;if(duration)*duration=0;
    try{if(!h||!count||!duration)return ZS_GRANNY_INVALID_ARGUMENT;int32_t status=check(h);if(status)return status;
        std::lock_guard<std::mutex> lock(g_mutex);auto& s=g_handles.at(token(h))->sampler;*count=s->Count();*duration=s->Duration();return ZS_GRANNY_OK;
    }catch(Exception^ e){return failure(e);}catch(...){return failure_native();}
}
extern "C" int32_t __cdecl ZSGrannyBridge_GetTrackName(ZSGrannyBridge* h,uint32_t index,wchar_t* buffer,uint32_t capacity,uint32_t* required){
    if(required)*required=0;if(buffer&&capacity)buffer[0]=0;
    try{if(!h||!required||(!buffer&&capacity))return ZS_GRANNY_INVALID_ARGUMENT;int32_t status=check(h);if(status)return status;
        std::lock_guard<std::mutex> lock(g_mutex);auto& s=g_handles.at(token(h))->sampler;if(index>=static_cast<uint32_t>(s->Count()))return ZS_GRANNY_INVALID_ARGUMENT;
        String^ name=s->TrackName(static_cast<int>(index));uint32_t chars=static_cast<uint32_t>(name->Length+1);*required=chars;
        if(!buffer||capacity<chars)return ZS_GRANNY_BAD_VERSION_OR_SIZE;pin_ptr<const wchar_t> p=PtrToStringChars(name);wcsncpy_s(buffer,capacity,p,_TRUNCATE);return ZS_GRANNY_OK;
    }catch(Exception^ e){return failure(e);}catch(...){return failure_native();}
}
extern "C" int32_t __cdecl ZSGrannyBridge_Sample(ZSGrannyBridge* h,uint32_t index,float time,float duration,uint32_t version,uint32_t out_size,ZSGrannySample* sample){
    try{
        if(!h||!sample)return ZS_GRANNY_INVALID_ARGUMENT;
        if(out_size)ZeroMemory(sample,(std::min)(out_size,static_cast<uint32_t>(sizeof(ZSGrannySample))));
        if(out_size!=sizeof(ZSGrannySample)||version!=ZS_GRANNY_SAMPLE_VERSION)return ZS_GRANNY_BAD_VERSION_OR_SIZE;
        int32_t status=check(h);if(status)return status;
        std::lock_guard<std::mutex> lock(g_mutex);auto& s=g_handles.at(token(h))->sampler;
        sample->version=ZS_GRANNY_SAMPLE_VERSION;sample->size=sizeof(ZSGrannySample);s->Sample(static_cast<int>(index),time,duration,sample);return ZS_GRANNY_OK;
    }catch(Exception^ e){if(sample&&out_size==sizeof(ZSGrannySample))ZeroMemory(sample,sizeof(*sample));return failure(e);}
     catch(...){if(sample&&out_size==sizeof(ZSGrannySample))ZeroMemory(sample,sizeof(*sample));return failure_native();}
}
extern "C" int32_t __cdecl ZSGrannyBridge_Close(ZSGrannyBridge** ph){
    try{
        if(!ph)return ZS_GRANNY_INVALID_ARGUMENT;if(!*ph)return ZS_GRANNY_OK;
        std::unique_ptr<BridgeState> doomed;
        {std::lock_guard<std::mutex> lock(g_mutex);auto it=g_handles.find(token(*ph));if(it==g_handles.end())return ZS_GRANNY_INVALID_ARGUMENT;
         if(it->second->owner!=GetCurrentThreadId())return ZS_GRANNY_WRONG_THREAD;doomed=std::move(it->second);g_handles.erase(it);}
        doomed->sampler->ReleaseResources();*ph=nullptr;return ZS_GRANNY_OK;
    }catch(Exception^ e){return failure(e);}catch(...){return failure_native();}
}
extern "C" int32_t __cdecl ZSGrannyBridge_GetLastError(wchar_t* buffer,uint32_t capacity,uint32_t* required){
    if(required)*required=0;if(buffer&&capacity)buffer[0]=0;
    try{if(!required||(!buffer&&capacity))return ZS_GRANNY_INVALID_ARGUMENT;std::lock_guard<std::mutex> lock(g_mutex);
        uint32_t chars=static_cast<uint32_t>(g_error.size()+1);*required=chars;if(!buffer||capacity<chars)return ZS_GRANNY_BAD_VERSION_OR_SIZE;
        wcsncpy_s(buffer,capacity,g_error.c_str(),_TRUNCATE);return ZS_GRANNY_OK;
    }catch(...){return ZS_GRANNY_FAILURE;}
}
