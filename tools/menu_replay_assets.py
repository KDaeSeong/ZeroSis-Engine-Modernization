"""Exact retail replay source snapshots and the bounded local SDK wire profile."""
from __future__ import annotations
import hashlib
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).absolute().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
ORIGINALS = {
    'viewerLua': ('Assets/UI/InGame/Popups/ReplayViewer.lua', 39084,
        '64141da32e031d89dbcada820c0eccd30bd0cf50bf66322a4e4955847b927379'),
    'viewerXml': ('Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml', 13444,
        'c10c832cc827dc8fcf3db0c69bf71a27f0cb21c4c140c18d794d1f90af442f6d'),
    'endGameLua': ('Assets/UI/InGame/Popups/EndGameReplay.lua', 1744,
        '8f13d0079603af9ca7f95c3a528e9b6f76f3d4dd7a749438224a5be7c123b235'),
    'endGameXml': ('Assets/UI/InGame/Popups/EndGameReplay.xml', 2110,
        '6528a8e3c5a7da1ebb2b8c8e7211e52de17482e35d4860b55768198340fabd1b'),
}
SDK_INPUTS = ('Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvReplayInfo.cpp',
    'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvReplayInfo.h',
    'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvReplayMessage.cpp',
    'Source/SDK_BNW_x64/FirePlace/include/FireWorks/FStlContainerSerialization.h',
    'Source/Providers/Streams/SdkDataStream.cpp', 'Source/Providers/Strings/SdkStringStream.cpp',
    'Source/Providers/Serialization/SdkEnumSerialization.cpp', 'Source/Providers/Serialization/SdkEnumTypes.inc')


def artifact(path):
    path = Path(path); raw = path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def freeze_replay_sources(snapshots=None,game_root=GAME):
    snapshots = Path(snapshots or PROJECT/'Source/Assets/UI')
    result = {}
    for name,(relative,size,sha) in ORIGINALS.items():
        original = Path(game_root)/relative; row = artifact(original)
        if (row['bytes'],row['sha256']) != (size,sha):
            raise ValueError('Original replay source identity changed: '+relative)
        target = snapshots/relative
        if target.exists() and artifact(target)['sha256'] != sha:
            raise ValueError('Refusing to overwrite a different replay snapshot')
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(original,target)
        frozen = artifact(target)
        if (frozen['bytes'],frozen['sha256']) != (size,sha):
            raise ValueError('Replay snapshot failed exact readback')
        result[name] = dict(original=row,frozen=frozen)
    result['sdkWireInputs'] = [artifact(PROJECT/path) for path in SDK_INPUTS]
    result['profile'] = 'BNW_LOCAL_WRITE_REPLAY_V1_MESSAGE_V2_GAME_TYPE_INT8'
    result['originalsReadOnly'] = True
    result['sdkOrGameLoaded'] = False
    return result


def replay_control_tree(sources=None):
    sources = sources or freeze_replay_sources()
    xml = Path(sources['viewerXml']['frozen']['path'])
    def node(element):
        return dict(type=element.tag,attributes=dict(element.attrib),children=[node(child) for child in element])
    tree = node(ET.fromstring(xml.read_bytes()))
    tree['replay'] = dict(profile='ORIGINAL_REPLAY_VIEWER_SOURCE_WITH_OWNED_RAW_REPLAY_MODEL_V1',
        originalLua=sources['viewerLua']['frozen'],originalXml=sources['viewerXml']['frozen'],
        sourceBytesPreserved=True,gameOrSdkRequired=False,
        terrainHistory='FINAL_TERRAIN_SAMPLE_REFERENCE_ONLY',
        territoryHistory='ACTUAL_REPLAY_MESSAGE_OWNER_AND_CITY_EVENTS',
        graphHistory='RECORDED_SPARSE_DATASET_POINTS_NO_INVENTED_SAMPLES',
        completeRetailScriptExecuted=False,wrapperFormatsSupported=False)
    return tree


def original_replay_layout(sources=None):
    """Inspect the actual sibling anchors and child offsets used by native UI."""
    sources=sources or freeze_replay_sources()
    root=ET.fromstring(Path(sources['viewerXml']['frozen']['path']).read_bytes())
    required={
        'FrontEndReplayViewer':dict(Size='960,628',Anchor='C,C',Offset='0,36',Style='Grid9DetailFive140'),
        'MainPanel':dict(Size='920,440',Anchor='C,C'),
        'MessagesPanel':dict(Offset='0,35',Size='920,405'),
        'MessageText':dict(Font='TwCenMT18',FontStyle='Base',WrapWidth='890',ColorSet='Gray_Chat'),
        'MessageText2':dict(Font='TwCenMT18',FontStyle='Base',Color0='White,120'),
        'GraphDisplay':dict(Offset='160,20',Size='720,360'),
        'ReplayMap':dict(Offset='0,0',Size='920,360'),
        'TurnSlider':dict(Anchor='C,B',Length='500',Style='Slider'),
        'PlayPauseButton':dict(Anchor='R,B',Size='150,32',Offset='10,0',Style='SmallButton'),
        'BackButton':dict(Anchor='L,C',Size='150,32',Offset='14,0',Style='SmallButton'),
    }
    inspected={}
    for key,expected in required.items():
        found=root.findall(".//*[@ID='"+key+"']")
        if len(found)!=1 or any(found[0].get(name)!=value for name,value in expected.items()):
            raise ValueError('Original replay control attributes changed: '+key)
        inspected[key]=dict(found[0].attrib)
    sibling_ids=[node.get('ID') for node in root]
    if not all(key in sibling_ids for key in ('FrontEndReplayViewer','MainPanel')):
        raise ValueError('Original replay frame/main must be root siblings')
    return dict(schema='zerosis.original_replay.source_layout.v1',original_xml=sources['viewerXml']['frozen'],
        original_lua=sources['viewerLua']['frozen'],inspected_controls=inspected,
        logical_viewport=[1920,1080],frame=[480,262,960,628],main=[500,320,920,440],
        message_viewport=[500,355,920,405],message_text=[510,355,890,405],
        graph=[660,375,720,360],map=[500,355,920,360],slider=[710,728,500,32],
        back=[519,805.5,150,32],message_order='ORIGINAL_VECTOR_ORDER_NOT_TURN_SORTED',
        original_message_bottom_spacer=63,native_execution=False,retail_pixel_parity=False)


def source_profile(sources=None):
    sources = sources or freeze_replay_sources()
    code = (PROJECT/SDK_INPUTS[0]).read_bytes().decode('latin1')
    message = (PROJECT/SDK_INPUTS[2]).read_bytes().decode('latin1')
    enums = (PROJECT/SDK_INPUTS[-1]).read_text(encoding='utf8')
    for present in ('int CvReplayInfo::REPLAY_VERSION = 1;', 'plotStatePerTurn[m_iFinalTurn] = plotState;',
                    'turnData[(*it).first - m_iInitialTurn] = (*it).second;'):
        if present not in code: raise ValueError('Local replay wire source contract changed: '+present)
    if 'return 2;' not in message or 'SDK_ENUM_BYTE(GameTypes)' not in enums:
        raise ValueError('Replay message version or byte-sized game enum changed')
    return dict(sources=sources,controlTree=replay_control_tree(sources),sourceLayout=original_replay_layout(sources),version=1,messageVersion=2,
        gameTypeBytes=1,collectionCountBytes=4,stringCountBytes=4,plotStateBytes=4,
        rawInputPreserved=True,retailWrapperSupported=False,nativeExecution=False)
