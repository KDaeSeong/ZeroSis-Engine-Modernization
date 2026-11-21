local arrayType={}
local function encoded(value)
  return __ZeroSisSnapshotJson(value,arrayType)
end

local typed={
  label='기술 트리',
  number=1.2345678901234567,
  sparse=setmetatable({[2]='not visited'},arrayType),
  ordered={z='last',a='first'},
  controls='\0\1\31"\\',
  repeated={shared={answer=42}}
}

snapshot_json_report=encoded({
  status='UI_SNAPSHOT_JSON_ROUNDTRIP_FIXTURE',
  empty_array=encoded(setmetatable({},arrayType)),
  empty_object=encoded({}),
  sparse_array=encoded(typed.sparse),
  sorted_object=encoded(typed.ordered),
  payload=encoded(typed)
},arrayType)
