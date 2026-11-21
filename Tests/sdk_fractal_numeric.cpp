#include "ZeroSisLuaFractalNumeric.h"
#include <memory>
#include <limits>
#include <climits>
static unsigned observationLimit = UINT_MAX;
#define main FractalNumericPriorSuiteMain
#include "fractal_numeric_existing_suite.h"
#undef main

class NumericFractal : public CvFractal
{
public:
    using CvFractal::yieldX;
    std::uint64_t State() const
    {
        std::uint64_t hash=UINT64_C(14695981039346656037);
        const int fields[]={m_iXs,m_iYs,m_iFlags,m_iFracX,m_iFracY,m_iFracXExp,m_iFracYExp,m_iXInc,m_iYInc};
        for (int value:fields) HashWord(hash,static_cast<std::uint32_t>(value));
        for (int x=0;x<=m_iFracX;++x) for (int y=0;y<=m_iFracY;++y)
            HashWord(hash,static_cast<std::uint32_t>(m_aaiFrac[x][y]));
        return hash;
    }
};
static std::unique_ptr<NumericFractal> NewFractal(CvRandom& random,int x=5,int y=5,int grain=3,int flags=0)
{
    auto value=std::make_unique<NumericFractal>();
    value->fracInit(41,29,grain,random,flags,nullptr,x,y);
    return value;
}
static std::uint64_t Samples(CvFractal& value)
{
    std::uint64_t hash=UINT64_C(14695981039346656037);
    const int xs[]={0,1,7,20,39,40},ys[]={0,1,9,14,27,28};
    for (int x:xs) for (int y:ys) { int height=value.getHeight(x,y);CHECK(height>=0 && height<=255);HashWord(hash,static_cast<std::uint32_t>(height)); }
    for (int p:{-1,0,1,25,50,75,99,100,101}) HashWord(hash,static_cast<std::uint32_t>(value.getHeightFromPercent(p)));
    return hash;
}
static void Record(unsigned index,CvFractal& value,const CvRandom& random)
{
    std::printf("NUMERIC|%u|%016llx|%u|%u|%016llx\n",index,static_cast<unsigned long long>(Samples(value)),
        random.seed,random.calls,static_cast<unsigned long long>(random.trace));
}
static void Matrix()
{
    unsigned index=0;
    for (std::uint32_t seed:{UINT32_C(0),UINT32_C(1),UINT32_C(0xfedcba98)})
    {
        for (int x=0;x<=7;++x) for (int y=0;y<=7;++y) for (int grain:{-9,0,3,11})
            for (int flags:{0,3,8,63})
            {
                CvRandom random;random.seed=seed;auto value=NewFractal(random,x,y,grain,flags);
                Record(index++,*value,random);
            }
        for (int flags:{0,1,2,3})
        {
            CvRandom random;random.seed=seed;auto value=std::make_unique<NumericFractal>();
            const int width=(flags&1)?8:9,height=(flags&2)?8:9;
            std::vector<byte> hints(static_cast<std::size_t>(width*height));
            for (std::size_t i=0;i<hints.size();++i) hints[i]=static_cast<byte>((i*37U)&255);
            value->fracInitHinted(41,29,3,random,hints.data(),static_cast<int>(hints.size()),flags,nullptr,5,5);
            Record(index++,*value,random);
        }
        for (int exponent:{4,5,6,7})
        {
            CvRandom random;random.seed=seed;auto rifts=NewFractal(random,exponent,exponent,2,1);
            auto value=std::make_unique<NumericFractal>();
            value->fracInit(41,29,3,random,1,rifts.get(),exponent,exponent);Record(index++,*value,random);
        }
        const int weights[][2]={{1,2},{6,1},{0,0},{1,0},{0,1}};
        for (int flags:{0,1}) for (int seedCount:{3,8,18}) for (const auto& blend:weights)
        {
            CvRandom random;random.seed=seed;auto value=NewFractal(random,7,6);
            value->ridgeBuilder(random,seedCount,flags,blend[0],blend[1]);Record(index++,*value,random);
        }
    }
    std::printf("MATRIX_CASES|%u\n",index);
}

#ifndef FRACTAL_NUMERIC_ORIGINAL
template<class Function> static void RejectUnchanged(NumericFractal& value,CvRandom& random,Function function)
{
    const auto before=value.State();const auto calls=random.calls,seed=random.seed;const auto trace=random.trace;
    bool rejected=false;try { function(); } catch (const std::exception&) { rejected=true; }
    CHECK(rejected);CHECK(value.State()==before);CHECK(random.calls==calls && random.seed==seed && random.trace==trace);
}
static void Boundaries()
{
    CvRandom random;auto value=NewFractal(random);
    unsigned rejections=0;
    for (int invalid:{INT_MIN,-1,0}) for (int axis:{0,1})
    {
        RejectUnchanged(*value,random,[&]{value->fracInit(axis?41:invalid,axis?invalid:29,3,random,0,nullptr,5,5);});++rejections;
    }
    for (int invalid:{8,31,32,INT_MAX}) for (int axis:{0,1})
    {
        RejectUnchanged(*value,random,[&]{value->fracInit(41,29,3,random,0,nullptr,axis?5:invalid,axis?invalid:5);});++rejections;
    }
    byte hints[81]={};
    for (int length:{INT_MIN,-1,0,80,82,INT_MAX})
    { RejectUnchanged(*value,random,[&]{value->fracInitHinted(41,29,3,random,hints,length,0,nullptr,5,5);});++rejections; }
    auto empty=std::make_unique<NumericFractal>();auto riftsSmall=NewFractal(random,0,0);
    for (CvFractal* rifts:{static_cast<CvFractal*>(empty.get()),static_cast<CvFractal*>(riftsSmall.get()),static_cast<CvFractal*>(value.get())})
    { RejectUnchanged(*value,random,[&]{value->fracInit(41,29,3,random,1,rifts,5,5);});++rejections; }
    for (int weight:{INT_MIN,-1}) for (int axis:{0,1})
    { RejectUnchanged(*value,random,[&]{value->ridgeBuilder(random,3,0,axis?1:weight,axis?weight:2);});++rejections; }
    for (int count:{1537,INT_MAX})
    { RejectUnchanged(*value,random,[&]{value->ridgeBuilder(random,count,0,1,2);});++rejections; }
    bool rejected=false;try { empty->getHeightFromPercent(50); } catch (const std::logic_error&) { rejected=true; } CHECK(rejected);
    rejected=false;try { empty->ridgeBuilder(random,3,0,1,2); } catch (const std::logic_error&) { rejected=true; } CHECK(rejected);
    for (int exponent=0;exponent<=7;++exponent)
    {
        CvRandom a,b;auto left=NewFractal(a,exponent,exponent,INT_MIN);auto right=NewFractal(b,exponent,exponent,0);
        CHECK(left->State()==right->State());CHECK(a.seed==b.seed && a.calls==b.calls && a.trace==b.trace);
        for (int x:{INT_MIN,-999,-17,-1,0,1,17,999,INT_MAX})
        { const int result=left->yieldX(x);CHECK(result>=0 && result<(1<<exponent));CHECK((static_cast<std::int64_t>(x)-result)%(INT64_C(1)<<exponent)==0); }
    }
    CvRandom a,b;auto left=NewFractal(a,INT_MIN,-1);auto right=NewFractal(b,7,6);
    CHECK(left->State()==right->State());CHECK(a.trace==b.trace);
    value->fracInit(INT_MAX,INT_MAX,INT_MAX,random,0,nullptr,7,7);
    CHECK(value->getHeight(INT_MAX-1,INT_MAX-1)>=0);CHECK(value->getHeight(-1,0)==0);
    std::printf("REJECTIONS|%u|unchanged_state_and_rng\n",rejections);
}
static void SmallRifts()
{
    for (int x=0;x<=3;++x) for (int y=0;y<=3;++y)
    {
        CvRandom random;auto rifts=NewFractal(random,x,y,2,1);auto value=std::make_unique<NumericFractal>();
        value->fracInit(41,29,3,random,1,rifts.get(),x,y);Samples(*value);
    }
    std::puts("SMALL_RIFTS|16|bounded_wrapping");
}
static unsigned exceptionsDestroyed=0;
class CheckedException : public std::exception { public: ~CheckedException() noexcept { ++exceptionsDestroyed; } const char* what() const noexcept override { return "tracked numeric exception"; } };
static int ThrowTracked(lua_State*) { throw CheckedException(); }
static int ThrowUnknown(lua_State*) { throw 17; }
static int ThrowAllocation(lua_State*) { throw std::bad_alloc(); }
static void LuaErrors()
{
    LuaMemory memory;auto* L=Open(memory);CvLuaFractal::Register(L);
    const char* failures[]={
        "Fractal.Create(0,29,3,{})","Fractal.Create(41,-1,3,{})","Fractal.Create(41,29,3,{},8,5)",
        "Fractal.CreateRifts(41,29,3,{},Fractal.Create(41,29,3,{},0,0),5,5)",
        "a:BuildRidges(2147483647,{},1,2)","a:BuildRidges(3,{},-1,2)",
        "b=Fractal.Create(41,29,3,{},1,1);b:BuildRidges(3,{},1,2)"};
    CHECK(Script(L,"a=Fractal.Create(41,29,3,{},5,5);saved=a:GetHeight(10,10)"));
    for (const char* command:failures)
    {
        const std::string script="local ok,err=pcall(function() "+std::string(command)+" end);assert(not ok and type(err)=='string');assert(a:GetHeight(10,10)==saved)";
        CHECK(Script(L,script.c_str()));CHECK(lua_gettop(L)==1);CHECK(FLua::ms_CriticalSection.GetRecursionCount()==0);
        CHECK(Script(L,"local f=Fractal.Create(41,29,3,{});assert(f:GetHeight(50)>=0)"));
    }
    lua_pushcfunction(L,ZeroSisLuaFractalNumeric::Protected<ThrowTracked>);lua_setglobal(L,"tracked");
    lua_pushcfunction(L,ZeroSisLuaFractalNumeric::Protected<ThrowUnknown>);lua_setglobal(L,"unknown");
    lua_pushcfunction(L,ZeroSisLuaFractalNumeric::Protected<ThrowAllocation>);lua_setglobal(L,"allocation");
    CHECK(Script(L,"assert(not pcall(tracked));assert(not pcall(unknown));assert(not pcall(allocation))"));
    CHECK(exceptionsDestroyed==1);lua_close(L);CHECK(memory.blocks==0);
    std::puts("LUA_NUMERIC_ERRORS|7|retry_and_gc_pass|exception_destructed_before_lua_error");
}
#endif

static void WideBlend()
{
    unsigned comparisons=0,differences=0;
    for (std::uint32_t seed:{UINT32_C(0),UINT32_C(1),UINT32_C(0xfedcba98)}) for (int flags:{0,1})
    {
        CvRandom a,b;a.seed=b.seed=seed;auto left=NewFractal(a),right=NewFractal(b);
        left->ridgeBuilder(a,3,flags,INT_MAX,INT_MAX);right->ridgeBuilder(b,3,flags,1,1);
        const bool same=Samples(*left)==Samples(*right);++comparisons;if (!same) ++differences;
        CHECK(a.seed==b.seed && a.calls==b.calls && a.trace==b.trace);
#ifndef FRACTAL_NUMERIC_ORIGINAL
        CHECK(same);
#endif
    }
#ifdef FRACTAL_NUMERIC_ORIGINAL
    CHECK(differences>0);
#else
    CHECK(differences==0);
#endif
    std::printf("WIDE_BLEND|%u|differences=%u\n",comparisons,differences);
}
static void RetryLimit()
{
    CvRandom random;auto value=NewFractal(random,1,1);const auto state=value->State();const auto calls=random.calls;
    observationLimit=random.calls+20000;
    std::string error;try { value->ridgeBuilder(random,3,0,1,2); } catch (const std::exception& e) { error=e.what(); }
    observationLimit=UINT_MAX;CHECK(!error.empty());CHECK(value->State()==state);
#ifdef FRACTAL_NUMERIC_ORIGINAL
    CHECK(error=="numeric observation budget");CHECK(random.calls-calls==20000);
#else
    CHECK(error=="Fractal ridge placement retry budget exhausted");CHECK(random.calls-calls==2570);
#endif
    std::printf("RETRY|%u|%s|height_unchanged\n",random.calls-calls,error.c_str());
}
static int Probe(const char* mode)
{
    CvRandom random;auto value=std::make_unique<NumericFractal>();
    if (!std::strcmp(mode,"probe_zero")) value->fracInit(0,29,3,random,0,nullptr,5,5);
    else if (!std::strcmp(mode,"probe_exponent")) value->fracInit(41,29,3,random,0,nullptr,8,5);
    else if (!std::strcmp(mode,"probe_hints"))
    { auto hints=std::make_unique<byte[]>(2);hints[0]=hints[1]=123;value->fracInitHinted(41,29,3,random,hints.get(),2,0,nullptr,5,5); }
    else if (!std::strcmp(mode,"probe_rifts"))
    { auto rifts=NewFractal(random,0,0);value->fracInit(41,29,3,random,1,rifts.get(),0,0); }
    else return 3;
    std::puts("UNEXPECTED_PROBE_SUCCESS");return 4;
}
int main(int argc,char** argv)
{
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    if (argc!=2) return 1;
    FLua::SetErrorHandler(ErrorHandler);
    if (!std::strncmp(argv[1],"probe_",6)) return Probe(argv[1]);
    if (!std::strcmp(argv[1],"matrix")) Matrix();
    else if (!std::strcmp(argv[1],"math")) Mathematics();
    else if (!std::strcmp(argv[1],"wide")) WideBlend();
    else if (!std::strcmp(argv[1],"retry")) RetryLimit();
#ifndef FRACTAL_NUMERIC_ORIGINAL
    else if (!std::strcmp(argv[1],"bounds")) Boundaries();
    else if (!std::strcmp(argv[1],"small_rifts")) SmallRifts();
    else if (!std::strcmp(argv[1],"lua_errors")) LuaErrors();
#endif
    else return 1;
    std::printf("PASS|%u\n",checks);return 0;
}
