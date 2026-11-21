import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

directory = Path(__file__).resolve().parent
project = directory.parents[2]
tools = project / "tools"
sys.path.insert(0, str(tools))
from native_build import environment_for, run
from collect_baseline import digest

provider = project / "Build/Localization/provider_x64"
database = project / "Build/Database/x64"
provider_report = json.loads((project / "evidence/localization/provider/build_result.json").read_text(encoding="utf-8"))
database_report = json.loads((project / "evidence/database/candidate/build_result.json").read_text(encoding="utf-8"))
vs = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
environment, compiler = environment_for(vs, "x64", directory)
environment["VSLANG"] = "1033"
compiler = Path(compiler)
sdk = project / "Source/SDK_BNW_x64"
icu = project / "Source/ThirdParty/ICU44/original/source"
include = [f'/I"{project / "Source/Providers/Localization"}"',
           f'/I"{project / "Source/Providers/Database"}', "/external:W0"]
include += [f'/external:I"{path}"' for path in (sdk / "CvLocalization/include", sdk / "CvGameDatabase/include", icu / "common", icu / "i18n")]
flags = ["/nologo", "/O2", "/MD", "/EHsc", "/std:c++14", "/W4", "/WX", "/utf-8", "/fp:strict",
         "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS", "/DU_STATIC_IMPLEMENTATION", "/DU_HAVE_INTTYPES_H=1",
         "/FIstdint.h", *include]
exe = directory / "number_provider_probe.exe"
obj = directory / "number_provider_probe.obj"
response = directory / "number_provider_probe.rsp"
link_map = directory / "number_provider_probe.map"
response.write_text("\n".join(flags + [f'"{directory / "probe.cpp"}"', f'"{provider / "ZeroSisLocalization_x64.lib"}"',
    f'"{database / "ZeroSisDatabase_x64.lib"}"', f'/Fo"{obj}"', f'/Fe"{exe}"']) + "\n", encoding="utf-8")
built = run([compiler, f"@{response}", "/link", "/WX", "/INCREMENTAL:NO", "/Brepro", "/MACHINE:X64", f"/MAP:{link_map}"],
            cwd=directory, env=environment, timeout=180)
(directory / "compile.log").write_bytes(built.stdout + built.stderr)
if built.returncode:
    raise SystemExit(f"probe build failed: {built.returncode}")

runtime_env = dict(environment)
runtime_env["PATH"] = str(provider) + ";" + str(database) + ";" + runtime_env.get("PATH", "")
executed = run([exe], cwd=provider, env=runtime_env, timeout=30)
(directory / "stdout.log").write_bytes(executed.stdout)
(directory / "stderr.log").write_bytes(executed.stderr)
if executed.returncode:
    raise SystemExit(f"probe execution failed: {executed.returncode}")

text = executed.stdout.decode("ascii")
results = []
for line in text.splitlines():
    if not line.startswith("RESULT|"):
        continue
    _, name, byte_field, encoded = line.split("|", 3)
    count = int(byte_field.removeprefix("bytes="))
    raw = bytes.fromhex(encoded)
    if len(raw) != count:
        raise SystemExit(f"output byte count mismatch for {name}")
    results.append({"input": name, "output_utf8_hex": encoded, "output": raw.decode("utf-8")})
if len(results) != 6 or "PASS|6" not in text:
    raise SystemExit("probe did not report all six successful formatter cases")
expected = ["0", "1.23", "-1.23", "NaN", "NaN", "NaN"]
if [item["output"] for item in results] != expected:
    raise SystemExit(f"unexpected formatter output: {[item['output'] for item in results]}")

report = {
    "status": "PASS",
    "scope": "Isolated call through the frozen ZeroSisLocalization_x64 provider and its public Localization::String composition API; no GameCore or Civ V module loaded.",
    "pattern": "{1:number #.##}",
    "inputs": ["0", "1.234", "-1.234", "quiet_NaN", "+infinity", "-infinity"],
    "results": results,
    "probe_source": {"path": str(directory / "probe.cpp"), "sha256": digest(directory / "probe.cpp")},
    "provider_dll": provider_report["dll"],
    "provider_import_library": provider_report["library"],
    "database_dll": database_report["dll"],
    "compiler": {"path": str(compiler), "sha256": digest(compiler)},
    "executable_sha256_before_cleanup": digest(exe),
    "compile_log_sha256": digest(directory / "compile.log"),
    "stdout_log_sha256": digest(directory / "stdout.log"),
    "stderr_log_sha256": digest(directory / "stderr.log"),
    "process_exit_code": executed.returncode,
    "game_launched": False,
    "gamecore_loaded": False,
}
for item in (exe, obj, response, link_map, directory / "read_build_environment.cmd"):
    if item.exists():
        item.unlink()
(directory / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
