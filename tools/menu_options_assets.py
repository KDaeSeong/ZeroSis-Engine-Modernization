"""Small exact-source inventory for private options and original touch help.

No window, game module, retail configuration, textures or saves are opened.
The complete retail XML is preserved. Options runtime is an honest supported
subset adapter; the 133-function retail OptionsManager surface is not emulated.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

from civ5_ui_assets import (MENU_SOURCE_IDENTITIES as SOURCE_IDENTITIES,
    MENU_SUPPORTED_ORIGINAL_HANDLERS as SUPPORTED_ORIGINAL_HANDLERS,
    supported_original_menu_handlers as supported_original_handlers,
    menu_slider_style, menu_source_artifact as artifact, menu_original_sources as original_sources)

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
LAYOUTS = (("MenuOptionsLayout", SOURCE_IDENTITIES["optionsXml"][0], "MenuOptions"),
           ("TouchHelpLayout", SOURCE_IDENTITIES["touchXml"][0], "TouchHelp"))
PRIVATE_KEYS = ("noBasicHelp", "hideTouchHelp", "uiCueVolumePercent", "windowWidth",
                "windowHeight", "fullscreen", "vsync", "policyInfo", "noRewardPopups")










def freeze_menu_sources(snapshots=None, game_root=GAME) -> dict:
    snapshots = Path(snapshots or PROJECT / "Source/Assets/UI")
    originals = original_sources(game_root)
    result = {}
    for key, (relative, _, _) in SOURCE_IDENTITIES.items():
        target = snapshots / relative
        if target.exists() and artifact(target)["sha256"] != originals[key]["sha256"]:
            raise ValueError("Frozen menu source differs; refusing replacement: " + str(target))
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(game_root) / relative, target)
        record = artifact(target)
        if (record["bytes"], record["sha256"]) != (originals[key]["bytes"], originals[key]["sha256"]):
            raise ValueError("Frozen menu source failed exact readback: " + str(target))
        result[key] = {"original": originals[key], "snapshot": record}
    if original_sources(game_root) != originals:
        raise ValueError("Installed menu sources changed during read-only capture")
    return result


def menu_options_control_tree(element, kind: str, game_root=GAME) -> dict:
    from prepare_ui_popup_assets import KINDS
    def control_tree(node):
        # Sliders retain their exact source declaration. Only an explicitly
        # supported slider may gain a real shared input/renderer implementation.
        if node.tag not in KINDS and node.tag != "Slider":
            raise ValueError("Unexpected original menu element: " + node.tag)
        if node.text and node.text.strip():
            raise ValueError("Unexpected menu mixed XML content")
        return {"kind": node.tag, "attributes": dict(node.attrib),
                "children": [control_tree(child) for child in node]}
    if kind not in ("MenuOptions", "TouchHelp"):
        raise ValueError("Unknown menu child kind")
    sources = original_sources(game_root)
    prefix = "options" if kind == "MenuOptions" else "touch"
    original = ET.parse(Path(sources[prefix + "Xml"]["path"])).getroot()
    tree = control_tree(element)
    if tree != control_tree(original):
        raise ValueError("Menu child must retain every original XML node, attribute and child order")
    lua = Path(sources["optionsLua"]["path"]).read_text(encoding="utf-8-sig")
    lua = re.sub(r"--\[\[.*?\]\]", "", lua, flags=re.DOTALL)
    lua = "\n".join(line.split("--", 1)[0] for line in lua.splitlines())
    surface = sorted(set(re.findall(r"OptionsManager\.([A-Za-z_][A-Za-z0-9_]*)", lua)))
    if len(surface) != 133:
        raise ValueError("Retail OptionsManager source surface changed")
    tree.update(contextName="OptionsMenu_InGame" if kind == "MenuOptions" else "TouchControlsMenu",
                popupKind=kind)
    tree["menuOptions"] = {
        "profile": "HOST_SUPPORTED_OPTIONS_SUBSET_V1" if kind == "MenuOptions" else "ORIGINAL_TOUCH_HELP_V1",
        "originalLua": sources[prefix + "Lua"], "originalXml": sources[prefix + "Xml"],
        "completeOriginalXmlRetained": True, "retailOptionsLuaExecuted": False,
        "originalTouchLuaExecuted": kind == "TouchHelp",
        "retailWidgetGeometryVerified": False, "nativeDisplayVerified": False,
        "omittedStackGrowth": "Bottom",
        "derivedControlPolicy": "HOST_MENU_ADAPTER_V1",
        "privateSettingsSchema": "ZEROSIS_PRIVATE_MENU_OPTIONS_V3",
        "readablePrivateSettingsSchemas": ["ZEROSIS_PRIVATE_MENU_OPTIONS_V1", "ZEROSIS_PRIVATE_MENU_OPTIONS_V2", "ZEROSIS_PRIVATE_MENU_OPTIONS_V3"],
        "privateSettingsMigration": "V1/V2 reads preserve exact bytes and supply noRewardPopups=false in memory; V1 policyInfo retains its actual legacy seed; only explicitly changed successful commits atomically publish V3 with appended noRewardPopups; unknown/corrupt bytes preserved",
        "privateSettingsBasename": "menu-options.zssettings", "privateKeys": list(PRIVATE_KEYS),
        "retailSettingsWritten": False, "saveContractChanged": False,
        "retailOptionApiSurface": surface,
        "retailOptionApiSurfaceCount": len(surface),
        "originalSupportedHandlers": supported_original_handlers(game_root) if kind == "MenuOptions" else None,
        "sliderStyle": menu_slider_style(game_root) if kind == "MenuOptions" else None,
        "policyInfoScope": "actual original SocialPolicy description display; one canonical private Host transaction",
        "noRewardPopupsScope": "Host preference published to existing SDK popup/notification selection only after successful private persistence; cached edits and display previews never publish the draft; reward rules unchanged",
        "unsupportedCategories": [
            "retail graphics quality, texture decode, antialiasing and exclusive display mode",
            "retail music, speech and ambience audio engines",
            "SDK/player options, automated workers, quick combat/movement, auto-end-turn and autosaves",
            "retail UI size/language/tutorial/mouse/map camera settings",
            "SMTP/email, Steam, multiplayer and LAN preferences",
        ],
        "uiCueVolumeScope": ["AS2D_INTERFACE_BUY_TILE", "AS2D_INTERFACE_CITY_SCREEN_PURCHASE",
                             "AS2D_INTERFACE_FAITH_PURCHASE", "AS2D_INTERFACE_POLICY"],
        "fullscreenScope": "host borderless window; no retail exclusive display mode",
        "resolutionScope": "host client size; retained scene logical viewport stays 1920x1080",
    }
    if kind != "MenuOptions":
        tree["menuOptions"].pop("originalSupportedHandlers")
        tree["menuOptions"].pop("sliderStyle")
    return tree


def menu_checkbox_defaults(tree: dict, snapshots=None) -> dict:
    """Disclose a stock Button_16 candidate, rather than invent retail geometry."""
    from prepare_ui_popup_assets import STYLE_SOURCE, freeze_source
    snapshots = Path(snapshots or PROJECT / "Source/Assets/UI")
    source, frozen = freeze_source(STYLE_SOURCE, snapshots)
    style = ET.parse(frozen).getroot().find("Button_16")
    if style is None or style.get("Size") != "32,32" or style.get("Texture") != "Assets/UI/Art/Controls/Checkbox.dds":
        raise ValueError("Original menu checkbox style candidate changed")
    result = {}
    def visit(node):
        if node["kind"] == "CheckBox":
            control_id = node["attributes"].get("ID")
            if not control_id:
                raise ValueError("Menu checkbox has no original ID")
            result[control_id] = {"policy": "MENU_BUTTON_16_DEFAULT_CANDIDATE_V1", "style": "Button_16",
                "width": 32, "height": 32, "frameCount": 4,
                "texture": style.get("Texture"), "source": artifact(source),
                "sourceStyleAttributes": {"Texture": style.get("Texture"), "Size": style.get("Size")},
                "controlSourceAttributes": dict(node["attributes"]),
                "retailWidgetGeometryVerified": False, "defaultBindingVerified": False}
        for child in node["children"]:
            visit(child)
    visit(tree)
    return result
