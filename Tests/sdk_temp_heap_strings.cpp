// The archive's FString host exports use executable linkage, while TempHeap
// calls in this test deliberately use the DLL-facing C++ binding contract.
#undef FXS_IS_DLL
#include "sdk_stream_reference_host.cpp"
