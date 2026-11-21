"""Compile selected original desktop skin pages into an existing owned compiler.

The caller owns the single new immutable pack. This helper writes no packet,
bank, source snapshot, game setting or evidence file. Unsupported callbacks
retain key zero and are never enabled by asset restoration.
"""
from __future__ import annotations

from copy import deepcopy
import xml.etree.ElementTree as ET

from menu_frontend_assets import KEYS, PAGES, source_tree
from menu_frontend_skin import STYLE_NAMES, require


def _walk(node):
    yield node
    for child in node.get('children', []):
        yield from _walk(child)


NATIVE_DEFAULT_IMAGE_EVIDENCE = 'evidence/game_menu/frontend_windowtrim/retail_image_probe.json'


def native_default_image_region(offset, size, texture_size):
    """Retail ForgeUI <Image> without StretchMode (CivilizationV_DX11.exe 0x41bf50, 0x562900).

    StretchMode 0 copies Size into the sampled texture region, so UV spans
    TextureOffset/texture .. (TextureOffset+Size)/texture: Size pixels are drawn
    1:1 and the texture is never rescaled. Pixels outside the texture are read
    through a sampler/FTXT path that is not established; they are not drawn.
    """
    u, v = offset
    width, height = size
    texture_width, texture_height = texture_size
    require(all(type(value) in (int, float) for value in (u, v, width, height, texture_width, texture_height)) and
            u >= 0 and v >= 0 and width > 0 and height > 0 and u < texture_width and v < texture_height,
            'Native default Image region is outside its texture')
    drawn_width, drawn_height = min(width, texture_width - u), min(height, texture_height - v)
    return dict(source=(u, v, u + drawn_width, v + drawn_height), drawn_size=(drawn_width, drawn_height),
                columns_beyond_texture=width - drawn_width, rows_beyond_texture=height - drawn_height,
                texture_columns_not_drawn=texture_width - u - drawn_width,
                texture_rows_not_drawn=texture_height - v - drawn_height)


def compile_style_descriptors(compiler):
    from ui_pixel_scene import pair
    styles = []
    for name in STYLE_NAMES:
        node = compiler.styles[name]
        if name == 'GenericPullDown':
            node = compiler.styles[node.find('ButtonData/GridButton').get('Style')]
        grid = node.find('GridData')
        if grid is not None:
            node = compiler.styles[grid.get('Style')]
        attrs = node.attrib
        if 'ULSize' in attrs:
            kind = 0
            parts = [(x, y, key) for y, row in enumerate((('UL', 'UC', 'UR'), ('L', 'C', 'R'), ('LL', 'LC', 'LR'))) for x, key in enumerate(row)]
        elif 'LSize' in attrs and 'RSize' in attrs:
            kind = 1
            parts = [(x, 1, key) for x, key in enumerate(('L', 'C', 'R'))]
        elif 'UCSize' in attrs and 'LCSize' in attrs:
            kind = 2
            parts = [(1, y, key) for y, key in enumerate(('UC', 'C', 'LC'))]
        else:
            kind = 3
            parts = []
        texture, _, _ = compiler.texture(attrs['Texture'])
        width, height = pair(attrs.get('Size', '32,32'))
        step = pair(attrs.get('StateOffsetIncrement', '0,0'))
        if name == 'Button_16':
            step = (0, 32)
        pieces = []
        for x, y, key in parts:
            w, h = pair(attrs[key + 'Size'])
            u, v = pair(attrs.get(key + 'TexStart', '0,0'))
            if w and h:
                pieces.append((x, y, u, v, u + w, v + h))
        if kind == 3:
            pieces = [(1, 1, 0, 0, width, height)]
        styles.append(dict(name=name, kind=kind, texture=texture, width=width, height=height,
                           step=step, pieces=pieces))
    return styles


def _compile_skin_pages(compiler, skin, *, options_tree, options_context, image_policies, image_records):
    # Cached output records must not bypass the selected package or pack winner.
    skin.verify_texture_records(list(compiler.assets.outputs.values()))
    compiler.styles.update(skin.selected_style_elements())
    # Stock front-end nodes use original anchors, whereas the options adapter
    # owns measured x/y. Preserve the same source-anchor path as the V1 producer.
    compiler.context = 'ranking'
    # Compiler.unchanged() then protects every selected style/source as well as
    # its original base style file and the shared immutable font profile.
    for path, row in skin._pins.items():
        compiler.context_sources[type(compiler.styles_path)(path)] = row['sha256']
    sources = {}

    def original(name):
        row = skin.resolve('UI/FrontEnd/' + name)
        sources[name] = row
        compiler.context_sources[type(compiler.styles_path)(row['source']['path'])] = row['source']['sha256']
        return ET.parse(row['source']['path']).getroot()

    def source_nodes(element, *, hover=False):
        tree = source_tree(element, compiler, hover=hover)
        image_policies.clear()
        for node in _walk(tree):
            attrs = node.get('sourceAttributes', {})
            texture = attrs.get('Texture', '')
            basename = texture.replace('\\', '/').rsplit('/', 1)[-1].casefold()
            if node['kind'] != 'Image' or basename not in ('windowtrimleft.dds', 'windowtrimright.dds'):
                continue
            # The original Expansion1 XML specifies 82x396 for its own 82x395 art,
            # while the active Expansion2 image is 98x394. A retail default Image
            # samples Size pixels 1:1 (native_default_image_region): the right 16
            # texture columns are not drawn and 2 rows fall beyond the texture.
            require(attrs.get('Size') == '82,396' and attrs.get('TextureOffset', '0,0') == '0,0' and
                    'StretchMode' not in attrs and 'Sampler' not in attrs and
                    texture.startswith('Assets/DLC/Expansion/UI/Art/Controls/') and
                    (node['width'], node['height']) == (82, 396),
                    'WindowTrim whole-image candidate differs from its exact original source declaration')
            image_policies[node['key']] = dict(texture=texture, source_attributes=deepcopy(attrs))
        return tree

    compiler.sprites = []
    compiler.geometry = []
    compiler.keys = set()
    frontend = source_nodes(original('FrontEnd.xml'))
    for child in frontend['children']:
        if child['id'] == 'AtlasLogo':
            child['texture'] = 'CivilzationVAtlas.dds'
    compiler.node(frontend, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
    scenes = {'background': list(compiler.sprites)}
    controls = []
    for page in PAGES:
        compiler.sprites = list(scenes['background'])
        compiler.geometry = []
        compiler.keys = set()
        element = original(page + '.xml')
        compiler.node(source_nodes(element), (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        scenes[page] = list(compiler.sprites)
        names = {node.get('ID'): node for node in element.iter() if node.get('ID')}
        for row in compiler.geometry:
            name = row.get('id')
            if name not in names:
                continue
            node = names[name]
            if node.tag not in ('GridButton', 'Button') or 'PromoButton' in name:
                continue
            text = node.get('String', '')
            if not text:
                text = next((child.get('String') for child in node if child.tag == 'Label'), '')
            controls.append(dict(page=PAGES.index(page), name=name, key=KEYS.get(name, 0),
                                 spriteKey=row['key'], bounds=row['bounds'], text=text))
    hover_root = original('MainMenu.xml')
    button = next(node for node in hover_root.iter() if node.get('ID') == 'SinglePlayerButton')
    hover = button.find('ShowOnMouseOver')
    require(hover is not None, 'Original desktop menu hover decoration is missing')
    compiler.sprites = []
    compiler.geometry = []
    compiler.keys = set()
    compiler.node(source_nodes(hover, hover=True), (0, 0, 320, 45),
                  {'Font': 'TwCenMT22', 'FontStyle': 'Shadow'}, (0, 0, 1920, 1080))
    scenes['hover'] = list(compiler.sprites)
    options_chrome = None
    if options_tree is not None:
        image_policies.clear()
        compiler.context = options_context
        tree = deepcopy(options_tree)
        for node in _walk(tree):
            name = node.get('id', '')
            if name in ('GamePanel', 'IFacePanel', 'VideoPanel', 'AudioPanel', 'MultiplayerPanel'):
                node['hidden'] = True
            if node.get('kind') in ('Label', 'ShowOnMouseOver', 'GridButton', 'Button',
                                   'CheckBox', 'Slider', 'PullDown') or name.endswith('Highlight'):
                node['hidden'] = True
            node['text'] = ''
        compiler.sprites = []
        compiler.geometry = []
        compiler.keys = set()
        compiler.node(tree, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        options_chrome = list(compiler.sprites)
    styles = compile_style_descriptors(compiler)
    skin.verify_texture_records(list(compiler.assets.outputs.values()))
    image_api_path = skin.game_root / 'Assets/UI/InGame/Popups/WonderPopup.lua'
    image_api = skin._pin(image_api_path)
    image_api_lines = image_api_path.read_text('utf-8-sig').splitlines()
    texture_resize = [index + 1 for index, line in enumerate(image_api_lines)
                      if 'Controls.WonderSplash:SetTextureAndResize(' in line]
    independent_size = [index + 1 for index, line in enumerate(image_api_lines)
                        if 'Controls.WonderSplash:SetSizeVal(' in line]
    require(texture_resize and independent_size,
            'Original image API usage no longer supports independent draw-size evidence')
    compiler.context_sources[image_api_path] = image_api['sha256']
    provenance = skin.provenance(texture_names=sorted(compiler.assets.outputs))
    require(skin.unchanged(), 'Original active skin inputs changed during source compilation')
    return dict(scenes=scenes, controls=controls, styles=styles, options_chrome=options_chrome,
                provenance=provenance, original_sources=sources,
                original_image_size_candidates=image_records,
                image_size_source_api_evidence=dict(source=image_api,
                    SetTextureAndResize_lines=texture_resize, SetSizeVal_lines=independent_size,
                    inference='Original image scripts resize the same image after choosing its texture; '
                              'this supports independent draw dimensions, not WindowTrim UV or sampling parity.',
                    native_windowtrim_uv_or_scaling_verified=False),
                options_geometry='SHARED_RETAINED_ORIGINAL_OPTIONS_TREE_WITH_SELECTED_STYLE_OVERLAY',
                native_geometry_verified=False, host_or_sdk_or_window_executed=False)


def compile_skin_pages(compiler, skin, *, options_tree=None):
    """Return source-derived sprites/control records; never mutate an old pack."""
    previous_context = compiler.context
    original_image = compiler.image
    had_image_override = 'image' in compiler.__dict__
    image_policies = {}
    image_records = []

    def original_frontend_image(key, texture_name, u, v, bounds, clip, color, **options):
        policy = image_policies.get(key)
        if policy is not None:
            require(texture_name == policy['texture'] and (u, v) == (0, 0) and
                    bounds[2:] == (82, 396) and options.get('source_extent') is None and
                    not options.get('stretch_full_texture'),
                    'Original WindowTrim image was reused outside its source geometry')
            _, width, height = compiler.texture(texture_name)
            basename = texture_name.rsplit('/', 1)[-1].casefold()
            conversion = compiler.assets.outputs[basename]['conversion']
            require((width, height) == (98, 394) and conversion['source_scalable'] is False,
                    'Selected active WindowTrim atlas differs from its source-backed candidate')
            region = native_default_image_region((u, v), bounds[2:], (width, height))
            drawn = (bounds[0], bounds[1], *region['drawn_size'])
            original_image(key, texture_name, u, v, drawn, clip, color, **options)
            image_records.append(dict(key=key, texture=texture_name,
                source_attributes=deepcopy(policy['source_attributes']),
                source_extent=[width, height], target_bounds=list(bounds), drawn_bounds=list(drawn),
                active_texture_source=skin.texture(texture_name),
                ftxt_conversion=deepcopy(conversion), source_rectangle=list(region['source']),
                transform=dict(x_scale_numerator=1, x_scale_denominator=1, y_scale_numerator=1, y_scale_denominator=1),
                texture_columns_not_drawn=region['texture_columns_not_drawn'],
                rows_beyond_texture_not_drawn=region['rows_beyond_texture'],
                rows_beyond_texture_policy='NOT_DRAWN_RETAIL_SAMPLER_AND_FTXT_SHADER_RESULT_UNPROVEN',
                original_pixel_rows_discarded=False, source_pixel_data_modified=False,
                sampling='CURRENT_PRESENTER_SAMPLING_1TO1_RETAIL_DEFAULT_SAMPLER_INDEX_10',
                policy='ORIGINAL_DEFAULT_IMAGE_SIZE_PIXELS_1TO1_FROM_TEXTURE_OFFSET',
                native_mapping_evidence=NATIVE_DEFAULT_IMAGE_EVIDENCE,
                native_geometry_verified=False, retail_texture_stretch_verified=True,
                native_uv_and_scaling_parity_unresolved=False))
            return 'ORIGINAL_DEFAULT_IMAGE_SIZE_PIXELS_1TO1_FROM_TEXTURE_OFFSET'
        return original_image(key, texture_name, u, v, bounds, clip, color, **options)

    compiler.image = original_frontend_image
    try:
        return _compile_skin_pages(compiler, skin, options_tree=options_tree,
                                   options_context=previous_context, image_policies=image_policies,
                                   image_records=image_records)
    finally:
        compiler.context = previous_context
        if had_image_override:
            compiler.image = original_image
        else:
            del compiler.image
