#define NOMINMAX
#include "NativeMapCatalog.h"
#include <filesystem>
#include <cstdio>

using namespace ZeroSisHost;
namespace fs=std::filesystem;
static int checks=0;
static void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class F> static void Reject(F fn,const char* message){bool rejected=false;try{fn();}catch(const std::exception&){rejected=true;}Check(rejected,message);}
static std::vector<unsigned char> Read(const fs::path& path){
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Fixture read open failed");
    LARGE_INTEGER size{};if(!GetFileSizeEx(file,&size) || size.QuadPart<0 || size.QuadPart>1024*1024){CloseHandle(file);throw std::runtime_error("Fixture read size failed");}
    std::vector<unsigned char> bytes(static_cast<std::size_t>(size.QuadPart));DWORD got=0;
    const bool success=ReadFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&got,nullptr)!=FALSE;CloseHandle(file);
    if(!success || got!=bytes.size())throw std::runtime_error("Fixture read was incomplete");return bytes;
}
static void Write(const fs::path& path,const std::vector<unsigned char>& bytes,const FILETIME* stamp=nullptr){
    HANDLE file=CreateFileW(path.c_str(),GENERIC_WRITE,FILE_SHARE_READ,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Fixture write open failed");
    DWORD written=0;bool success=WriteFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)!=FALSE;
    if(stamp)success=success && SetFileTime(file,nullptr,nullptr,stamp)!=FALSE;
    success=success && FlushFileBuffers(file)!=FALSE;CloseHandle(file);
    if(!success || written!=bytes.size())throw std::runtime_error("Fixture write was incomplete");
}
static std::vector<unsigned char> Map(unsigned char mark=0){
    std::vector<unsigned char> b{12};
    const auto word=[&](std::uint32_t value){for(unsigned i=0;i<4;++i)b.push_back(static_cast<unsigned char>(value>>(8*i)));};
    word(1);word(1);b.push_back(1);word(0);
    const std::string terrain="TERRAIN_GRASS";const std::string title="Fixture";const std::string world="WORLDSIZE_DUEL";
    for(auto size:{terrain.size()+1,std::size_t(0),std::size_t(0),std::size_t(0),std::size_t(0),title.size()+1,std::size_t(0)})word(static_cast<std::uint32_t>(size));
    b.insert(b.end(),terrain.begin(),terrain.end());b.push_back(0);b.insert(b.end(),title.begin(),title.end());b.push_back(0);
    word(static_cast<std::uint32_t>(world.size()+1));b.insert(b.end(),world.begin(),world.end());b.push_back(0);
    b.insert(b.end(),8,0);b.back()=mark;return b;
}
static std::string Utf8(const fs::path& path){
    const auto w=path.wstring();const int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,w.data(),static_cast<int>(w.size()),nullptr,0,nullptr,nullptr);
    if(size<=0)throw std::runtime_error("Fixture path conversion failed");std::string out(static_cast<std::size_t>(size),'\0');
    WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,w.data(),static_cast<int>(w.size()),&out[0],size,nullptr,nullptr);return out;
}
static std::size_t Stages(const fs::path& maps){std::size_t count=0;for(const auto& entry:fs::directory_iterator(maps))if(entry.path().extension()==L".stage" || entry.path().extension()==L".recovery")++count;return count;}

int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=2)throw std::runtime_error("One owned fixture directory is required");
        const fs::path root=fs::absolute(argv[1]);if(!fs::is_directory(root) || !fs::is_empty(root))throw std::runtime_error("Fixture directory must exist and be empty");
        for(const auto* dll:{L"CvGameCoreDLL_Expansion2_x64.dll",L"CvGameCoreDLL_Expansion2.dll",L"ZeroSisHost_x64.dll",L"clr.dll",L"d3d11.dll",L"user32.dll"})
            Check(GetModuleHandleW(dll)==nullptr,"Forbidden runtime module already loaded in console fixture");
        const auto original=Map(7);const auto next=Map(9);const std::vector<unsigned char> foreign{'f','o','r','e','i','g','n'};
        const auto document=MenuMapDocument::Read(original);
        Check(document.width==1 && document.height==1 && document.worldType=="WORLDSIZE_DUEL" && document.name=="Fixture","Minimal genuine map framing did not parse");
        for(std::size_t size:{std::size_t(0),std::size_t(1),std::size_t(45),original.size()-1}){
            auto bad=original;bad.resize(size);Reject([&]{MenuMapDocument::Read(bad);},"Truncated map accepted");
        }
        auto bad=original;bad.push_back(0);Reject([&]{MenuMapDocument::Read(bad);},"Trailing map payload accepted");
        bad=original;bad[0]=11;Reject([&]{MenuMapDocument::Read(bad);},"Wrong map version accepted");
        for(const auto& name:std::vector<std::string>{"","../escape","a/b","C:\\bad","CON","con.txt","NUL","COM1","LPT9",".","..","name."," name","name ","a\nb",std::string("a\0b",3),std::string(241,'a'),std::string(1,static_cast<char>(0xff))})
            Reject([&]{NativeMapCatalog::DecodeName(name);},"Unsafe map name accepted");
        Check(NativeMapCatalog::DecodeName("valid name")==L"valid name","Valid map leaf rejected");
        const auto normal=root/L"normal";fs::create_directory(normal);Write(normal/L"foreign-original.bin",foreign);
        {
            NativeMapCatalog catalog(normal.wstring());Check(catalog.List().empty(),"Fresh map catalog is not empty");
            Reject([&]{NativeMapCatalog duplicate(normal.wstring());},"Two writers acquired the same catalog lock");
            Check(catalog.NameAvailable("Alpha"),"Fresh map leaf unavailable");
            int writers=0;
            const auto writer=[&](const std::wstring& path,const std::string& name){++writers;Check(name=="Alpha","Writer lost logical map name");Write(path,original);return true;};
            auto first=catalog.Save("Alpha",{},writer);
            Check(writers==1 && first.name=="Alpha" && first.width==1 && first.height==1 && first.bytes==original.size(),"Real save metadata differs");
            Check(Read(normal/L"Maps/Alpha.Civ5Map")==original && !catalog.NameAvailable("Alpha"),"Real save did not preserve exported bytes");
            Check(catalog.List().size()==1 && catalog.List()[0].checksum==first.checksum,"List did not observe written map");
            Reject([&]{catalog.Save("Alpha",{},writer);},"Unconfirmed overwrite accepted");Check(writers==1,"Unconfirmed overwrite called writer");
            auto second=catalog.Save("Alpha",std::make_shared<const UiMapMenuFile>(first),[&](const std::wstring& path,const std::string&){Write(path,next);return true;});
            Check(Read(normal/L"Maps/Alpha.Civ5Map")==next && second.checksum!=first.checksum && second.identity!=first.identity,"Observed overwrite did not replace the exact leaf");
            Reject([&]{catalog.Delete(first);},"Pre-overwrite stale observation deleted replacement");
            Reject([&]{catalog.Save("Alpha",std::make_shared<const UiMapMenuFile>(first),writer);},"Pre-overwrite stale observation overwrote replacement");
            Check(Read(normal/L"Maps/Alpha.Civ5Map")==next,"Rejected stale observation changed replacement bytes");
            auto changed=next;changed.back()=3;FILETIME stamp{second.timeLow,second.timeHigh};Write(normal/L"Maps/Alpha.Civ5Map",changed,&stamp);
            Reject([&]{catalog.Delete(second);},"Same identity/time changed checksum was accepted for deletion");
            Reject([&]{catalog.Save("Alpha",std::make_shared<const UiMapMenuFile>(second),writer);},"Same identity/time changed checksum was accepted for overwrite");
            Check(Read(normal/L"Maps/Alpha.Civ5Map")==changed,"Changed observation rejection lost existing data");
            auto current=catalog.List()[0];
            Reject([&]{catalog.Save("New",{},[&](const std::wstring& path,const std::string&){Write(path,{12,1});return false;});},"Failed writer was accepted");
            Reject([&]{catalog.Save("New",{},[&](const std::wstring& path,const std::string&)->bool{Write(path,{12,1});throw std::runtime_error("injected");});},"Throwing writer was accepted");
            Reject([&]{catalog.Save("New",{},[&](const std::wstring& path,const std::string&){Write(path,{12,1});return true;});},"Truncated successful writer was accepted");
            Check(catalog.NameAvailable("New") && Stages(normal/L"Maps")==0,"Failed new save left a publication or staging file");
            Reject([&]{catalog.Save("Alpha",std::make_shared<const UiMapMenuFile>(current),[&](const std::wstring& path,const std::string&){Write(path,{12,1});return false;});},"Failed overwrite was accepted");
            Check(Read(normal/L"Maps/Alpha.Civ5Map")==changed && Stages(normal/L"Maps")==0,"Failed overwrite changed the original or retained a stage");
            Write(normal/L"Maps/.map-replace.pending",foreign);
            Reject([&]{catalog.Save("Alpha",std::make_shared<const UiMapMenuFile>(current),writer);},"Foreign pending replacement was replaced");
            Check(Read(normal/L"Maps/.map-replace.pending")==foreign && Read(normal/L"Maps/Alpha.Civ5Map")==changed,"Foreign pending marker or original changed");
            Check(Stages(normal/L"Maps")==0,"Foreign pending refusal left a generated stage");
            fs::remove(normal/L"Maps/.map-replace.pending");
            Reject([&]{catalog.Save("Race",{},[&](const std::wstring& path,const std::string&){Write(path,original);Write(normal/L"Maps/Race.Civ5Map",next);return true;});},"Unobserved destination race was replaced");
            Check(Read(normal/L"Maps/Race.Civ5Map")==next && Stages(normal/L"Maps")==0,"Destination race lost foreign bytes or left a stage");
            UiMapMenuFile outside=current;outside.path=Utf8(normal/L"foreign-original.bin");outside.name="foreign-original";
            Reject([&]{catalog.Delete(outside);},"Deletion escaped the catalog leaf namespace");
            catalog.Delete(current);Check(catalog.NameAvailable("Alpha") && catalog.List().size()==1,"Exact observed deletion failed or deleted another map");
            Check(Read(normal/L"foreign-original.bin")==foreign,"Protected fixture original changed");
        }
        const auto pending=root/L"pending";fs::create_directory(pending);fs::create_directory(pending/L"Maps");Write(pending/L"Maps/.map-replace.pending",foreign);
        Reject([&]{NativeMapCatalog catalog(pending.wstring());},"Catalog resumed across an unresolved foreign replacement");
        Check(Read(pending/L"Maps/.map-replace.pending")==foreign,"Constructor changed pending recovery record");
        const auto corrupt=root/L"corrupt";fs::create_directory(corrupt);
        {
            NativeMapCatalog catalog(corrupt.wstring());Write(corrupt/L"Maps/Broken.Civ5Map",{12,1});
            Reject([&]{catalog.List();},"Catalog listed a truncated map");Check(Read(corrupt/L"Maps/Broken.Civ5Map")==std::vector<unsigned char>({12,1}),"Catalog modified a corrupt existing map");
        }
        const auto links=root/L"links";fs::create_directory(links);bool hardlinkCreated=false;DWORD hardlinkError=0;
        {
            NativeMapCatalog catalog(links.wstring());Write(links/L"Maps/Linked.Civ5Map",original);
            hardlinkCreated=CreateHardLinkW((links/L"alias.bin").c_str(),(links/L"Maps/Linked.Civ5Map").c_str(),nullptr)!=FALSE;
            if(hardlinkCreated){Reject([&]{catalog.List();},"Hardlinked map was accepted");Check(Read(links/L"alias.bin")==original,"Hardlinked original changed");}
            else hardlinkError=GetLastError();
        }
        std::printf("{\"status\":\"PASS_REAL_NATIVE_MAP_CATALOG_COMPONENT\",\"checks\":%d,\"hardlink_fixture_executed\":%s,\"hardlink_error\":%lu,\"host_executed\":false,\"sdk_loaded\":false,\"clr_loaded\":false,\"hwnd_created\":false,\"gpu_executed\":false}\n",checks,hardlinkCreated?"true":"false",static_cast<unsigned long>(hardlinkError));
        return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
