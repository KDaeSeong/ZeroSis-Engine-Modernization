"""Prepare the selected retail front-end artwork without running the game.

Only eight exact XML/Lua sources are frozen. DDS/font payloads use the existing
content-addressed UI caches. Source rectangles, styles and anchors come from the
installed XML; glyph placement keeps the existing explicitly provisional GGXML
metric convention. This is a source/CPU candidate, never retail pixel acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
OUTPUT = PROJECT / "Source/Assets/UIFrontEnd"
IDENTITIES = {
    "MainMenu.xml": (12589, "24182a32479ba935563da7fd6afaa0d8fea5f9d46f2407175893cfc4f9d4bbc3"),
    "MainMenu.lua": (9170, "ba20efc79f50b7ceeecc4a1fc6c2531ecfd64eaa06bd1dce7c0eec96b0251bc5"),
    "SinglePlayer.xml": (8115, "71a8a18f14160b144add053460cfe9e060adc2e959fd1cf04fcd6ced0f9cffc6"),
    "SinglePlayer.lua": (6331, "dec1ef86cfb0b4e414a3f28538ed96a224ef09b2632575c3062f04ec7232eacc"),
    "FrontEnd.xml": (730, "04b62bd49337f96712c74b6c0850a027055eab6fda29f3efda837d0c4443b1ae"),
    "FrontEnd.lua": (822, "2c3357645a41aa107aefd132bd99831f9d469ddabe9bdee7ea4130020c53c5e7"),
    "ExitConfirm.xml": (1510, "6d9794963c43a2df9de43974c219fb35d9423071ec1b98c8c2a24b696d09fe32"),
    "ExitConfirm.lua": (1929, "7682db382ff5e1dc104165ba1d8a787d8e64e75fb1e550f223f2bb40ef08a5ae"),
}
KEYS = {"SinglePlayerButton": 1, "ExitButton": 3, "OptionsButton": 4,
        "StartGameButton": 10, "BackButton": 11, "Yes": 20, "No": 21}
PAGES = ("MainMenu", "SinglePlayer", "ExitConfirm")


def artifact(path):
    data = Path(path).read_bytes()
    return dict(path=str(Path(path).absolute()), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def freeze_sources(game=GAME):
    result = []
    for name, expected in IDENTITIES.items():
        source = Path(game) / "Assets/UI/FrontEnd" / name
        row = artifact(source)
        if (row["bytes"], row["sha256"]) != expected:
            raise ValueError("Retail front-end source differs: " + name)
        target = PROJECT / "Source/Assets/UI/Assets/UI/FrontEnd" / name
        if target.exists() and artifact(target)["sha256"] != row["sha256"]:
            raise ValueError("Existing source snapshot differs: " + str(target))
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        if artifact(target)["sha256"] != row["sha256"]:
            raise ValueError("Front-end source readback failed")
        result.append(dict(original=row, snapshot=artifact(target)))
    return result


def packet(compiler, sprites):
    blob = bytearray(b"ZSUPIX02" + struct.pack("<6I", 1920, 1080, len(compiler.textures), len(sprites), 0, 0))
    for texture in compiler.textures:
        raw = Path(texture).relative_to(compiler.destination).as_posix().encode("utf-8")
        blob += struct.pack("<I", len(raw)) + raw
    for sprite in sprites:
        blob += struct.pack("<IQ16f", *sprite)
    return bytes(blob)


def source_tree(element, compiler, *, hover=False, counter=None):
    """Retain source nodes, resolving only dimensions and selected visibility.

    No retail callbacks or pregame-reset handlers run. Unsupported branches and
    expired promotional buttons remain outside this selected visual candidate.
    """
    from ui_pixel_scene import KINDS, pair
    counter = counter if counter is not None else [100]
    counter[0] += 1
    attrs = dict(element.attrib)
    name = attrs.get("ID", "")
    if element.tag not in KINDS:
        raise ValueError("Unsupported original front-end control: " + element.tag)
    style = compiler.styles.get(attrs.get("Style"))
    merged = {**(style.attrib if style is not None else {}), **attrs}
    raw = merged.get("Size", "1920,1080" if element.tag == "Context" else "0,0").replace(".", ",").split(",")
    if len(raw) != 2:
        raise ValueError("Invalid original size")
    width, height = [float(full if value == "Full" else value) for value, full in zip(raw, (1920, 1080))]
    hidden = attrs.get("Hidden", "0") in ("1", "True", "true")
    hidden = hidden or element.tag == "LuaContext" or "PromoButton" in name or name in ("VersionNumber", "VersionLabel")
    if element.tag == "ShowOnMouseOver": hidden = not hover
    if element.tag == "HideOnMouseOver": hidden = hover
    children = [source_tree(child, compiler, hover=hover, counter=counter) for child in element]
    if element.tag == "Box" and style is not None:
        children += [source_tree(child, compiler, hover=hover, counter=counter) for child in style]
    if element.tag == "Stack":
        visible = [child for child in children if not child["hidden"]]
        padding = float(merged.get("Padding", "0"))
        width = max((child["width"] for child in visible), default=0)
        height = sum(child["height"] for child in visible) + padding * max(0, len(visible) - 1)
    x, y = pair(merged.get("TextureOffset", "0,0"))
    resolved_attrs = dict(attrs)
    if element.tag == "Box" and style is not None:
        resolved_attrs = {key: value for key, value in merged.items() if key != "Style"}
    if "Style" in attrs and "Size" not in merged:
        resolved_attrs["Size"] = "%d,%d" % (width, height)
    node = dict(key=counter[0], id=name, kind=element.tag, attributes=resolved_attrs, sourceAttributes=attrs,
                width=width, height=height, hidden=hidden, children=children, text="",
                texture=attrs.get("Texture", ""), textureX=x, textureY=y,
                hovered=hover, buttonState="hover" if hover else "normal")
    # Every node keeps a distinct identity even when recursive descendants exist.
    node["key"] = counter[0] = counter[0] + 1
    if element.tag == "AlphaAnim":
        node["animation"] = dict(clock=0, alpha=min(1.0, max(0.0, float(attrs.get("AlphaStart", "1")))))
    return node


def write_same_or_new(path, data):
    path = Path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Refusing to replace an existing front-end asset: " + str(path))
    else:
        path.write_bytes(data)


def prepare(destination=OUTPUT, game=GAME):
    from ui_pixel_scene import Compiler
    from ui_font_profile import load_font_profile, profile_input_root
    destination = Path(destination).absolute()
    if destination != OUTPUT.absolute():
        raise ValueError("Front-end output must use its exact owned Source asset directory")
    sources = freeze_sources(game)
    destination.mkdir(parents=True, exist_ok=True)
    profile, _ = load_font_profile()
    # The shared frozen font root is reused; no retail font path is modified.
    compiler = Compiler(game, destination, context="ranking")
    compiler.font_root = profile_input_root()
    compiler.font_input_refs = {Path(row["path"]): row for row in profile["original_inputs"]} if "original_inputs" in profile else {}
    # Existing Compiler.font enforces the owned binding. Build it from the exact
    # profile inventory rather than weakening the shared renderer's validation.
    if not compiler.font_input_refs:
        compiler.font_input_refs = {path: artifact(path) for path in compiler.font_root.rglob("*") if path.is_file()}
    scenes = {}
    controls = []
    frontend = ET.parse(Path(game) / "Assets/UI/FrontEnd/FrontEnd.xml").getroot()
    tree = source_tree(frontend, compiler)
    for child in tree["children"]:
        if child["id"] == "AtlasLogo": child["texture"] = "CivilzationVAtlas.dds"
    compiler.node(tree, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
    scenes["background"] = list(compiler.sprites)
    for page in PAGES:
        compiler.sprites = list(scenes["background"])
        compiler.geometry = []; compiler.keys = set()
        element = ET.parse(Path(game) / "Assets/UI/FrontEnd" / (page + ".xml")).getroot()
        tree = source_tree(element, compiler)
        compiler.node(tree, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        scenes[page] = list(compiler.sprites)
        names = {node.get("ID"): node for node in element.iter() if node.get("ID")}
        for row in compiler.geometry:
            name = row.get("id")
            if name not in names: continue
            node = names[name]
            if node.tag not in ("GridButton", "Button") or "PromoButton" in name: continue
            bounds = row["bounds"]
            text = node.get("String", "")
            if not text:
                text = next((child.get("String") for child in node if child.tag == "Label"), "")
            controls.append(dict(page=PAGES.index(page), name=name, key=KEYS.get(name, 0), spriteKey=row["key"],
                                 bounds=bounds, text=text))
    # The stock hover decoration is shared by the selected main/single buttons.
    original = ET.parse(Path(game) / "Assets/UI/FrontEnd/MainMenu.xml").getroot()
    hover = next(node for node in original.iter() if node.get("ID") == "SinglePlayerButton").find("ShowOnMouseOver")
    compiler.sprites = []; compiler.geometry = []; compiler.keys = set()
    htree = source_tree(hover, compiler, hover=True)
    compiler.node(htree, (0, 0, 320, 45), {"Font": "TwCenMT22", "FontStyle": "Shadow"}, (0, 0, 1920, 1080))
    scenes["hover"] = list(compiler.sprites)
    # Preserve source-derived button geometry and full original glyph coverage.
    bank = bytearray(b"ZSMFE001" + struct.pack("<I", len(controls)))
    for row in controls:
        bank += struct.pack("<IQQ4f", row["page"], row["key"], row["spriteKey"], *row["bounds"])
        for field in ("name", "text"):
            raw = row[field].encode("utf-8"); bank += struct.pack("<I", len(raw)) + raw
    bank += struct.pack("<I", 3)
    for size in (20, 22, 24):
        font = compiler.font("TwCenMT%d" % size, "Shadow")
        colors = font.color_sets["Beige_Black_Alpha"].layer_colors
        bank += struct.pack("<Iii fII", size, font.line_advance, font.baseline_offset,
                            font.spacing / 2, len(font.layers), len(font.glyphs))
        for layer in font.layers:
            texture, _, _ = compiler.register_texture(destination / "textures" / layer.sheet.path.name,
                                                     layer.sheet.width, layer.sheet.height)
            rgba = colors[min(layer.order, len(colors) - 1)].rgba
            bank += struct.pack("<I4f", texture, *(value / 255 for value in rgba))
        for cp, glyph in sorted(font.glyphs.items()):
            bank += struct.pack("<I9i", cp, glyph.a, glyph.b, glyph.c, glyph.origin_x, glyph.origin_y,
                                glyph.u, glyph.v, glyph.width + font.spacing if glyph.width and glyph.height else 0,
                                glyph.height + font.spacing if glyph.width and glyph.height else 0)
    for name, sprites in scenes.items():
        write_same_or_new(destination / (name + ".packet"), packet(compiler, sprites))
    write_same_or_new(destination / "frontend.bin", bytes(bank))
    if not compiler.unchanged(): raise ValueError("Retail/cache assets changed during preparation")
    # Empty original labels can cause the shared compiler to materialize a font
    # that contributes no sprite. Remove only those exact observed generated
    # links; retain their original cache inputs and all referenced atlases.
    from menu_suite_storage import storage
    used = {Path(path) for path in compiler.textures}
    font_outputs = {Path(sheet['path']): sheet for row in compiler.font_records for sheet in row['sheets']}
    cleanup_path = PROJECT / "evidence/game_menu/original_menu_followup/frontend/unused_font_link_cleanup.json"
    cleanup_path.parent.mkdir(parents=True, exist_ok=True)
    cleanup = json.loads(cleanup_path.read_text('utf8')) if cleanup_path.exists() else []
    for path, sheet in font_outputs.items():
        if path in used: continue
        if path.parent != destination / 'textures' or path.resolve(strict=True) != path or storage.digest(path) != sheet['sha256']:
            raise ValueError('Unreferenced generated font escaped its exact owned identity')
        source = Path(sheet['source_path']);source_before = artifact(source)
        info = storage.ordinary(path)
        row = dict(path=str(path), sha256=storage.digest(path), allocated_bytes=storage.allocated(path), **storage.metadata(info))
        path.unlink()
        if artifact(source) != source_before: raise ValueError('Original font cache changed during generated-link cleanup')
        row.update(result='DELETED_ONLY_UNREFERENCED_GENERATED_FONT_LINK', protected_cache_unchanged=True)
        cleanup.append(row)
    cleanup_path.write_text(json.dumps(cleanup, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    result = dict(schema="zerosis.original_frontend.assets.v1", sources=sources,
                  styles=artifact(Path(game) / "Assets/UI/Styles.xml"), original_texture_sources=compiler.assets.records,
                  font_sources=[row for row in compiler.font_records if any(Path(sheet['path']) in used for sheet in row['sheets'])], controls=controls,
                  native_execution=False, sdk_loaded=False, retail_pixel_acceptance=False,
                  limitation="Source-derived anchors and GGXML metric candidate; unsupported routes have no hits.",
                  files=[artifact(path) for path in sorted(destination.rglob("*")) if path.is_file()])
    report = PROJECT / "evidence/game_menu/original_menu_followup/frontend/assets.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    value = prepare()
    print(json.dumps(dict(status="PASS_ORIGINAL_FRONTEND_ASSET_PREPARATION_ONLY", files=len(value["files"]),
                          controls=len(value["controls"]), native_execution=False)))
