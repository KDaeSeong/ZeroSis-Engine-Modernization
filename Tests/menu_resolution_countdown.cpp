// Execute the pure timer against verbatim original Lua callback goldens.
#include "MenuResolutionCountdown.h"
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <string>
#include <vector>

using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
class Fixture final {
public:
    explicit Fixture(const wchar_t* path){
        std::ifstream stream(path,std::ios::binary);if(!stream)throw std::runtime_error("Cannot read countdown goldens");
        bytes_.assign(std::istreambuf_iterator<char>(stream),{});
        if(bytes_.size()<12 || std::memcmp(bytes_.data(),"ZSCNTD01",8))throw std::runtime_error("Countdown golden header changed");at_=8;
    }
    template<class T> T Read(){
        if(sizeof(T)>bytes_.size()-at_)throw std::runtime_error("Countdown golden fixture truncated");
        T result{};std::memcpy(&result,bytes_.data()+at_,sizeof(T));at_+=sizeof(T);return result;
    }
    std::string Name(){
        const auto count=Read<std::uint32_t>();if(count>128 || count>bytes_.size()-at_)throw std::runtime_error("Countdown golden name invalid");
        const std::string result(reinterpret_cast<const char*>(bytes_.data()+at_),count);at_+=count;return result;
    }
    bool Finished() const noexcept{return at_==bytes_.size();}
private:
    std::vector<unsigned char> bytes_;std::size_t at_=0;
};
static unsigned OriginalGoldens(const wchar_t* path,unsigned& steps,unsigned& expiries){
    Fixture input(path);const auto count=input.Read<std::uint32_t>();Check(count>0 && count<=4096,"Countdown case count invalid");
    for(unsigned index=0;index<count;++index){
        const auto name=input.Name();const auto operations=input.Read<std::uint32_t>();
        Check(operations>0 && operations<=100000,"Countdown operation count invalid");
        MenuResolutionCountdown timer;unsigned yes=0,no=0,starts=0;
        for(unsigned operation=0;operation<operations;++operation){
            const auto kind=input.Read<std::uint32_t>();const auto delta=input.Read<double>();
            switch(kind){
            case 0:timer.Start();++starts;break;
            case 1:if(timer.Advance(delta)){++no;++expiries;}break;
            case 2:timer.Stop();++yes;break;
            case 3:timer.Stop();++no;break;
            default:throw std::runtime_error("Countdown golden opcode invalid");
            }
            const auto active=input.Read<std::uint32_t>();const auto remaining=input.Read<double>(),elapsed=input.Read<double>();
            const auto display=input.Read<std::int32_t>();const auto expectedYes=input.Read<std::uint32_t>();
            const auto expectedNo=input.Read<std::uint32_t>(),expectedStarts=input.Read<std::uint32_t>();
            if(timer.Active()!=(active!=0) || timer.Remaining()!=remaining || timer.Elapsed()!=elapsed ||
               timer.DisplaySeconds()!=display || yes!=expectedYes || no!=expectedNo || starts!=expectedStarts)
                throw std::runtime_error("Verbatim original countdown state/callback mismatch: "+name+" operation "+std::to_string(operation));
            checks+=7;++steps;
        }
    }
    Check(input.Finished(),"Trailing countdown golden fixture data");return count;
}
static unsigned InvalidDeltas(){
    unsigned rejected=0;
    const double invalid[]={-1,-(std::numeric_limits<double>::min)(),-std::numeric_limits<double>::infinity(),
        std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()};
    for(bool active:{false,true})for(const auto delta:invalid){
        MenuResolutionCountdown timer;if(active){timer.Start();Check(!timer.Advance(1.25),"Premature test countdown expiry");}
        const auto remaining=timer.Remaining(),elapsed=timer.Elapsed();const auto displayed=timer.DisplaySeconds();
        bool threw=false;try{timer.Advance(delta);}catch(const std::invalid_argument&){threw=true;++rejected;}
        Check(threw && timer.Active()==active && timer.Remaining()==remaining && timer.Elapsed()==elapsed && timer.DisplaySeconds()==displayed,
            "Invalid countdown delta mutated timer or bypassed rejection");
    }
    return rejected;
}
static void OwnerBoundaries(){
    MenuResolutionCountdown timer;Check(!timer.Active() && !timer.Stop(),"Fresh countdown unexpectedly active");
    Check(!timer.Advance(1000000) && timer.Elapsed()==0,"Inactive countdown consumed elapsed time");
    timer.Start();Check(timer.Active() && timer.Remaining()==20 && timer.Elapsed()==0 && timer.DisplaySeconds()==20,"Countdown did not start at original20");
    Check(!timer.Advance(0) && timer.DisplaySeconds()==21,"Original zero-delta21 display was replaced with ceil or clamp");
    Check(!timer.Advance(-0.0) && timer.DisplaySeconds()==21,"Negative zero should remain a valid zero elapsed update");
    Check(!timer.Advance(2.5) && timer.Remaining()==17.5 && timer.Elapsed()==2.5 && timer.DisplaySeconds()==18,"Original fractional countdown display differs");
    Check(timer.Stop() && !timer.Stop() && !timer.Active() && timer.Remaining()==17.5 && timer.DisplaySeconds()==18,"Stop did not preserve inactive source timer state");
    Check(!timer.Advance(1000) && timer.Remaining()==17.5 && timer.Elapsed()==2.5,"Late inactive update changed a confirmed/cancelled timer");
    timer.Start();Check(timer.Advance(30) && !timer.Active() && timer.Remaining()==-10 && timer.Elapsed()==30 && timer.DisplaySeconds()==20,
        "Stalled owner delta was capped or expiration did not occur once");
    Check(!timer.Advance(30) && timer.Remaining()==-10 && timer.Elapsed()==30,"Expired countdown emitted another rejection");
    timer.Start();Check(timer.Active() && timer.Remaining()==20 && timer.Elapsed()==0 && timer.DisplaySeconds()==20,"Restart did not reset all transient timer state");
    Check(timer.Advance((std::numeric_limits<double>::max)()) && std::isfinite(timer.Remaining()) && std::isfinite(timer.Elapsed()),
        "Largest finite stalled delta overflowed or failed to expire");
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=2)throw std::runtime_error("Expected owned original Lua countdown goldens");
    unsigned steps=0,expiries=0;const auto cases=OriginalGoldens(argv[1],steps,expiries);const auto rejected=InvalidDeltas();OwnerBoundaries();
    std::printf("{\"status\":\"PASS_ORIGINAL_RESOLUTION_COUNTDOWN_LUA_GOLDENS_CXX14\",\"checks\":%u,\"original_lua_cases\":%u,\"original_lua_steps\":%u,\"expiry_reject_edges\":%u,\"invalid_deltas_rejected\":%u,\"zero_delta_displays21\":true,\"uncapped_stall_expiry\":true,\"native_execution\":false}\n",
        checks,cases,steps,expiries,rejected);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
