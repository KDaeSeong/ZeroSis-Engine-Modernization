// Reuse only the existing bounded byte/file fixture helpers. Its broad test
// entry is renamed and never called by this one-concern executable.
#define wmain MenuMapCatalogUnusedFixtureEntry
#include "menu_map_catalog.cpp"
#undef wmain

static std::wstring Extended(const fs::path& path){return L"\\\\?\\"+path.wstring();}
static std::string Json(const std::string& text){
    std::string out="\"";for(unsigned char ch:text){
        if(ch=='\"' || ch=='\\'){out.push_back('\\');out.push_back(static_cast<char>(ch));}
        else if(ch>=32 && ch<127)out.push_back(static_cast<char>(ch));
        else out+='?';
    }return out+'\"';
}

int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=2)throw std::runtime_error("One exact owned fixture root is required");
        const auto root=fs::absolute(argv[1]);
        if(!fs::is_directory(root) || !fs::is_empty(root) || root.wstring().size()+1>=180)
            throw std::runtime_error("Long-path fixture root must be empty and shorter than 179 wchar");
        for(const auto* dll:{L"CvGameCoreDLL_Expansion2_x64.dll",L"CvGameCoreDLL_Expansion2.dll",L"clr.dll",L"d3d11.dll",L"user32.dll"})
            Check(GetModuleHandleW(dll)==nullptr,"Forbidden runtime module loaded");
        const fs::path session=root/fs::path(std::wstring(180-root.wstring().size()-1,L's'));
        if(!CreateDirectoryW(session.c_str(),nullptr))throw std::runtime_error("Cannot create exactly 180-wchar session directory");
        const std::string name(100,'A');const auto target=session/L"Maps"/fs::path(std::wstring(100,L'A')+L".Civ5Map");
        const auto bytes=Map(7);UiMapMenuFile observed;std::size_t writerLength=0;
        bool save=false,list=false,overwrite=false,remove=false,seeded=false;std::string saveError,listError,overwriteError,deleteError;
        DWORD saveWinError=0,listWinError=0,overwriteWinError=0,deleteWinError=0;
        {
            NativeMapCatalog catalog(session.wstring());
            Check(NativeMapCatalog::DecodeName(name).size()==100,"Production validator did not permit the tested name");
            try{
                observed=catalog.Save(name,{},[&](const std::wstring& stage,const std::string& actual){
                    Check(actual==name,"Long-path writer name changed");writerLength=stage.size();Write(stage,bytes);return true;
                });save=true;
            }catch(const std::exception& error){saveWinError=GetLastError();saveError=error.what();}
            if(!save){
                // Make one genuinely observed short map and move that same
                // owned file to the tested canonical long name. This isolates
                // List/Delete even if NameAvailable rejects before the writer.
                const auto shortSession=root/L"short";fs::create_directory(shortSession);
                {
                    NativeMapCatalog shortCatalog(shortSession.wstring());
                    observed=shortCatalog.Save("Reference",{},[&](const std::wstring& stage,const std::string&){Write(stage,bytes);return true;});
                }
                const auto old=fs::path(std::wstring(observed.path.begin(),observed.path.end()));
                if(!MoveFileExW(Extended(old).c_str(),Extended(target).c_str(),0))
                    throw std::runtime_error("Cannot seed independent owned long-path List/Delete fixture");
                observed.path=Utf8(target);observed.name=name;seeded=true;
            }
            Check(Read(Extended(target))==bytes,"Owned long-path map bytes differ before List/Delete");
            try{const auto entries=catalog.List();Check(entries.size()==1 && entries[0].path==Utf8(target),"Long-path List returned another map");list=true;}
            catch(const std::exception& error){listWinError=GetLastError();listError=error.what();}
            auto currentBytes=bytes;
            try{
                const auto next=Map(9);
                auto replacement=catalog.Save(name,std::make_shared<const UiMapMenuFile>(observed),
                    [&](const std::wstring& stage,const std::string& actual){
                        Check(actual==name,"Long-path overwrite writer name changed");Write(stage,next);return true;
                    });
                Check(replacement.path==Utf8(target) && replacement.name==name && replacement.checksum!=observed.checksum,
                    "Long-path overwrite changed the canonical observation or lost new bytes");
                Check(Read(Extended(target))==next,"Long-path overwrite persisted different bytes");
                observed=std::move(replacement);currentBytes=next;overwrite=true;
            }catch(const std::exception& error){overwriteWinError=GetLastError();overwriteError=error.what();}
            try{catalog.Delete(observed);remove=true;}
            catch(const std::exception& error){deleteWinError=GetLastError();deleteError=error.what();}
            if(!remove)Check(Read(Extended(target))==currentBytes,"Rejected long-path deletion changed the owned map");
        }
        const bool reproduced=!save || !list || !overwrite || !remove;
        std::printf("{\"status\":\"%s\",\"session_wchars\":%zu,\"name_wchars\":100,\"target_wchars\":%zu,\"writer_stage_wchars\":%zu,\"save\":%s,\"list\":%s,\"overwrite\":%s,\"delete\":%s,\"independent_owned_long_file_seeded\":%s,\"save_winerror\":%lu,\"list_winerror\":%lu,\"overwrite_winerror\":%lu,\"delete_winerror\":%lu,\"save_error\":%s,\"list_error\":%s,\"overwrite_error\":%s,\"delete_error\":%s,\"checks\":%d,\"host_executed\":false,\"sdk_loaded\":false,\"clr_loaded\":false,\"hwnd_created\":false,\"gpu_executed\":false}\n",
            reproduced?"REPRODUCED_NATIVE_MAP_LONG_PATH_DEFECT":"PASS_NATIVE_MAP_LONG_PATH",session.wstring().size(),target.wstring().size(),writerLength,
            save?"true":"false",list?"true":"false",overwrite?"true":"false",remove?"true":"false",seeded?"true":"false",
            static_cast<unsigned long>(saveWinError),static_cast<unsigned long>(listWinError),static_cast<unsigned long>(overwriteWinError),static_cast<unsigned long>(deleteWinError),
            Json(saveError).c_str(),Json(listError).c_str(),Json(overwriteError).c_str(),Json(deleteError).c_str(),checks);
        return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
