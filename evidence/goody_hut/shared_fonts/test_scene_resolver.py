"""Exercise the exact UiScene shared-font resolver with two synthetic glyphs.

This isolated Lua 5.1 boundary check never loads the complete scene or actual
font maps. Whole-source font preservation and native acceptance remain separate.
Only the fixed pure-Lua DLL and a fresh, explicitly named stage JSON are allowed.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
SCOPE = STAGE / 'scope.json'
SCENE = PROJECT / 'Source/Host/UiScene.lua'
PROVIDER = PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
SCOPE_SHA = '6c8037ff518356c3da0352075f36ee2f6c9ef7240ec86a41d25faced19152819'
SCENE_SHA = '260bfd3166bbaef43008cc928e72781b8c5595125b82a2afca0e0c705c5de3d7'
LUA_SHA = '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944'
INSTRUCTION_LIMIT = 8_000_000
SYMBOLS = {'luaL_newstate', 'luaL_openlibs', 'luaL_loadbuffer', 'lua_pcall', 'lua_tolstring', 'lua_close'}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def ordinary_path(path, *, fresh=False):
    path = Path(os.path.abspath(path))
    for index, ancestor in enumerate((path, *path.parents)):
        try:
            row = ancestor.lstat()
        except FileNotFoundError:
            require(fresh and index == 0, 'Missing input or output ancestor: ' + str(ancestor))
            continue
        require(not (fresh and index == 0), 'Output already exists: ' + str(path))
        require(not stat.S_ISLNK(row.st_mode) and not getattr(row, 'st_file_attributes', 0) & 0x400,
                'Reparse paths are forbidden: ' + str(ancestor))
        if index:
            require(stat.S_ISDIR(row.st_mode), 'Non-directory input ancestor')
    return path


def read_sealed(path, limit):
    path = ordinary_path(path)
    before = path.stat()
    identity = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns,
                            getattr(row, 'st_file_attributes', 0))
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'Input exceeds its ordinary-file bound')
    with path.open('rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Input changed while opening')
        raw = stream.read(limit + 1)
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Input changed while reading')
    require(identity(path.stat()) == identity(before) and len(raw) == before.st_size, 'Input path changed while reading')
    return raw, {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


class Boundary:
    def __init__(self, output):
        self.output = output
        self.reads = {key(path) for path in (SCOPE, SCENE, PROVIDER, Path(__file__).absolute())}
        self.denied = []
        self.loads = []
        self.symbols = []
        self.library = None
        self.output_ready = False
        self.output_opens = 0
        self.states_created = self.states_closed = 0
        self.chunks_loaded = self.chunks_called = 0

    def deny(self, event, message):
        self.denied.append(event)
        raise RuntimeError(message)

    def audit(self, event, arguments):
        if event == 'open':
            if not arguments or not isinstance(arguments[0], (str, bytes, os.PathLike)):
                self.deny(event, 'Unscoped file descriptors are forbidden')
            target = key(os.fsdecode(arguments[0]))
            mode, flags = arguments[1:3]
            writing = isinstance(mode, str) and any(char in mode for char in 'wax+') or (
                type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing:
                if not (self.output_ready and target == key(self.output) and self.output_opens == 0 and
                        type(flags) is int and flags & os.O_EXCL and flags & os.O_CREAT):
                    self.deny(event, 'Only one fresh requested stage JSON may be written')
                self.output_opens += 1
            elif target not in self.reads:
                self.deny(event, 'Only four exact engine-owned inputs may be read')
        if event in {'os.listdir', 'os.scandir', 'os.remove', 'os.rmdir', 'os.rename', 'os.mkdir',
                     'os.link', 'os.symlink', 'os.chmod', 'os.utime', 'os.truncate', 'os.chown'}:
            self.deny(event, 'Enumeration and unrelated filesystem mutations are forbidden')
        if event == 'ctypes.dlopen':
            if not (arguments and isinstance(arguments[0], (str, bytes, os.PathLike)) and
                    key(os.fsdecode(arguments[0])) == key(PROVIDER) and not self.loads):
                self.deny(event, 'Only one fixed pure-Lua provider load is allowed')
            self.loads.append(str(PROVIDER))
        if event in {'ctypes.dlsym', 'ctypes.dlsym/handle'}:
            if not (event == 'ctypes.dlsym' and len(arguments) == 2 and arguments[0] is self.library and
                    arguments[1] in SYMBOLS and arguments[1] not in self.symbols):
                self.deny(event, 'Only the six reviewed Lua C API symbols are allowed')
            self.symbols.append(arguments[1])
        if event == 'import':
            self.deny(event, 'No imports may occur inside the component guard')
        if event.startswith(('subprocess.', 'socket.', 'winreg.')) or event in {
                'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.spawn', 'os.posix_spawn',
                'os.fork', 'os.forkpty', 'os.kill', 'os.killpg', 'os.add_dll_directory'}:
            self.deny(event, 'Processes, windows, networking and user state are forbidden')


def extract_source(raw):
    lines = raw.splitlines(keepends=True)
    text = [line.rstrip(b'\r\n') for line in lines]

    def unique_line(value):
        found = [index for index, line in enumerate(text) if line == value]
        require(len(found) == 1, 'Source extraction anchor is missing or ambiguous')
        return found[0]

    finite_start = unique_line(b'local function finite(n)')
    finite_end = unique_line(b'local function frameTime()')
    require(finite_end == finite_start + 4 and text[finite_end - 1] == b'end', 'finite source boundary changed')
    starts = [index for index, line in enumerate(text[:-1]) if line == b'do' and
              text[index + 1] == b'  local metrics=layout.fontMetrics']
    require(len(starts) == 1, 'Shared resolver source boundary is missing or ambiguous')
    shared_start = starts[0]
    shared_end = unique_line(b'local function productionFont(fontID)')
    while shared_end > shared_start and text[shared_end - 1] == b'':
        shared_end -= 1
    require(shared_end > shared_start and text[shared_end - 1] == b'end', 'Shared resolver closing boundary changed')
    chunks, refs = {}, {}
    for name, start, end in (('finite', finite_start, finite_end), ('resolver', shared_start, shared_end)):
        chunk = b''.join(lines[start:end])
        chunks[name] = chunk.decode('utf-8')
        refs[name] = {'first_line': start + 1, 'last_line': end, 'offset': sum(map(len, lines[:start])),
                      'bytes': len(chunk), 'sha256': hashlib.sha256(chunk).hexdigest()}
    require('@@' not in ''.join(chunks.values()), 'Unexpected extraction marker in production source')
    return chunks, refs


LUA_HARNESS = r'''
local hook=debug.sethook
local function normalize(input,bank)
  local layout=input
  local ZeroSisUiSharedFontMetrics=bank
@@FINITE@@
@@RESOLVER@@
  return layout
end
-- The extracted code sees only the pure primitives that its current source uses.
setfenv(normalize,{assert=assert,type=type,getmetatable=getmetatable,pairs=pairs,next=next,
  math={huge=math.huge,floor=math.floor}})
io=nil;os=nil;package=nil;require=nil;dofile=nil;loadfile=nil;load=nil;loadstring=nil;module=nil;debug=nil
local A=string.rep('1',64)
local B=string.rep('2',64)
local C=string.rep('3',64)
local PROFILE=string.rep('a',64)
local function font(id)
  return {glyphSet=id,sha256=id,ggxmlPath='synthetic-only/'..id..'.ggxml',
    lineAdvance=12,baselineOffset=-1,spacing=0,fudgeadv=0}
end
local function fixture()
  return {kind='SyntheticOnly',attributes={ID='SyntheticFontBoundary'},children={},fontMetrics={
    policy='CIV5_GLYPHGEN_GGXML_LAYOUT_V1',retailMetricSemanticsVerified=false,
    glyphSetStorage='ZEROSIS_UI_SHARED_GLYPH_SETS_V1',sharedProfileId=PROFILE,glyphSetRefs={A,B},
    fonts={One=font(A),Two=font(B)}}},
    {schema='zerosis.ui.shared_font_metrics.v1',profileId=PROFILE,glyphSets={
      [A]={[32]={advance=5,width=0,height=0,originX=0,originY=0}},
      [B]={[65]={advance=7,width=6,height=8,originX=0,originY=-1}}}}
end
local function clone(value,seen)
  if type(value)~='table' then return value end
  seen=seen or {};if seen[value] then return seen[value] end
  local result={};seen[value]=result
  for k,v in pairs(value) do result[clone(k,seen)]=clone(v,seen) end
  return setmetatable(result,getmetatable(value))
end
local function same(a,b,seen)
  if rawequal(a,b) then return true end
  if type(a)~=type(b) then return false end
  if type(a)=='number' then return a~=a and b~=b end
  if type(a)~='table' or getmetatable(a)~=getmetatable(b) then return false end
  seen=seen or {};if seen[a]==b then return true end;seen[a]=b
  for k,v in pairs(a) do if not same(v,b[k],seen) then return false end end
  for k in pairs(b) do if a[k]==nil then return false end end
  return true
end
local results={}
local maximumInstructions=0
local totalInstructions=0
hook(function()
  totalInstructions=totalInstructions+100
  assert(totalInstructions<=8000000,'Original 8M instruction limit exceeded')
end,'',100)
local function check(name,mutate,expectedSuccess,expectedError,inspect)
  local input,bank=fixture()
  if mutate then input,bank=mutate(input,bank) end
  local beforeInput,beforeBank=clone(input),clone(bank)
  local beforeInstructions=totalInstructions
  local ok,result=pcall(normalize,input,bank)
  local instructions=totalInstructions-beforeInstructions
  maximumInstructions=math.max(maximumInstructions,instructions)
  assert(ok==expectedSuccess,name..': unexpected resolver result: '..tostring(result))
  if not ok then
    assert(type(result)=='string' and result:find(expectedError,1,true),name..': wrong rejection: '..tostring(result))
  end
  assert(same(input,beforeInput) and same(bank,beforeBank),name..': input or bank mutated')
  if inspect then inspect(result,input,bank) end
  results[#results+1]={name=name,accepted=ok,expected_result=true,input_and_bank_unchanged=true,
    instruction_hook_quantum=100,instruction_hook_count=instructions,
    rejection=not ok and result:sub(1,300) or false}
end
local function private(result,input,bank)
  assert(not rawequal(result,input) and not rawequal(result.fontMetrics,input.fontMetrics),'Private copies missing')
  assert(rawequal(result.attributes,input.attributes) and rawequal(result.children,input.children),
    'Unrelated layout fields changed')
  assert(rawequal(result.fontMetrics.fonts,input.fontMetrics.fonts),'Font metadata was copied or changed')
  assert(input.fontMetrics.glyphSets==nil,'Transport acquired private glyph maps')
  assert(not rawequal(result.fontMetrics.glyphSets,bank.glyphSets),'Selected map container must be private')
  assert(rawequal(result.fontMetrics.glyphSets[A],bank.glyphSets[A]),'Selected map A lost its identity')
end
check('shared_private_copy',nil,true,nil,function(result,input,bank)
  private(result,input,bank)
  assert(rawequal(result.fontMetrics.glyphSets[B],bank.glyphSets[B]),'Selected map B lost its identity')
  local count=0
  for _,glyphs in pairs(result.fontMetrics.glyphSets) do for _ in pairs(glyphs) do count=count+1 end end
  assert(count==2 and same(result.fontMetrics.glyphSets,bank.glyphSets),'Two synthetic glyphs were lost')
end)
check('selected_maps_only',function(input,bank)
  input.fontMetrics.glyphSetRefs={A};input.fontMetrics.fonts.Two=nil
  return input,bank
end,true,nil,function(result,input,bank)
  private(result,input,bank)
  assert(result.fontMetrics.glyphSets[B]==nil and bank.glyphSets[B]~=nil,'An unselected bank map leaked')
end)
check('legacy_inline_identity',function(input,bank)
  local metrics=input.fontMetrics
  metrics.glyphSetStorage=nil;metrics.sharedProfileId=nil;metrics.glyphSetRefs=nil
  metrics.glyphSets=bank.glyphSets
  return input,bank
end,true,nil,function(result,input,bank)
  assert(rawequal(result,input) and rawequal(result.fontMetrics.glyphSets,bank.glyphSets),'Legacy inline route changed')
end)
check('no_metrics_identity',function(input,bank)
  input.fontMetrics=nil;return input,bank
end,true,nil,function(result,input) assert(rawequal(result,input),'No-metrics route changed') end)
local negatives={
  {'missing_bank', function(i,b) return i,nil end, 'Shared font bank schema or profile'},
  {'bank_not_table', function(i,b) return i,'bank' end, 'Shared font bank schema or profile'},
  {'bank_metatable', function(i,b) setmetatable(b,{});return i,b end, 'Shared font bank schema or profile'},
  {'unknown_schema', function(i,b) b.schema='unknown';return i,b end, 'Shared font bank schema or profile'},
  {'profile_mismatch', function(i,b) b.profileId=string.rep('b',64);return i,b end, 'Shared font bank schema or profile'},
  {'bank_bad_profile', function(i,b) b.profileId='bad';return i,b end, 'Shared font bank schema or profile'},
  {'unknown_bank_field', function(i,b) b.unrecognized=true;return i,b end, 'Unknown shared font bank field'},
  {'missing_bank_maps', function(i,b) b.glyphSets=nil;return i,b end, 'Shared font bank schema or profile'},
  {'bank_maps_metatable', function(i,b) setmetatable(b.glyphSets,{});return i,b end, 'Shared font bank schema or profile'},
  {'empty_bank', function(i,b) b.glyphSets={};return i,b end, 'Shared font bank is empty'},
  {'invalid_bank_digest', function(i,b) b.glyphSets.invalid=b.glyphSets[A];return i,b end, 'Shared font bank has an invalid or empty glyph map'},
  {'empty_bank_map', function(i,b) b.glyphSets[B]={};return i,b end, 'Shared font bank has an invalid or empty glyph map'},
  {'bank_map_metatable', function(i,b) setmetatable(b.glyphSets[B],{});return i,b end, 'Shared font bank has an invalid or empty glyph map'},
  {'metrics_not_table', function(i,b) i.fontMetrics='metrics';return i,b end, 'Font metrics must be a plain table'},
  {'metrics_metatable', function(i,b) setmetatable(i.fontMetrics,{});return i,b end, 'Font metrics must be a plain table'},
  {'unknown_storage', function(i,b) i.fontMetrics.glyphSetStorage='unknown';return i,b end, 'Unknown or mixed shared/inline'},
  {'mixed_storage', function(i,b) i.fontMetrics.glyphSets=b.glyphSets;return i,b end, 'Unknown or mixed shared/inline'},
  {'partial_inline', function(i,b) i.fontMetrics.glyphSetStorage=nil;return i,b end, 'Inline font metrics cannot contain shared references'},
  {'inline_missing_maps', function(i,b) i.fontMetrics={fonts={}};return i,b end, 'Inline font metrics cannot contain shared references'},
  {'layout_bad_profile', function(i,b) i.fontMetrics.sharedProfileId=string.rep('A',64);return i,b end, 'Shared font metrics require their exact profile ID'},
  {'missing_profile', function(i,b) i.fontMetrics.sharedProfileId=nil;return i,b end, 'Shared font metrics require their exact profile ID'},
  {'missing_refs', function(i,b) i.fontMetrics.glyphSetRefs=nil;return i,b end, 'Shared font references must be a plain array'},
  {'refs_metatable', function(i,b) setmetatable(i.fontMetrics.glyphSetRefs,{});return i,b end, 'Shared font references must be a plain array'},
  {'empty_refs', function(i,b) i.fontMetrics.glyphSetRefs={};return i,b end, 'Shared font references are missing or sparse'},
  {'duplicate_refs', function(i,b) i.fontMetrics.glyphSetRefs={A,A};return i,b end, 'Shared font references must be sorted and unique'},
  {'sparse_refs', function(i,b) i.fontMetrics.glyphSetRefs={[1]=A,[3]=B};return i,b end, 'Shared font references are missing or sparse'},
  {'reversed_refs', function(i,b) i.fontMetrics.glyphSetRefs={B,A};return i,b end, 'Shared font references must be sorted and unique'},
  {'string_ref_index', function(i,b) i.fontMetrics.glyphSetRefs.extra=A;return i,b end, 'Shared font references must use dense positive array indices'},
  {'zero_ref_index', function(i,b) i.fontMetrics.glyphSetRefs[0]=A;return i,b end, 'Shared font references must use dense positive array indices'},
  {'over_limit_ref_index', function(i,b) i.fontMetrics.glyphSetRefs[65]=A;return i,b end, 'Shared font references must use dense positive array indices'},
  {'invalid_ref_digest', function(i,b) i.fontMetrics.glyphSetRefs={A,'bad'};return i,b end, 'Shared font references must be sorted and unique'},
  {'missing_referenced_map', function(i,b) i.fontMetrics.glyphSetRefs={A,C};return i,b end, 'Shared font reference is absent from its bank'},
  {'unused_reference', function(i,b) i.fontMetrics.fonts.Two=nil;return i,b end, 'Shared font references contain an unused glyph map'},
  {'missing_fonts', function(i,b) i.fontMetrics.fonts=nil;return i,b end, 'Shared font metadata is missing'},
  {'empty_fonts', function(i,b) i.fontMetrics.fonts={};return i,b end, 'Shared font metadata is empty'},
  {'fonts_metatable', function(i,b) setmetatable(i.fontMetrics.fonts,{});return i,b end, 'Shared font metadata is missing'},
  {'font_metatable', function(i,b) setmetatable(i.fontMetrics.fonts.One,{});return i,b end, 'Shared font metadata must bind its exact GGXML hash'},
  {'font_sha_mismatch', function(i,b) i.fontMetrics.fonts.One.sha256=B;return i,b end, 'Shared font metadata must bind its exact GGXML hash'},
  {'font_not_referenced', function(i,b) i.fontMetrics.fonts.One=font(C);return i,b end, 'Shared font metadata must bind its exact GGXML hash'},
  {'empty_font_path', function(i,b) i.fontMetrics.fonts.One.ggxmlPath='';return i,b end, 'Shared font metadata must bind its exact GGXML hash'},
  {'nonfinite_line', function(i,b) i.fontMetrics.fonts.One.lineAdvance=0/0;return i,b end, 'UI value must be finite'},
  {'nonfinite_baseline', function(i,b) i.fontMetrics.fonts.One.baselineOffset=math.huge;return i,b end, 'UI value must be finite'},
  {'nonfinite_spacing', function(i,b) i.fontMetrics.fonts.One.spacing=-math.huge;return i,b end, 'UI value must be finite'},
  {'nonnumeric_fudge', function(i,b) i.fontMetrics.fonts.One.fudgeadv='0';return i,b end, 'UI value must be finite'},
  {'nonpositive_line', function(i,b) i.fontMetrics.fonts.One.lineAdvance=0;return i,b end, 'Shared font line advance must be positive'}
}
for _,case in ipairs(negatives) do check(case[1],case[2],false,case[3]) end
local function quoted(value)
  local escapes={['"']='\\"',['\\']='\\\\',['\b']='\\b',['\f']='\\f',['\n']='\\n',['\r']='\\r',['\t']='\\t'}
  return '"'..value:gsub('[%z\1-\31\\"]',function(c) return escapes[c] or string.format('\\u%04x',c:byte()) end)..'"'
end
local function json(value)
  if type(value)=='string' then return quoted(value) end
  if type(value)=='boolean' or type(value)=='number' then return tostring(value) end
  assert(type(value)=='table','Unexpected report value')
  local parts={}
  if #value>0 then
    for _,v in ipairs(value) do parts[#parts+1]=json(v) end
    return '['..table.concat(parts,',')..']'
  end
  local keys={};for k in pairs(value) do keys[#keys+1]=k end;table.sort(keys)
  for _,k in ipairs(keys) do parts[#parts+1]=quoted(k)..':'..json(value[k]) end
  return '{'..table.concat(parts,',')..'}'
end
local outcome={cases=results,positive_cases=4,negative_cases=#negatives,synthetic_glyph_count=2,
  private_copies_and_map_identity_verified=true,input_layout_and_bank_unchanged=true,
  source_finite_and_shared_resolver_executed=true,instruction_limit=8000000,
  maximum_instruction_hook_count=maximumInstructions,total_instruction_hook_count=totalInstructions,
  instruction_hook_quantum=100}
hook()
return json(outcome)
'''


def execute_lua(source, boundary):
    lua = ctypes.CDLL(str(PROVIDER))
    boundary.library = lua
    api = {name: getattr(lua, name) for name in sorted(SYMBOLS)}
    api['luaL_newstate'].argtypes, api['luaL_newstate'].restype = [], ctypes.c_void_p
    api['luaL_openlibs'].argtypes, api['luaL_openlibs'].restype = [ctypes.c_void_p], None
    api['luaL_loadbuffer'].argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    api['luaL_loadbuffer'].restype = ctypes.c_int
    api['lua_pcall'].argtypes, api['lua_pcall'].restype = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int], ctypes.c_int
    api['lua_tolstring'].argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    api['lua_tolstring'].restype = ctypes.c_void_p
    api['lua_close'].argtypes, api['lua_close'].restype = [ctypes.c_void_p], None
    state = api['luaL_newstate']()
    require(state, 'Cannot create the single isolated Lua state')
    boundary.states_created += 1
    try:
        api['luaL_openlibs'](state)
        raw = source.encode('utf-8')
        require(len(raw) <= 48 * 1024, 'Synthetic harness exceeds its small source bound')
        boundary.chunks_loaded += 1
        status = api['luaL_loadbuffer'](state, raw, len(raw), b'@UiScene-shared-resolver-source.lua')
        if status == 0:
            boundary.chunks_called += 1
            status = api['lua_pcall'](state, 0, 1, 0)
        length = ctypes.c_size_t()
        pointer = api['lua_tolstring'](state, -1, ctypes.byref(length))
        require(pointer and length.value <= 64 * 1024, 'Missing or oversized Lua component result')
        returned = ctypes.string_at(pointer, length.value).decode('utf-8')
        require(status == 0, 'Extracted-source component failed: ' + returned[:1000])
        return json.loads(returned)
    finally:
        api['lua_close'](state)
        boundary.states_closed += 1


def verify(boundary, report):
    raw_scope, scope_ref = read_sealed(SCOPE, 16 * 1024)
    raw_scene, scene_ref = read_sealed(SCENE, 256 * 1024)
    _, provider_ref = read_sealed(PROVIDER, 256 * 1024)
    _, self_ref = read_sealed(Path(__file__).absolute(), 64 * 1024)
    report['inputs'] = {'scope': scope_ref, 'scene': scene_ref, 'provider': provider_ref, 'test': self_ref}
    require(scope_ref['sha256'] == SCOPE_SHA and scene_ref['sha256'] == SCENE_SHA and
            provider_ref['sha256'] == LUA_SHA and provider_ref['bytes'] == 166912, 'Reviewed inputs changed')
    scope = json.loads(raw_scope.decode('utf-8-sig'))
    require(scope['schema'] == 'zerosis.goody_hut.shared_font_source.scope.v1' and
            scope['pure_lua_component_allowed'] is True and scope['retail_mod_test_hold_active'] is True and
            scope['host_gamecore_hwnd_execution_allowed'] is False and
            scope['retail_user_state_or_game_process_access_allowed'] is False and
            scope['default_promotion_allowed'] is False and scope['full_engine_goal_complete'] is False and
            scope['mod_ids_save_keys_or_schemas_changed'] is False, 'Scope boundary changed')
    contract = scope['contract']
    require(contract['bank_schema'] == 'zerosis.ui.shared_font_metrics.v1' and
            contract['storage_tag'] == 'ZEROSIS_UI_SHARED_GLYPH_SETS_V1' and
            contract['global_name'] == 'ZeroSisUiSharedFontMetrics' and
            contract['source_glyph_count_per_changed_set'] == 17315, 'Shared-font contract changed')
    chunks, extracted = extract_source(raw_scene)
    report['extracted_source'] = extracted
    harness = LUA_HARNESS.replace('@@FINITE@@', chunks['finite']).replace('@@RESOLVER@@', chunks['resolver'])
    require('@@' not in harness, 'Unresolved extracted-source marker')
    report['harness'] = {'bytes': len(harness.encode('utf-8')), 'sha256': hashlib.sha256(harness.encode('utf-8')).hexdigest()}
    result = execute_lua(harness, boundary)
    negatives = re.findall(r"^  \{'([a-z0-9_]+)', function", LUA_HARNESS, re.M)
    expected = ['shared_private_copy', 'selected_maps_only', 'legacy_inline_identity', 'no_metrics_identity', *negatives]
    require([row['name'] for row in result['cases']] == expected and len(set(expected)) == len(expected) and
            result['positive_cases'] == 4 and result['negative_cases'] == len(negatives) and len(negatives) == 45 and
            all(row['accepted'] is (index < 4) and row['expected_result'] is True and
                row['input_and_bank_unchanged'] is True for index, row in enumerate(result['cases'])),
            'Synthetic boundary cases were skipped or did not verify their expected result')
    require(result['synthetic_glyph_count'] == 2 and result['source_finite_and_shared_resolver_executed'] is True and
            result['private_copies_and_map_identity_verified'] is True and result['input_layout_and_bank_unchanged'] is True and
            result['instruction_limit'] == INSTRUCTION_LIMIT and
            0 < result['maximum_instruction_hook_count'] <= result['total_instruction_hook_count'] <= INSTRUCTION_LIMIT,
            'Extracted-source proof or original budget changed')
    for reference in report['inputs'].values():
        _, after = read_sealed(reference['path'], max(reference['bytes'], 1))
        require(after == reference, 'Component input changed during the Lua boundary check')
    require(not boundary.denied and boundary.loads == [str(PROVIDER)] and set(boundary.symbols) == SYMBOLS and
            boundary.states_created == boundary.states_closed == boundary.chunks_loaded == boundary.chunks_called == 1,
            'The single-state pure-Lua execution boundary changed')
    report.update(result)
    report.update(status='PASS_EXTRACTED_SHARED_FONT_RESOLVER_SYNTHETIC_BOUNDARY', inputs_unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Fresh JSON directly below this shared-font evidence stage')
    arguments = parser.parse_args()
    require(os.name == 'nt' and sys.flags.optimize == 0, 'Reviewed Windows Python without optimization is required')
    require(key(STAGE) == key(PROJECT / 'evidence/goody_hut/shared_fonts'), 'Unexpected evidence stage')
    output = Path(os.path.abspath(arguments.output))
    require(key(output.parent) == key(STAGE) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,95}\.json', output.name),
            'Output must be one named JSON directly below the evidence stage')
    ordinary_path(output, fresh=True)
    # Warm codecs and ctypes parameter types before the exact-input audit guard.
    b'x'.decode('utf-8-sig')
    ctypes.POINTER(ctypes.c_size_t)
    json.dumps({}, ensure_ascii=False)
    boundary = Boundary(output)
    sys.addaudithook(boundary.audit)
    report = {'schema': 'zerosis.goody_hut.shared_font_scene_resolver_boundary.v1', 'status': 'FAIL',
              'python_optimization_level': 0, 'fixture': 'SYNTHETIC_TWO_GLYPHS_IN_TWO_MAPS',
              'whole_scene_executed': False, 'actual_font_maps_loaded': False,
              'actual_17315_glyph_preservation_verified': False,
              'unused_glyph_numeric_validation_claimed': False,
              'duplicate_bank_key_rejection_claimed': False,
              'duplicate_bank_key_limit': 'Duplicate raw keys are no longer distinguishable after a Lua table is constructed.',
              'native_acceptance': False, 'full_engine_goal_complete': False, 'host_executed': False,
              'gamecore_loaded': False, 'hwnd_created': False, 'game_process_queries': 0,
              'retail_user_state_accessed': False, 'mod_ids_save_keys_or_schemas_changed': False}
    try:
        verify(boundary, report)
    except Exception as error:
        report.update(status='FAIL', error={'type': type(error).__name__, 'message': str(error)[:2000]})
    report['boundary'] = {'permitted_component_dll_loads': boundary.loads,
                          'permitted_lua_symbols': sorted(boundary.symbols),
                          'lua_states_created': boundary.states_created, 'lua_states_closed': boundary.states_closed,
                          'lua_chunks_loaded': boundary.chunks_loaded, 'lua_chunks_called': boundary.chunks_called,
                          'forbidden_access_attempts': boundary.denied, 'subprocesses_started': 0,
                          'output_policy': 'ONE_EXCLUSIVE_FRESH_JSON_DIRECTLY_BELOW_STAGE'}
    boundary.output_ready = True
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
