#pragma once
#include <atomic>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>

namespace ZeroSisHost {
struct MapFrame {
    MapFrame(std::uint64_t epoch,std::size_t count):generation(epoch),dirtyPlots(count,1){}
    const std::uint64_t generation;
    // Every tile in a newly published map needs a complete presentation refresh.
    const std::vector<unsigned char> dirtyPlots;
};
class MapSurface {
public:
    std::shared_ptr<const MapFrame> Snapshot() const noexcept {return std::atomic_load(&current_);}
    void Setup(int count) {
        if(count<0)throw std::invalid_argument("Negative map plot count");
        std::lock_guard<std::mutex> guard(mutation_);
        if(generation_==(std::numeric_limits<std::uint64_t>::max)())throw std::overflow_error("Map generation exhausted");
        // Prepare every allocation before publishing or incrementing the generation.
        std::shared_ptr<const MapFrame> next=std::make_shared<MapFrame>(generation_+1,static_cast<std::size_t>(count));
        std::atomic_store(&current_,std::move(next));++generation_;
    }
    void Clear() {
        std::lock_guard<std::mutex> guard(mutation_);
        std::atomic_store(&current_,std::shared_ptr<const MapFrame>());
    }
private:
    std::mutex mutation_;
    std::shared_ptr<const MapFrame> current_;
    std::uint64_t generation_=0;
};
}
