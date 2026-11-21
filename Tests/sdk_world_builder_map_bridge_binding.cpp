// Test-only service binding. All actual I/O is performed by the observed memory
// transport; this is not a production filesystem provider or GameCore host.
#include "sdk_world_builder_map_file_host.h"
FIFileSystem* FIFileSystem::ms_pInstance=NULL;
FIFileSystem& FIFileSystem::GetInstance(){if(!ms_pInstance)throw std::logic_error("Test map filesystem is not installed");return *ms_pInstance;}
void FIFileSystem::SetInstance(FIFileSystem* instance){ms_pInstance=instance;}
