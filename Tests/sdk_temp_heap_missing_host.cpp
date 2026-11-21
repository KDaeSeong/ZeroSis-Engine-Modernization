#include "SdkTempHeapIncludes.h"
int main() {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    // Repeat after initialization throws: failed first binding must not cache a
    // null callback, and no GameCore or game host is present in this process.
    for(int i=0;i<2;++i) {
        try { GetTempHeap();return 1; }
        catch(const std::runtime_error& e) { if(strcmp(e.what(),"Engine host must export GetTempHeap"))return 2; }
    }
    printf("MISSING_HOST|2\nPASS|2\n");return 0;
}
