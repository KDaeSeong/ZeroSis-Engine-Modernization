"""Define reviewed numeric edits against the preserved attempt-005 diagnostic baseline.

This edits only the canonical patch specification; build_sdk_x64 generates SDK copies.
"""
from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
import re

from collect_baseline import PROJECT, digest


def main():
    specification = PROJECT / "Source/Porting/sdk_x64_patches.json"
    plan = json.loads(specification.read_text(encoding="utf-8"))
    plan["patches"] = [p for p in plan["patches"] if not p["id"].startswith("numeric_")]
    manifest = json.loads((PROJECT / "evidence/numeric_boundaries/before/port_manifest.json").read_text(encoding="utf-8"))
    mapping = {r["relative_path"].lower(): r for r in manifest}
    original, working = {}, {}
    for key, row in mapping.items():
        path = Path(row["snapshot"])
        if digest(path) != row["original_sha256"]:
            raise RuntimeError(f"Snapshot changed: {path}")
        content = path.read_bytes().decode("latin1")
        for patch in plan["patches"]:
            if patch["file"].lower() == key:
                if content.count(patch["old"]) != patch["count"]:
                    raise RuntimeError(f"Preceding patch drift: {patch['id']}")
                content = content.replace(patch["old"], patch["new"])
        original[key] = content
        working[key] = content
    changed, lua_files, ledger = set(), set(), []

    def add(file, old, new, reason):
        key = file.lower()
        if old == new:
            raise RuntimeError("No-op patch")
        if old not in working[key]:
            if new in working[key]:
                return # A previous identical line edit covered repeated diagnostics.
            raise RuntimeError(f"Missing patch text: {file}: {old!r}")
        row = mapping[key]
        plan["patches"].append({"id": f"numeric_{len(plan['patches']):04d}",
            "file": row["relative_path"], "source_sha256": row["original_sha256"],
            "old": old, "new": new, "count": working[key].count(old), "reason": reason})
        working[key] = working[key].replace(old, new)
        changed.add(key)

    def wrap(expr, target):
        return f"CvChecked::Integer<{target}>({expr})"

    rows = list(csv.DictReader((PROJECT / "evidence/numeric_boundaries/before/compiler_diagnostics.csv").open(encoding="utf-8-sig")))
    for row in rows:
        file, code = row["file"], row["code"]
        if code not in {"C4244", "C4267", "C4838"}:
            continue
        key = file.lower()
        line = original[key].splitlines()[int(row["line"]) - 1]
        reason = "Preserve the original game field width; reject unrepresentable values before conversion"
        new = None
        if code == "C4244":
            if re.search(r"\blua(?:L)?_(?:tointeger|checkinteger|optinteger)\(", line):
                new = line.replace("lua_tointeger(", "CvLuaChecked::ToInt(")
                new = new.replace("luaL_checkinteger(", "CvLuaChecked::CheckUInt(" if "uint uiSpyIndex" in line else "CvLuaChecked::CheckInt(")
                new = new.replace("luaL_optinteger(", "CvLuaChecked::OptInt(")
                lua_files.add(key)
                reason = "Keep Lua conversion semantics, validate native numeric range, then validate the 32-bit game field"
            elif "FFastVector.h" in file:
                match = re.search(r"=\s*(.+);", line)
                target = "unsigned int" if ("unsigned int" in line or "UINT " in line) else "int"
                new = line[:match.start(1)] + wrap(match.group(1), target) + line[match.end(1):]
            elif "FromLuaAnalog<T>::Convert(analog)" in line:
                reason = "FLua int validator/converter specialization shared by GetAs and Value::GetAs"
            else:
                raise RuntimeError(f"Unreviewed C4244: {file}: {line}")
        elif code == "C4838":
            if file.endswith("CvNotifications.cpp"):
                new = re.sub(r"\b(NOTIFICATION_\w+)\b", r"static_cast<uint>(\1)", line)
                reason = "Intentional modulo-2^32 notification hash bits, unchanged enum and legacy table position"
            elif file.endswith("CvTeam.cpp"):
                new = re.sub(r"\b(num\w+Infos)\b", lambda m: wrap(m[0], "unsigned int"), line)
                reason = "Reject negative allocation dimensions while retaining unsigned 32-bit descriptor fields"
            else:
                raise RuntimeError(f"Unreviewed C4838: {file}")
        else:
            if file.endswith(("CvDatabaseUtility.cpp", "FAutoVector.h")):
                reason = "Checked native allocation bytes or command-field preflight in the complete function edit"
            elif "iCulturePerWork * m_aBuildingGreatWork.size()" in line:
                new = line.replace("iCulturePerWork * m_aBuildingGreatWork.size()", "CvChecked::CountProduct(iCulturePerWork, m_aBuildingGreatWork.size())")
            elif "if(mapScript[i] == '.')" in line:
                new = line.replace("mapScript[i]", "mapScript.c_str()[i]")
                reason = "Use the already length-bounded native index directly, avoiding FString's 32-bit subscript API"
            elif "lua_createtable(L, data.size() - 1, 1)" in line:
                new = line.replace("data.size() - 1", "data.empty() ? 0 : CvChecked::Integer<int>(data.size() - 1)")
                reason = "Nonnegative Lua capacity hint for empty history; stored keys and values unchanged"
            elif "s_GameOptionsHash" in line and "= i;" in line:
                new = line.replace("= i;", "= CvChecked::Integer<unsigned int>(i);")
            else:
                quotes = re.findall(r"'([^']+)'", row["example_message"])
                target = next((v for v in quotes[2:] if v in {"int", "unsigned int", "uint", "UINT", "const ObjectType"}), None)
                if target == "const ObjectType":
                    target = "int" # s_numVictoryInfos is FAutoVariable<int,...>.
                if target in {"uint", "UINT"}:
                    target = "unsigned int"
                match = re.search(r"(?:\w+(?:(?:->|\.)\w+)*|CvPreGame::\w+\(\))\.size\(\)|(?:strlen|_tcslen)\([^()]+\)|\blen(?:Building|Improvement)Type\b", line)
                if not target or not match:
                    raise RuntimeError(f"Unreviewed C4267: {file}: {line}")
                expr = match[0]
                # Unsigned final indices follow insertion in these original functions.
                if target == "unsigned int" and line[match.end():].startswith(" - 1"):
                    expr += " - 1"
                new = line.replace(expr, wrap(expr, target))
        if new is not None:
            add(file, line + "\r\n", new + "\r\n", reason)
        ledger.append({"file": mapping[key]["relative_path"], "baseline_line": int(row["line"]),
                       "code": code, "before": line.strip(), "after": new.strip() if new else "shared function/template patch", "reason": reason})

    file = "CvGameCoreDLL_Expansion2/CvDatabaseUtility.cpp"
    add(file, "unsigned int iNumBytes = iCount1 * sizeof(int*) + iCount1 * iCount2 * sizeof(int);",
        "const size_t iNumBytes = CvChecked::Array2DBytes(CvChecked::Integer<size_t>(iCount1), CvChecked::Integer<size_t>(iCount2), sizeof(int), sizeof(int*));",
        "Compute and check all pointer-table and payload byte products in native width, in both overloads")
    for index in ("i", "j"):
        add(file, f"for(unsigned int {index} =", f"for(size_t {index} =",
            "Native-size allocation dimensions require native-size traversal counters")
    add(file, "delete[] ppArray;", "delete[] reinterpret_cast<unsigned char*>(ppArray);",
        "Release the same unsigned-char array type created by Initialize2DArray")

    file = "FirePlace/include/FireWorks/FAutoVector.h"
    add(file, "command(c)", "command(CvChecked::Integer<unsigned char>(static_cast<int>(c)))",
        "Check the command enum before storing its existing one-byte serialized field")
    for signature, field in (("setAt(size_t index, const ElementType & v)", "index"),
                             ("insert(size_t index, const ElementType & v)", "index"),
                             ("erase(size_t index)", "index"),
                             ("resize(size_t count)", "count"),
                             ("resize(size_t count, const ElementType & v)", "count")):
        add(file, signature + "\r\n{", signature + "\r\n{\r\n\tconst unsigned int commandIndex = CvChecked::Integer<unsigned int>(" + field + ");",
            "Check the 32-bit command field before touch, vector access or mutation")
    for command, field in (("SET", "index"), ("INSERT", "index"), ("ERASE", "index"), ("RESIZE", "count"), ("RESIZE_WITH_VALUE", "count")):
        add(file, f"::{command}, {field},", f"::{command}, commandIndex,", "Use the prevalidated command field without changing its serialized type")

    file = "FirePlace/include/FireWorks/FLua/Include/FLuaCommon.h"
    lua_files.add(file.lower())
    add(file, "return lua_tointeger(L, idx);", "return CvLuaChecked::ToInteger(L, idx);", "Validate finite native range before Lua's floating-to-integer conversion")
    old = "\t\t// ArgValidator for uint\r\n"
    new = """\t\t// x64 Lua integers must fit the existing 32-bit game integer.
\t\ttemplate<> struct ArgValidator<int> {
\t\t\tstatic inline void Validate(lua_Integer &arg, bool &bValid) {
\t\t\t\tint checked = 0;
\t\t\t\tif (!CvChecked::TryInteger(arg, checked)) {
\t\t\t\t\tError(_T("Bad argument: Integer outside game field range"));
\t\t\t\t\tbValid = false;
\t\t\t\t}
\t\t\t}
\t\t};
\t\ttemplate<> struct ArgValidator<const int> : ArgValidator<int> {};

""".replace("\n", "\r\n") + old
    add(file, old, new, "Use FLua's existing invalid-argument path, allowing Value::GetAs to pop its stack value")
    old = "\t\t// FromLuaAnalog for reference types\r\n"
    new = """\t\ttemplate<> struct FromLuaAnalog<int> {
\t\t\tstatic inline int Convert(const lua_Integer arg) { return CvChecked::Integer<int>(arg); }
\t\t};
\t\ttemplate<> struct FromLuaAnalog<const int> : FromLuaAnalog<int> {};

""".replace("\n", "\r\n") + old
    add(file, old, new, "Return an int only after validation instead of implicit native-width narrowing")

    # The count is validated before replacing the stored victory list.
    file = "CvGameCoreDLL_Expansion2/CvPreGame.cpp"
    add(file, "\ts_victories = v;\r\n\ts_numVictoryInfos = CvChecked::Integer<int>(s_victories.size());",
        "\tconst int count = CvChecked::Integer<int>(v.size());\r\n\ts_victories = v;\r\n\ts_numVictoryInfos = count;",
        "Validate the fixed-width count before the dependent state mutation")

    for key in sorted(changed):
        include = '#include "CvLuaCheckedInteger.h"\r\n' if key in lua_files else '#include "CvCheckedNarrow.h"\r\n'
        if key.endswith(".cpp"):
            match = re.search(r'^#include ["<][^\r\n]*CvGameCoreDLLPCH\.h[">]\r?\n', working[key], re.M)
            if not match:
                raise RuntimeError(f"Missing PCH include: {key}")
            old = match[0]
            add(key, old, old + include, "Explicit port support dependency after the precompiled header")
        else:
            first = working[key][:1024]
            if working[key].count(first) != 1:
                raise RuntimeError(f"Nonunique header include context: {key}")
            add(key, first, include + first, "Make the modified public header's checked conversion dependency explicit")

    evidence = PROJECT / "evidence/numeric_boundaries"
    specification.write_text(json.dumps(plan, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    (evidence / "edit_ledger.json").write_text(json.dumps({"baseline_diagnostic_locations": len(ledger),
        "by_code": dict(Counter(r["code"] for r in ledger)), "modified_sdk_files": len(changed),
        "patch_specification_sha256": digest(specification), "locations": ledger}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"numeric_locations": len(ledger), "modified_sdk_files": len(changed), "patch_entries": len(plan["patches"])}))


if __name__ == "__main__":
    main()
