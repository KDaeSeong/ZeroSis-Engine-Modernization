#include "ZeroSisLuaBorrowed.h"
struct CvCity;
extern "C" void PeerInvalidate(const void* target) { ZeroSisLuaBorrowed::Invalidate(target); }
extern "C" const void* PeerTracking() { return &ZeroSisLuaBorrowed::State(); }
extern "C" void* PeerCityRegistry() { return ZeroSisLuaBorrowed::RegistryKey<CvCity, 0>(); }
