// Included in UiPopupContext's private section; owns no process-global state.
    bool IsPrivateMenuChild() const {
        return kind_==UiPopupKind::MenuOptions || kind_==UiPopupKind::TouchHelp || kind_==UiPopupKind::MapMenu;
    }
    void EnsureMenuOptions(){
        EnsureHostMenuOptions(host_,HostMenuOptionsDirectory(),[]{return std::make_shared<UiAudioPlayback>();});
    }
    struct PrivateMenuLuaCall final {const char* name;};
    static int PrivateMenuLua(lua_State* state){
        const auto* input=static_cast<const PrivateMenuLuaCall*>(lua_touserdata(state,1));
        if(!input || !input->name)throw std::invalid_argument("Missing private menu operation");
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,input->name);
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Private menu Lua entry is absent");
        lua_call(state,0,0);return 0;
    }
    void CallPrivateMenu(const char* name){PrivateMenuLuaCall request{name};Call(&PrivateMenuLua,&request);}
    void RequirePrivateMenuOwner(){
        if(!IsPrivateMenuChild() || !externalRouting_ || faulted_)throw std::logic_error("Private menu child is outside its owner scope");
        RequireOwnedMenuPlayer();
        if(kind_==UiPopupKind::MapMenu && (!mapMenuCatalog_ || !mapMenuCatalog_->nameAvailable))throw std::logic_error("Map menu has no sealed catalog");
    }
    void RequirePrivateMenuInput(){
        RequirePrivateMenuOwner();
        if(!privateMenuInput_ || !dispatching_ || !active_ || timerState_!=TimerState::Released)
            throw std::logic_error("Menu mutation requires its original completed-input owner scope");
    }
    const UiMapMenuFile& FindMapMenuFile(const std::string& path){
        RequirePrivateMenuOwner();
        for(const auto& file:mapMenuCatalog_->files)if(file.path==path)return file;
        throw std::invalid_argument("Map path is absent from the sealed private catalog");
    }
    bool TryMenuNative(lua_State* state,const char* op,int& result){
        result=0;
        if(std::strcmp(op,"gameMenuMainMenu")==0 || std::strcmp(op,"gameMenuRestart")==0 || std::strcmp(op,"gameMenuRetire")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Game transition accepts no extra arguments");
            const bool main=std::strcmp(op,"gameMenuMainMenu")==0;
            const bool restart=std::strcmp(op,"gameMenuRestart")==0;
            if(main && (timerState_!=TimerState::Released || !gameMenuCursorToken_))throw std::logic_error("Main menu return lacks its original confirmation/cursor boundary");
            QueueGameMenuRequest(main?GameMenuRequest::Kind::MainMenu:restart?GameMenuRequest::Kind::Restart:GameMenuRequest::Kind::Retire,
                                 main?"ExitToMainMenu":restart?"Restart":"Retire");return true;
        }
        if(std::strcmp(op,"menuOptionsOpen")==0 || std::strcmp(op,"touchHelpOpen")==0 || std::strcmp(op,"mapMenuOpen")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Menu child entry accepts no extra arguments");
            const bool map=std::strcmp(op,"mapMenuOpen")==0;
            if(map && kind_==UiPopupKind::SaveMenu){
                RequireSaveMenuOwner();
                if(!saveMenuInput_ || saveMenuInputKind_!=UiInputKind::LeftClick || !active_ || !gameMenuRequests_.empty() || !saveMenuRequests_.empty())
                    throw std::logic_error("Nested map entry requires the original SaveMenu click");
                gameMenuRequests_.push_back({GameMenuRequest::Kind::OpenMapMenu,gameMenuOwner_,gameMenuTurn_,"SaveMapMenu"});return true;
            }
            const bool options=std::strcmp(op,"menuOptionsOpen")==0;
            QueueGameMenuRequest(map?GameMenuRequest::Kind::OpenMapMenu:options?GameMenuRequest::Kind::OpenMenuOptions:GameMenuRequest::Kind::OpenTouchHelp,
                                 map?"SaveMapMenu":options?"OptionsMenu_InGame":"TouchControlsMenu");return true;
        }
        if(std::strncmp(op,"menuOptions",11)==0 || std::strncmp(op,"touchHelp",9)==0){
            RequirePrivateMenuOwner();EnsureMenuOptions();
            const bool touch=std::strncmp(op,"touchHelp",9)==0;
            if(kind_!=(touch?UiPopupKind::TouchHelp:UiPopupKind::MenuOptions))throw std::logic_error("Options operation used the wrong child context");
            auto& model=*host_.menuOptions;
            if(std::strcmp(op,"menuOptionsBegin")==0){
                if(lua_gettop(state)!=1 || active_ || model.Active())throw std::logic_error("Options transaction can begin once at entry");
                model.Begin(gameMenuOwner_,gameMenuTurn_);return true;
            }
            if(std::strcmp(op,"menuOptionsGet")==0){
                if(lua_gettop(state)!=3 || lua_type(state,3)!=LUA_TBOOLEAN)throw std::invalid_argument("Options get requires key and cache flag");
                lua_pushinteger(state,model.Get(Text(state,2),lua_toboolean(state,3)!=0));result=1;return true;
            }
            if(std::strcmp(op,"menuOptionsCapability")==0){
                if(lua_gettop(state)!=2)throw std::invalid_argument("Options capability requires one key");
                lua_pushboolean(state,model.Supports(Text(state,2)));result=1;return true;
            }
            if(std::strcmp(op,"touchHelpGet")==0){
                if(lua_gettop(state)!=1)throw std::invalid_argument("Touch help get requires no arguments");
                lua_pushboolean(state,model.Committed().hideTouchHelp);result=1;return true;
            }
            RequirePrivateMenuInput();
            if(std::strcmp(op,"menuOptionsSet")==0){
                if(lua_gettop(state)!=3)throw std::invalid_argument("Options set requires key and integer value");
                model.Set(Text(state,2),Integer(state,3));return true;
            }
            if(std::strcmp(op,"touchHelpCache")==0){
                if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TBOOLEAN)throw std::invalid_argument("Touch help cache requires one boolean");
                if(!model.Active())model.Begin(gameMenuOwner_,gameMenuTurn_);
                model.Set("hideTouchHelp",lua_toboolean(state,2)?1:0);return true;
            }
            if(lua_gettop(state)!=1)throw std::invalid_argument("Options command accepts no arguments");
            if(std::strcmp(op,"menuOptionsDefaults")==0){model.ResetDefaults();return true;}
            if(std::strcmp(op,"menuOptionsCancel")==0){if(model.Active())model.Cancel(gameMenuOwner_,gameMenuTurn_);return true;}
            if(std::strcmp(op,"menuOptionsApply")==0 || std::strcmp(op,"touchHelpCommit")==0){
                try{
                    if(model.Active())model.Apply(gameMenuOwner_,gameMenuTurn_,host_.applyMenuOptions,
                        [this](const MenuOptionsValues& value){host_.menuOptionsStore->WriteAtomic(value);});
                    lua_pushboolean(state,true);lua_pushliteral(state,"");
                }catch(const std::exception& error){
                    if(model.Faulted())throw;
                    lua_pushboolean(state,false);lua_pushstring(state,error.what());
                }
                result=2;return true;
            }
            throw std::invalid_argument("Unknown private menu setting operation");
        }
        if(std::strncmp(op,"mapMenu",7)==0){
            RequirePrivateMenuOwner();if(kind_!=UiPopupKind::MapMenu)throw std::logic_error("Map operation used another context");
            if(std::strcmp(op,"mapMenuCurrent")==0){
                if(lua_gettop(state)!=1)throw std::invalid_argument("Map metadata takes no arguments");
                lua_pushlstring(state,mapMenuCatalog_->mapScript.data(),mapMenuCatalog_->mapScript.size());lua_pushinteger(state,mapMenuCatalog_->worldSize);
                lua_pushlstring(state,mapMenuCatalog_->parentContext.data(),mapMenuCatalog_->parentContext.size());result=3;return true;
            }
            if(std::strcmp(op,"mapMenuList")==0){
                if(lua_gettop(state)!=1)throw std::invalid_argument("Map list takes no arguments");
                lua_newtable(state);int index=0;
                for(const auto& file:mapMenuCatalog_->files){
                    lua_newtable(state);
                    const auto text=[state](const char* key,const std::string& value){lua_pushlstring(state,value.data(),value.size());lua_setfield(state,-2,key);};
                    text("File",file.path);text("Name",file.name);text("Description","");text("worldType",file.worldType);text("ModificationTime",file.modificationTime);
                    lua_pushinteger(state,file.width);lua_setfield(state,-2,"width");lua_pushinteger(state,file.height);lua_setfield(state,-2,"height");
                    lua_rawseti(state,-2,++index);
                }
                result=1;return true;
            }
            if(std::strcmp(op,"mapMenuNameAvailable")==0){
                if(lua_gettop(state)!=2)throw std::invalid_argument("Map name check requires one name");
                bool available=false;try{available=mapMenuCatalog_->nameAvailable(Text(state,2));}catch(const std::invalid_argument&){}
                lua_pushboolean(state,available);result=1;return true;
            }
            RequirePrivateMenuInput();
            if(!mapMenuRequests_.empty())throw std::logic_error("One map input cannot issue multiple mutations");
            std::shared_ptr<const UiMapMenuFile> expected;std::string name;
            if(std::strcmp(op,"mapMenuSave")==0){
                if(lua_gettop(state)!=3)throw std::invalid_argument("Map save requires name and exact observed path");
                name=Text(state,2);const std::string path=Text(state,3);
                if(!path.empty())expected=std::make_shared<const UiMapMenuFile>(FindMapMenuFile(path));
                else if(!mapMenuCatalog_->nameAvailable(name))throw std::invalid_argument("Unconfirmed map overwrite rejected");
            }else if(std::strcmp(op,"mapMenuDelete")==0){
                if(lua_gettop(state)!=2)throw std::invalid_argument("Map delete requires an exact observed path");
                expected=std::make_shared<const UiMapMenuFile>(FindMapMenuFile(Text(state,2)));name=expected->name;
            }else throw std::invalid_argument("Unknown map menu operation");
            const bool deleting=std::strcmp(op,"mapMenuDelete")==0;
            bool permitted=privateMenuInputKind_==UiInputKind::KeyDown && privateMenuInputKey_==VK_RETURN && !deleting && !expected;
            if(privateMenuInputKind_==UiInputKind::LeftClick &&
               ((expected && privateMenuInputId_=="Yes") || (!expected && !deleting && privateMenuInputId_=="SaveButton")))permitted=true;
            if(!permitted)throw std::logic_error("Map mutation lacks its original Save or confirmed Yes input");
            mapMenuRequests_.push_back({deleting?MapMenuRequest::Kind::Delete:expected?MapMenuRequest::Kind::Overwrite:MapMenuRequest::Kind::Save,
                                       gameMenuOwner_,gameMenuTurn_,name,std::move(expected)});return true;
        }
        return false;
    }
    std::shared_ptr<const UiMapMenuCatalog> mapMenuCatalog_;
    std::vector<MapMenuRequest> mapMenuRequests_;
    bool privateMenuInput_=false,mapMenuReady_=false;
    UiInputKind privateMenuInputKind_=UiInputKind::KeyDown;
    std::uint64_t privateMenuInputKey_=0;
    std::string privateMenuInputId_;
