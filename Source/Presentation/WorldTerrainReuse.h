#pragma once
#include "WorldViewRenderer.h"
#include <cmath>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <utility>

namespace ZeroSisPresentation {

// Exact detached ground inputs. Unit poses, UI state and presentation time do
// not affect ground geometry or its integer ID pass. Keep plot order: it owns
// the index-to-key correspondence and the order of equal-depth triangles.
class WorldTerrainGroundKey final {
    struct Plot final {
        int index,x,y,continent,terrainId;
        bool revealed,visible,water,hills,mountain,naturalWonder;
        std::string terrain,feature;
        bool Matches(const WorldViewPlot& p) const noexcept {
            return index==p.index && x==p.x && y==p.y && continent==p.continent &&
                terrainId==p.terrainId && naturalWonder==p.naturalWonder &&
                revealed==p.revealed && visible==p.visible && water==p.water &&
                hills==p.hills && mountain==p.mountain && terrain==p.terrain && feature==p.feature;
        }
    };
public:
    WorldTerrainGroundKey(const WorldTerrainGroundKey&)=default;
    WorldTerrainGroundKey(WorldTerrainGroundKey&&) noexcept=default;
    WorldTerrainGroundKey& operator=(const WorldTerrainGroundKey&)=default;
    WorldTerrainGroundKey& operator=(WorldTerrainGroundKey&&) noexcept=default;
    static WorldTerrainGroundKey Capture(const WorldView& view,std::uint32_t width,
        std::uint32_t height,std::uint32_t mapWidth,std::uintptr_t device,std::uintptr_t context){
        if(!width || !height || width>4096 || height>4096 || !mapWidth || mapWidth>width ||
           view.gridWidth<=0 || view.gridHeight<=0 || view.plots.size()>500000 ||
           !std::isfinite(view.tileWidth) || view.tileWidth<WorldCameraZoom::Minimum || view.tileWidth>WorldCameraZoom::Maximum)
            throw std::invalid_argument("Invalid detached terrain cache dimensions or camera");
        WorldTerrainGroundKey key;
        key.width_=width;key.height_=height;key.mapWidth_=mapWidth;key.device_=device;key.context_=context;
        key.gridWidth_=view.gridWidth;key.gridHeight_=view.gridHeight;key.cameraX_=view.cameraX;key.cameraY_=view.cameraY;
        key.wrapX_=view.wrapX;key.wrapY_=view.wrapY;key.tileWidth_=view.tileWidth;key.package_=view.terrainAssetsPath;
        key.waterSurface_=view.waterSurfaceAssetsPath;
        key.lightingPackage_=view.lightingAssetsPath;
        if(!key.waterSurface_.empty())key.waterPackage_=view.waterAssetsPath;
        key.seed_=view.mapRandomSeed;
        key.plots_.reserve(view.plots.size());
        for(const auto& p:view.plots)key.plots_.push_back({p.index,p.x,p.y,p.continent,p.terrainId,p.revealed,p.visible,p.water,p.hills,p.mountain,p.naturalWonder,p.terrain,p.feature});
        return key;
    }
    bool Matches(const WorldView& view,std::uint32_t width,std::uint32_t height,
        std::uint32_t mapWidth,std::uintptr_t device,std::uintptr_t context) const noexcept {
        if(width_!=width || height_!=height || mapWidth_!=mapWidth || device_!=device || context_!=context ||
           seed_!=view.mapRandomSeed ||
           gridWidth_!=view.gridWidth || gridHeight_!=view.gridHeight || cameraX_!=view.cameraX || cameraY_!=view.cameraY ||
           wrapX_!=view.wrapX || wrapY_!=view.wrapY || tileWidth_!=view.tileWidth || package_!=view.terrainAssetsPath ||
           plots_.size()!=view.plots.size()||waterSurface_!=view.waterSurfaceAssetsPath||lightingPackage_!=view.lightingAssetsPath||
           (!waterSurface_.empty()&&waterPackage_!=view.waterAssetsPath))return false;
        for(std::size_t i=0;i<plots_.size();++i)if(!plots_[i].Matches(view.plots[i]))return false;
        return true;
    }
private:
    WorldTerrainGroundKey()=default;
    std::uint32_t width_=0,height_=0,mapWidth_=0,seed_=0;
    std::uintptr_t device_=0,context_=0;
    int gridWidth_=0,gridHeight_=0,cameraX_=0,cameraY_=0;
    bool wrapX_=false,wrapY_=false;float tileWidth_=0;
    std::wstring package_,waterSurface_,waterPackage_,lightingPackage_;std::vector<Plot> plots_;
};

// One render-owner entry, not an unbounded per-camera cache. Preparation and
// GPU work finish outside this object. Failed preparation/publication retains
// the old key and its owned metadata/buffers; readers never move them out.
template<class T>class WorldTerrainReuse final {
    struct Entry final {
        WorldTerrainGroundKey key;std::unique_ptr<T> value;
        Entry(WorldTerrainGroundKey&& k,std::unique_ptr<T>&& v) noexcept:key(std::move(k)),value(std::move(v)){}
    };
public:
    const T* Find(const WorldView& view,std::uint32_t width,std::uint32_t height,
        std::uint32_t mapWidth,std::uintptr_t device,std::uintptr_t context) const noexcept {
        return entry_ && entry_->key.Matches(view,width,height,mapWidth,device,context)?entry_->value.get():nullptr;
    }
    void Publish(WorldTerrainGroundKey key,std::unique_ptr<T> value){
        if(!value)throw std::invalid_argument("Terrain cache cannot publish a null candidate");
        std::unique_ptr<Entry> next(new Entry(std::move(key),std::move(value)));
        entry_.swap(next);
    }
    void Clear() noexcept {entry_.reset();}
private:
    std::unique_ptr<Entry> entry_;
};
}
