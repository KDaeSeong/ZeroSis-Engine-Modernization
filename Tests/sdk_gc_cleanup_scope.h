#pragma once
#include "ZeroSisHostBinding.h"
#include "ZeroSisGlobalsLifecycle.h"

// Older component fixtures create partial owners directly. Adopt that synthetic
// state into the real lifecycle before executing the exact current GC cleanup.
// No actual GC initialization or transitive child lifecycle is implied.
template<class Globals, class Host>
void RunInstrumentedCleanup(Globals& globals, Host* host) {
    ZeroSisHostBinding::Lease lease(ZeroSisHostBinding::ProcessGate());
    if(!lease) throw std::logic_error("Cleanup fixture lifecycle is busy");
    auto& state=ZeroSisGlobalsLifecycle::ProcessState();
    state.Initialize(&globals,[&] { if(host) state.EnterHost(host); },[] {});
    state.Uninitialize(&globals,[&] { globals.uninit(); });
}
