-- Adapter for the unchanged original SaveMapMenu script. File mutations are
-- deferred until its callback has returned and the owner scope is rechecked.
if popupKind=='MapMenu' then
  local validatorInstalled=false
  local validationError
  local function files()
    local result=native('mapMenuList')
    assert(type(result)=='table','Map menu requires an immutable private catalog')
    return result
  end
  local function selected(path)
    assert(type(path)=='string','Map selection requires a catalog path')
    for _,row in ipairs(files()) do if row.File==path then return row end end
    error('Map is absent from the immutable private catalog')
  end
  local function mapSize(row)
    local world=GameInfo.Worlds[row.worldType]
    assert(world and type(world.ID)=='number','Map world type is absent from the current rules')
    return world.ID
  end
  PreGame=PreGame or {}
  PreGame.GetMapScript=function() local script=native('mapMenuCurrent');return script end
  PreGame.GetWorldSize=function() local _,size=native('mapMenuCurrent');return size end
  Modding=Modding or {}
  Modding.GetMapFiles=files
  UI.SaveMap=function(name)
    assert(type(name)=='string' and ValidateText(name),'Map name failed original input validation')
    local expected=''
    for _,row in ipairs(files()) do if row.Name==name then
      assert(expected=='','Map name is ambiguous in its private catalog');expected=row.File
    end end
    if expected=='' then assert(native('mapMenuNameAvailable',name),'Map filename already exists') end
    native('mapMenuSave',name,expected)
  end
  UI.DeleteSavedGame=function(path) selected(path);native('mapMenuDelete',path) end
  UI.GetSavedGameModificationTime=function(path) return selected(path).ModificationTime end
  UI.GetMapPreview=function(path) return {MapSize=mapSize(selected(path))} end
  ZeroSisUi.OpenMapMenu=function()
    assert(not active and contextHidden and timer==0,'Map menu is already open')
    if not validatorInstalled then
      local originalValidate,originalSave=assert(ValidateText),assert(OnSave)
      ValidateText=function(name)
        if not originalValidate(name) then validationError='Invalid map name';return false end
        for _,row in ipairs(files()) do if row.Name==name then validationError=nil;return true end end
        local valid=native('mapMenuNameAvailable',name)==true
        validationError=not valid and 'Map name is reserved, too long, or already exists' or nil
        return valid
      end
      OnSave=function()
        if not ValidateText(Controls.NameBox:GetText()) then Controls.SaveButton:SetDisabled(true);return false end
        return originalSave()
      end
      Controls.SaveButton:RegisterCallback(Mouse.eLClick,OnSave)
      validatorInstalled=true
    end
    UIManager:QueuePopup(ContextPtr,PopupPriority.SaveMapMenu)
    assert(active and not contextHidden and timer==0,'Map menu did not enter its timer-free child scope')
  end
  ZeroSisUi.CloseMapMenu=function()
    assert(active and timer==0,'Map menu is not active');OnBack()
    assert(not active and contextHidden and timer==0,'Map menu did not release its original child scope')
  end
  ZeroSisUi.RefreshMapMenu=function()
    assert(active and timer==0,'Map catalog refresh requires its active child')
    SetupFileButtonList();Controls.NameBox:ClearString();OnEditBoxChange();ZeroSisUi.FlushLayout()
  end
  ZeroSisUi.MapMenuMetadata=function()
    local script,size,parent=native('mapMenuCurrent')
    return {privateCatalogOnly=true,originalScript=true,fileCount=#files(),mapScript=script,worldSize=size,
      owner=Game.GetActivePlayer(),turn=Game.GetGameTurn(),parentContext=parent or 'GameMenu',source=layout.mapMenu,
      validationError=validationError,originalMapFormat='Civ5Map-v12-plain',campaignSave=false,nativeAcceptanceVerified=false}
  end
end
