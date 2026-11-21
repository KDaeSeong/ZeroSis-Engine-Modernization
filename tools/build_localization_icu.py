"""Build the actual Localization numeric/case backend, separate from its probes."""
import argparse
import json
from pathlib import Path
import re
import struct
from collect_baseline import PROJECT, digest
from native_build import environment_for, run
from build_icu44 import artifact, verify_source
from verify_localization_reference import artifacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vs", type=Path, default=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"))
    args = parser.parse_args()
    root, _, _ = verify_source()
    dependency_path = PROJECT / "evidence/icu44/build_result.json"
    dependency = json.loads(dependency_path.read_text(encoding="utf-8"))
    if dependency["status"] != "ICU44_AMD64_STATIC_LIBRARIES_BUILT":
        raise RuntimeError("ICU dependency build is incomplete")
    for item in artifacts(dependency):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("ICU dependency differs: " + item["path"])
    out = PROJECT / "Build/Localization/icu_backend"
    evidence = PROJECT / "evidence/localization/icu_backend"
    out.mkdir(parents=True, exist_ok=True); evidence.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(args.vs, "x64", out)
    source = PROJECT / "Source/Providers/Localization/SdkLocalizationIcu.cpp"
    header = source.with_suffix(".h")
    obj = out / "SdkLocalizationIcu.obj"
    flags = ["/nologo", "/c", "/O2", "/MD", "/EHsc", "/std:c++17", "/fp:strict", "/W4", "/WX", "/utf-8",
             "/DU_STATIC_IMPLEMENTATION", "/DU_HAVE_INTTYPES_H=1", "/FIstdint.h",
             f'/I"{root / "source/common"}"', f'/I"{root / "source/i18n"}"', f'/Fo"{obj}"', f'"{source}"']
    rsp = out / "compile.rsp"; rsp.write_text("\n".join(flags) + "\n", encoding="utf-8")
    result = run([compiler, "@" + str(rsp)], cwd=out, env=env)
    log = evidence / "build.log"; log.write_bytes(result.stdout + result.stderr)
    if result.returncode or re.search(rb"warning\s+[A-Z]+\d+", result.stdout + result.stderr, re.I):
        raise RuntimeError("Localization backend build failed: " + str(log))
    with obj.open("rb") as stream:
        if struct.unpack("<H", stream.read(2))[0] != 0x8664:
            raise RuntimeError("Localization backend object is not AMD64")
    lib = out / "localization_icu.lib"
    librarian = Path(compiler).with_name("lib.exe")
    result = run([librarian, "/nologo", "/WX", "/Brepro", "/MACHINE:X64", "/OUT:" + str(lib), obj], cwd=out, env=env)
    lib_log = evidence / "library.log"; lib_log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("Localization backend librarian failed")
    report = {"status": "SDK_LOCALIZATION_ICU_BACKEND_BUILT", "sources": [artifact(source), artifact(header)],
              "object": artifact(obj), "library": artifact(lib), "dependency": artifact(dependency_path),
              "compiler": artifact(Path(compiler)), "librarian": artifact(librarian), "flags": flags,
              "response": artifact(rsp), "log": artifact(log), "library_log": artifact(lib_log),
              "compiler_warnings": 0, "builder": artifact(Path(__file__).resolve()),
              "game_launched": False, "gamecore_loaded": False,
              "scope": "Internal numeric/case implementation; SDK String/dictionary/parser integration pending"}
    (evidence / "build_result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["status"])


if __name__ == "__main__":
    main()
