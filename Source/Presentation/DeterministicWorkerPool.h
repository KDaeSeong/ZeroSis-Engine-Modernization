#pragma once

#include <array>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>
#if defined(_M_X64) || defined(__x86_64__)
#include <xmmintrin.h>
#endif

namespace ZeroSisPresentation { namespace DeterministicParallel {

constexpr unsigned MaxWorkers=4;
constexpr std::size_t MaxIndexedJobs=8192;
constexpr std::size_t MinParallelJobs=1024;

inline unsigned ResolveWorkers(unsigned logicalCpuHint) noexcept {
    return logicalCpuHint<=1?0u:logicalCpuHint<=3?2u:4u;
}

struct Metrics {
    unsigned requestedWorkers=0,poolThreads=0,newThreads=0,workersUsed=0;
    bool serialFallback=false;
    std::size_t jobs=0,completed=0,failedIndex=MaxIndexedJobs;
    std::array<std::size_t,MaxWorkers> laneJobs{};
    std::array<std::thread::id,MaxWorkers> laneThreads{};
};

struct ThreadFactory {
    template<class Function>std::thread Start(Function function){return std::thread(std::move(function));}
};

// A synchronous owner-thread dispatch. The caller keeps all immutable inputs
// alive until Dispatch returns; no task or result pointer escapes that call.
// Threads persist between meshes, while each mesh has at most four lanes.
template<class Factory=ThreadFactory>class WorkerPool final {
public:
    using RangeFunction=void(*)(void*,unsigned,unsigned);
    struct DispatchInfo {unsigned poolThreads=0,newThreads=0;};

    explicit WorkerPool(Factory factory=Factory()):factory_(std::move(factory)),owner_(std::this_thread::get_id()){}
    WorkerPool(const WorkerPool&)=delete;
    WorkerPool& operator=(const WorkerPool&)=delete;
    ~WorkerPool(){StopAndJoin();}

    bool Dispatch(unsigned workers,RangeFunction function,void* context,DispatchInfo& info){
        if(std::this_thread::get_id()!=owner_)throw std::logic_error("Parallel preparation requires its owning thread");
        if((workers!=2&&workers!=4)||function==nullptr||context==nullptr)
            throw std::invalid_argument("Invalid bounded parallel dispatch");
        info={};
        std::unique_lock<std::mutex> lock(mutex_);
        if(disabled_)return false;
        if(busy_)throw std::logic_error("Nested parallel preparation dispatch");
        if(generation_==(std::numeric_limits<std::uint64_t>::max)())return false;
        const unsigned before=started_;
        try {
            while(started_<workers){
                const unsigned lane=started_;const auto generation=generation_;
                threads_[lane]=factory_.Start([this,lane,generation]{Worker(lane,generation);});
                if(!threads_[lane].joinable())throw std::runtime_error("Parallel thread factory returned an empty thread");
                ++started_;
            }
        }catch(...){
            info.newThreads=started_-before;
            disabled_=true;stopping_=true;
            lock.unlock();ready_.notify_all();Join();
            return false;
        }
        info.poolThreads=started_;info.newThreads=started_-before;
        active_=workers;remaining_=workers;function_=function;context_=context;busy_=true;++generation_;
        ready_.notify_all();
        try {finished_.wait(lock,[this]{return remaining_==0;});}
        catch(...){
            disabled_=true;stopping_=true;
            lock.unlock();ready_.notify_all();Join();
            throw;
        }
        // The mutex hand-off from every worker publishes its private range.
        function_=nullptr;context_=nullptr;busy_=false;
        return true;
    }

private:
    void Worker(unsigned lane,std::uint64_t observed){
        for(;;){
            std::unique_lock<std::mutex> lock(mutex_);
            ready_.wait(lock,[&]{return stopping_||generation_!=observed;});
            if(stopping_)return;
            observed=generation_;
            if(lane>=active_)continue;
            const auto function=function_;void* const context=context_;const unsigned active=active_;
            lock.unlock();function(context,lane,active);lock.lock();
            if(--remaining_==0)finished_.notify_one();
        }
    }
    void Join(){
        for(auto& thread:threads_)if(thread.joinable())thread.join();
        started_=0;
    }
    void StopAndJoin(){
        {std::lock_guard<std::mutex> lock(mutex_);stopping_=true;}
        ready_.notify_all();Join();
    }

    Factory factory_;
    const std::thread::id owner_;
    std::mutex mutex_;
    std::condition_variable ready_,finished_;
    std::array<std::thread,MaxWorkers> threads_;
    unsigned started_=0,active_=0,remaining_=0;
    std::uint64_t generation_=0;
    RangeFunction function_=nullptr;
    void* context_=nullptr;
    bool stopping_=false,disabled_=false,busy_=false;
};

namespace Detail {
struct FloatingPointScope {
#if defined(_M_X64) || defined(__x86_64__)
    unsigned previous;
    explicit FloatingPointScope(unsigned captured) noexcept:previous(_mm_getcsr()){_mm_setcsr(captured);}
    ~FloatingPointScope(){_mm_setcsr(previous);}
    static unsigned Capture() noexcept{return _mm_getcsr();}
#else
    explicit FloatingPointScope(unsigned) noexcept{}
    static unsigned Capture() noexcept{return 0;}
#endif
};
template<class Output,class Operation>struct IndexedTask {
    std::vector<Output>& output;
    const Operation& operation;
    std::array<std::exception_ptr,MaxWorkers> errors{};
    std::array<std::size_t,MaxWorkers> failed{};
    std::array<std::size_t,MaxWorkers> completed{};
    std::array<std::thread::id,MaxWorkers> threads{};
    const unsigned floatingPointControl;
    IndexedTask(std::vector<Output>& values,const Operation& work):output(values),operation(work),
        floatingPointControl(FloatingPointScope::Capture()){failed.fill(MaxIndexedJobs);}
    static void Run(void* pointer,unsigned lane,unsigned lanes) noexcept {
        auto& self=*static_cast<IndexedTask*>(pointer);
        // A persistent thread may have seen another caller rounding/FTZ mode.
        // Match this x64 caller for the whole range, then restore the worker.
        FloatingPointScope floatingPoint(self.floatingPointControl);
        self.threads[lane]=std::this_thread::get_id();
        const auto begin=self.output.size()*lane/lanes,end=self.output.size()*(lane+1)/lanes;
        for(auto index=begin;index<end;++index){
            try {self.output[index]=self.operation(index);++self.completed[lane];}
            catch(...){self.errors[lane]=std::current_exception();self.failed[lane]=index;break;}
        }
    }
};
}

// Pure operation(index) must read immutable inputs and return one owned value.
// Distinct contiguous slots have one writer; failed batches never return rows.
// Allocation/setup failures occur before dispatch. Launch failure joins any
// idle threads and recomputes the whole batch serially without partial commit.
template<class Output,class Operation,class Factory>
std::vector<Output> TransformIndexed(std::size_t count,unsigned workers,const Operation& operation,
                                    WorkerPool<Factory>& pool,Metrics* diagnostics=nullptr){
    static_assert(std::is_trivially_copyable<Output>::value,"Parallel preparation returns an owned trivial value");
    if(count>MaxIndexedJobs||(workers!=0&&workers!=2&&workers!=4))
        throw std::invalid_argument("Invalid bounded parallel preparation size or workers");
    Metrics local;Metrics& metrics=diagnostics?*diagnostics:local;metrics={};metrics.requestedWorkers=workers;metrics.jobs=count;
    std::vector<Output> output(count);
    if(count==0)return output;
    Detail::IndexedTask<Output,Operation> task(output,operation);
    if(workers!=0&&count>=MinParallelJobs){
        typename WorkerPool<Factory>::DispatchInfo info;
        if(pool.Dispatch(workers,&Detail::IndexedTask<Output,Operation>::Run,&task,info)){
            metrics.poolThreads=info.poolThreads;metrics.newThreads=info.newThreads;metrics.workersUsed=workers;
            metrics.laneJobs=task.completed;metrics.laneThreads=task.threads;
            std::size_t failed=MaxIndexedJobs;unsigned failedLane=0;
            for(unsigned lane=0;lane<workers;++lane){
                metrics.completed+=task.completed[lane];
                if(task.failed[lane]<failed){failed=task.failed[lane];failedLane=lane;}
            }
            if(failed!=MaxIndexedJobs){metrics.failedIndex=failed;std::rethrow_exception(task.errors[failedLane]);}
            return output;
        }
        metrics.newThreads=info.newThreads;metrics.serialFallback=true;
    }
    metrics.laneThreads[0]=std::this_thread::get_id();
    for(std::size_t index=0;index<count;++index){
        try {output[index]=operation(index);++metrics.completed;++metrics.laneJobs[0];}
        catch(...){metrics.failedIndex=index;throw;}
    }
    return output;
}

}}
