#pragma once
#include "SdkHostIncludes.h"
#include <algorithm>
#include <cstdint>
#include <functional>
#include <limits>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ZeroSisHost {
// A local UI selection stores identities only. Every SDK adapter is resolved
// afresh on the owner thread, and enumerators become inert when the binding ends.
class LocalUnitSelection final {
public:
    using ActiveOwner=std::function<bool(PlayerTypes)>;
    using Resolver=std::function<ICvUnit1*(PlayerTypes,int)>;

    void Bind(ActiveOwner activeOwner,Resolver resolver){
        RequireOwner();
        if(binding_)throw std::logic_error("Local unit selection is already bound");
        if(!activeOwner || !resolver)throw std::invalid_argument("Selection requires an active-owner check and unit resolver");
        if(epoch_==UINT64_MAX)throw std::overflow_error("Selection binding epoch exhausted");
        ++epoch_;binding_=std::make_shared<Binding>(epoch_,ownerCheck_,std::move(activeOwner),std::move(resolver));
        binding_->invalidateIdentity=[this](PlayerTypes owner,int id){Invalidate(owner,id);};
        binding_->clearSelection=[this](){Clear();ClearLast();};
        selected_.clear();hasLast_=false;dirty_=true;
    }
    // Teardown may run during constructor rollback or destruction; Unbind only
    // detaches the resolver and invalidates outstanding enumerators.
    void Unbind() noexcept {
        if(binding_){binding_->active=false;binding_->activeOwner={};binding_->resolver={};binding_->invalidateIdentity={};binding_->clearSelection={};}
        binding_.reset();selected_.clear();hasLast_=false;dirty_=true;
        if(epoch_!=UINT64_MAX)++epoch_;
    }
    bool IsBound() const noexcept{return static_cast<bool>(binding_);}
    std::uint64_t Epoch() const noexcept{return epoch_;}

    void Clear(){RequireOwner();selected_.clear();dirty_=true;}
    void ClearLast(){RequireOwner();hasLast_=false;dirty_=true;}
    void InsertSingle(PlayerTypes owner,int id,bool clear,bool toggle,bool group,bool minimalChange){
        const auto binding=RequireBinding();
        if(owner<0 || owner>=MAX_PLAYERS || id<0)throw std::invalid_argument("Invalid local selection identity");
        if(!binding->activeOwner(owner))throw std::logic_error("Selection owner is not the active human turn");
        if(!clear || toggle || group || minimalChange)
            throw std::logic_error("Only a clearing, single-unit selection is supported");
        std::unique_ptr<ICvUnit1> unit(binding->resolver(owner,id));
        if(!unit || unit->GetOwner()!=owner || unit->GetID()!=id || unit->IsDelayedDeathExported())
            throw std::invalid_argument("Selection target is missing, stale, or not owned by the active player");
        selected_.assign(1,Identity{owner,id});dirty_=true;
    }
    bool Remove(PlayerTypes owner,int id){
        RequireOwner();
        for(auto it=selected_.begin();it!=selected_.end();++it)if(it->owner==owner && it->id==id){
            selected_.erase(it);if(hasLast_ && last_.owner==owner && last_.id==id)hasLast_=false;dirty_=true;return true;
        }
        return false;
    }
    ICvUnit1* Head(){RequireOwner();return Resolve(selected_.empty()?nullptr:&selected_.front());}
    ICvUnit1* Last(){RequireOwner();return hasLast_?Resolve(&last_):nullptr;}
    void SetLast(PlayerTypes owner,int id){
        const auto binding=RequireBinding();
        if(owner<0 || owner>=MAX_PLAYERS || id<0)throw std::invalid_argument("Invalid last-unit identity");
        if(!binding->activeOwner(owner))throw std::logic_error("Last unit is not owned by the active human turn");
        std::unique_ptr<ICvUnit1> unit(binding->resolver(owner,id));
        if(!unit || unit->GetOwner()!=owner || unit->GetID()!=id || unit->IsDelayedDeathExported())
            throw std::invalid_argument("Last unit is missing or stale");
        const Identity identity{owner,id};
        last_=identity;hasLast_=true;dirty_=true;
    }
    bool IsSelected(PlayerTypes owner,int id){
        RequireOwner();
        for(const auto& item:selected_)if(item.owner==owner && item.id==id){std::unique_ptr<ICvUnit1> unit(Resolve(&item));return static_cast<bool>(unit);}
        return false;
    }
    int Length(){RequireOwner();Prune();return static_cast<int>(selected_.size());}
    std::vector<std::pair<PlayerTypes,int>> Snapshot(){
        RequireOwner();Prune();std::vector<std::pair<PlayerTypes,int>> result;result.reserve(selected_.size());
        for(const auto& item:selected_)result.emplace_back(item.owner,item.id);return result;
    }
    ICvEnumerator* CreateEnumerator();
    bool Dirty() const {RequireOwner();return dirty_;}
    void MarkDirty(){RequireOwner();dirty_=true;}
    void MarkClean(){RequireOwner();dirty_=false;}

private:
    struct Identity{PlayerTypes owner;int id;};
    struct Binding{Binding(std::uint64_t value,std::function<bool()> owner,ActiveOwner active,Resolver get):epoch(value),ownerCheck(std::move(owner)),activeOwner(std::move(active)),resolver(std::move(get)){}
        std::uint64_t epoch;std::function<bool()> ownerCheck;ActiveOwner activeOwner;Resolver resolver;
        std::function<void(PlayerTypes,int)> invalidateIdentity;std::function<void()> clearSelection;bool active=true;};
    std::shared_ptr<Binding> RequireBinding(){RequireOwner();if(!binding_)throw std::logic_error("Selection input is not bound");return binding_;}
    void RequireOwner() const {
        if(!ownerCheck_ || !ownerCheck_())throw std::logic_error("Selection access requires the GameCore owner lock");
    }
    ICvUnit1* Resolve(const Identity* identity){
        RequireOwner();if(!identity)return nullptr;
        auto binding=binding_;if(!binding || !binding->active)return nullptr;
        if(!binding->activeOwner(identity->owner)){Clear();ClearLast();return nullptr;}
        std::unique_ptr<ICvUnit1> unit(binding->resolver(identity->owner,identity->id));
        if(!unit)return InvalidateAndNull(identity->owner,identity->id);
        if(unit->GetID()!=identity->id || unit->GetOwner()!=identity->owner || unit->IsDelayedDeathExported()){
            return InvalidateAndNull(identity->owner,identity->id);
        }
        return unit.release();
    }
    ICvUnit1* InvalidateAndNull(PlayerTypes owner,int id){Invalidate(owner,id);return nullptr;}
    void Invalidate(PlayerTypes owner,int id){
        selected_.erase(std::remove_if(selected_.begin(),selected_.end(),[&](const Identity& value){return value.owner==owner && value.id==id;}),selected_.end());
        if(hasLast_ && last_.owner==owner && last_.id==id)hasLast_=false;dirty_=true;
    }
    void Prune(){RequireOwner();if(selected_.empty())return;std::unique_ptr<ICvUnit1> unit(Resolve(&selected_.front()));}
    friend class LocalSelectionEnumerator;
public:
    void SetOwnerCheck(std::function<bool()> check){if(binding_)throw std::logic_error("Cannot change selection owner check while bound");ownerCheck_=std::move(check);}
private:
    std::function<bool()> ownerCheck_;
    std::shared_ptr<Binding> binding_;
    std::uint64_t epoch_=0;
    std::vector<Identity> selected_;
    Identity last_{static_cast<PlayerTypes>(NO_PLAYER),-1};
    bool hasLast_=false;
    bool dirty_=false;
};

class LocalSelectionEnumerator final:public ICvEnumerator {
public:
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* pointer) noexcept {::operator delete(pointer);}
    LocalSelectionEnumerator(std::weak_ptr<LocalUnitSelection::Binding> binding,std::vector<std::pair<PlayerTypes,int>> ids,std::uint64_t epoch)
        :binding_(std::move(binding)),ids_(std::move(ids)),epoch_(epoch){}
    void* DLLCALL QueryInterface(GUID id) override {
        if(id!=guidICvUnknown && id!=guidICvEnumerator)return nullptr;
        if(refCount_==UINT_MAX)throw std::overflow_error("Selection enumerator reference count overflow");
        ++refCount_;return static_cast<ICvEnumerator*>(this);
    }
    void DLLCALL Destroy() override {if(--refCount_==0)delete this;}
    bool DLLCALL MoveNext() override {
        const auto binding=binding_.lock();if(!IsLive(binding))return false;RequireLiveOwner(binding);
        if(index_+1>=ids_.size()){index_=ids_.size();return false;}++index_;return true;
    }
    void DLLCALL Reset() override {
        const auto binding=binding_.lock();if(!IsLive(binding))return;RequireLiveOwner(binding);index_=static_cast<std::size_t>(-1);
    }
    ICvUnknown* DLLCALL GetCurrent() override {
        auto binding=binding_.lock();if(!IsLive(binding) || index_>=ids_.size())return nullptr;
        RequireLiveOwner(binding);
        const auto value=ids_[index_];
        if(!binding->activeOwner(value.first)){binding->clearSelection();return nullptr;}
        std::unique_ptr<ICvUnit1> unit(binding->resolver(value.first,value.second));
        if(!unit){binding->invalidateIdentity(value.first,value.second);return nullptr;}
        if(unit->GetOwner()!=value.first || unit->GetID()!=value.second || unit->IsDelayedDeathExported()){
            binding->invalidateIdentity(value.first,value.second);
            return nullptr;
        }
        return unit.release();
    }
private:
    bool IsLive(const std::shared_ptr<LocalUnitSelection::Binding>& binding) const {return binding && binding->active && binding->epoch==epoch_;}
    bool IsLive() const {return IsLive(binding_.lock());}
    static void RequireLiveOwner(const std::shared_ptr<LocalUnitSelection::Binding>& binding){
        if(!binding->ownerCheck || !binding->ownerCheck())throw std::logic_error("Selection enumeration requires the GameCore owner lock");
    }
    std::weak_ptr<LocalUnitSelection::Binding> binding_;
    std::vector<std::pair<PlayerTypes,int>> ids_;
    std::uint64_t epoch_;
    std::size_t index_=static_cast<std::size_t>(-1);
    unsigned refCount_=1;
};

inline ICvEnumerator* LocalUnitSelection::CreateEnumerator(){
    RequireOwner();auto ids=Snapshot();return new LocalSelectionEnumerator(binding_,std::move(ids),epoch_);
}
}
