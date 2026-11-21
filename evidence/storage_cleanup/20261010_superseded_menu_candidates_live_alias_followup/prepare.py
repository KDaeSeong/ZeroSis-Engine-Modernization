"""Prepare an exact ten-root follow-up; allow only positive live-EA DDS aliases."""
from __future__ import annotations
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXPECTED = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization")
if ROOT != EXPECTED or OUT != ROOT / "evidence/storage_cleanup/20261010_superseded_menu_candidates_live_alias_followup":
    raise RuntimeError("Unexpected follow-up output boundary")
ORIGINAL = ROOT / "evidence/storage_cleanup/20261010_superseded_menu_candidates"
ORIGINAL_PLAN_SHA = "0310b24da094eddeca38d9cb8238d8b1c419045180819fac5ee4d96e1d83b220"
ORIGINAL_PREPARE_SHA = "5cbab2b5c4a453e0cc33867639bcccda52947b6205eafd80480de1d638134a4b"
EA_SESSION = ROOT / "Build/InteractiveGameRuntime/20261009T163702Z_0461db127034/sessions/c91e76144590c3387df3eb021427f506"
SCHEMA = "ZEROSIS_TEN_ROOT_POSITIVE_LIVE_EA_DDS_ALIAS_FOLLOWUP_V1"
POLICY = dict(allowed_session=str(EA_SESSION), relative_pattern="play-ui-[1-9][0-9]*/{source_assets,textures}/<existing-exact-DDS-basename-in-same-directory>",
    extensions=[".dds"], content_magic="DDS ", original_file_id_required=True,
    original_names_and_metadata_required=True, original_content_sha_required=True,
    positive_alias_additions_only=True, missing_original_or_accepted_alias_forbidden=True,
    target_name_addition_forbidden=True, other_sessions_and_paths_forbidden=True,
    reconcile_on_link_count_change_before_each_unlink=True, final_alias_reconciliation_required=True)

def digest(path):
    with Path(path).open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()

# Import only the reviewed definitions; never execute the historical main/apply.
if digest(ORIGINAL / "plan.json") != ORIGINAL_PLAN_SHA or digest(ORIGINAL / "prepare.py") != ORIGINAL_PREPARE_SHA:
    raise RuntimeError("Original reviewed plan/definitions changed")
spec = importlib.util.spec_from_file_location("original_menu_retirement_definitions", ORIGINAL / "prepare.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
need = m.need

def pair(identity):
    return identity["device"], identity["file_id"]

def nonlink(identity):
    return {key: value for key, value in identity.items() if key != "links"}

def write_new(name, document):
    path = OUT / name
    need(path.parent == OUT, "Follow-up output escaped")
    raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with path.open("xb") as stream: stream.write(raw)
    need(path.read_bytes() == raw, "Follow-up write changed")
    return dict(path=str(path), bytes=len(raw), sha256=digest(path))

def load_original():
    need(digest(ORIGINAL / "plan.json") == ORIGINAL_PLAN_SHA, "Original plan SHA changed")
    plan = m.read(ORIGINAL / "plan.json")
    need(plan["schema"] == m.SCHEMA and plan["status"] == "READY_FOR_ROOT_REVIEW_NO_DELETION" and
         plan["project"] == str(ROOT) and plan["targets"] == [str(x) for x in m.TARGETS] and len(m.TARGETS) == 10,
         "Original exact target contract changed")
    need(not any((ORIGINAL / name).exists() for name in
         ("application-started.json", "retired.json", "application-failed.json", "unlink-journal.jsonl")),
         "Original apply acquired an execution marker; no follow-up permitted")
    for item in [*plan["scripts"].values(), *plan["helper_inputs"]]:
        need(digest(m.checked(Path(item["path"]))) == item["sha256"], "Original reviewed code changed")
    values = []
    for name in ("inventory", "protection", "diagnostics"):
        ref = plan[name]; path = m.checked(Path(ref["path"]))
        need(path == ORIGINAL / (name + ".json.gz") and digest(path) == ref["sha256"], "Original ledger hash/path changed")
        packed = path.read_bytes(); raw = gzip.decompress(packed)
        need(len(packed) == ref["bytes"] and len(raw) == ref["uncompressed_bytes"] and
             hashlib.sha256(raw).hexdigest() == ref["uncompressed_sha256"], "Original ledger length/roundtrip changed")
        values.append(json.loads(raw))
    inventory, protection, diagnostics = values
    need(len(inventory["files"]) == plan["target_file_count"] and
         len(inventory["directories"]) == plan["target_directory_count"], "Original inventory counts changed")
    need(all(m.inside(Path(row["path"])) for row in inventory["files"] + inventory["directories"]), "Original inventory escaped")
    need(all(not m.inside(Path(row["path"])) for row in protection["files"]), "Protection intersects targets")
    return plan, inventory, protection, diagnostics

def current_tree(inventory):
    files, directories = set(), set()
    for target in m.TARGETS:
        for path, info, directory in m.walk(target):
            (directories if directory else files).add(str(path))
    need(files == {row["path"] for row in inventory["files"]} and
         directories == {row["path"] for row in inventory["directories"]}, "Target tree membership changed")
    for row in inventory["directories"]:
        need(m.ident(m.checked(Path(row["path"])).lstat()) == row["identity"], "Target directory metadata changed")

class LiveAliasState:
    """Keep the original ledger intact and account for this one live session."""
    def __init__(self, groups, seed=()):
        self.groups = {pair(group["identity"]): group for group in groups}
        need(len(self.groups) == len(groups), "Duplicate original file identity")
        self.additions = {key: set() for key in self.groups}
        self.removed = set()
        self.removed_counts = Counter()
        self.parents_checked = set()
        self.observations = {}
        for group in groups:
            names = {Path(p) for p in group["target_paths"] + group["surviving_aliases"]}
            need(len(names) == group["identity"]["links"], "Original alias count inconsistent")
        for row in seed:
            key = (row["device"], row["file_id"])
            need(key in self.groups, "Accepted addition references unknown original file")
            for name in row["added_paths"]:
                path = Path(name)
                self.validate_addition_path(path, self.groups[key])
                self.additions[key].add(path)

    def original_names(self, group):
        return {Path(path) for path in group["target_paths"] + group["surviving_aliases"]}

    def expected_names(self, group):
        key = pair(group["identity"])
        return (self.original_names(group) - self.removed) | self.additions[key]

    def validate_parents(self, path):
        for parent in path.parents:
            if parent in self.parents_checked: break
            info = parent.lstat()
            need(parent.is_dir() and not info.st_file_attributes & 0x400, "Alias reparse ancestor changed")
            self.parents_checked.add(parent)

    def validate_addition_path(self, path, group):
        need(path.is_absolute() and not m.inside(path) and path.is_relative_to(EA_SESSION), "Alias addition escaped live EA session: " + str(path))
        parts = path.relative_to(EA_SESSION).parts
        need(len(parts) == 3 and re.fullmatch(r"play-ui-[1-9][0-9]*", parts[0]) is not None and
             parts[1] in ("source_assets", "textures") and path.suffix == ".dds",
             "Alias addition escaped exact source_assets/textures DDS boundary: " + str(path))
        known_names = {Path(name).name for name in group["surviving_aliases"]
                       if Path(name).parent.name == parts[1] and Path(name).suffix == ".dds"}
        need(path.name in known_names, "Alias is not an originally shared image basename in the same directory: " + str(path))
        m.checked(path)

    def check_static(self, path, group):
        self.validate_parents(path)
        actual = m.ident(m.low.regular(path))
        need(nonlink(actual) == nonlink(group["identity"]), "Alias content identity/size/mtime/attributes changed: " + str(path))
        return actual

    def reconcile(self, group, hashes=None):
        key = pair(group["identity"])
        wanted = self.expected_names(group)
        if not wanted:
            need(all(Path(path) in self.removed for path in group["target_paths"]), "Unexplained missing alias group")
            self.observations[key] = dict(observed_links=0, surviving_paths=0)
            return
        sample = sorted(wanted, key=lambda path: str(path).casefold())[0]
        for attempt in range(3):
            before = self.check_static(sample, group)
            names = set(m.hardlink_names(sample))
            need(wanted.issubset(names), "An original or previously accepted alias disappeared: " +
                 json.dumps(sorted(str(path) for path in wanted - names)))
            additions = names - wanted
            for path in additions:
                self.validate_addition_path(path, group)
            for path in names:
                self.check_static(path, group)
            if additions:
                with sample.open("rb") as stream: need(stream.read(4) == b"DDS ", "Shared source image is not a DDS file")
                # Every name was just checked against the same original file ID.
                # Link additions do not excuse any content SHA change.
                need(digest(sample) == group["sha256"], "New live alias content SHA differs")
                self.additions[key].update(additions)
                wanted.update(additions)
            after = self.check_static(sample, group)
            need(after["links"] >= before["links"], "Alias count decreased during enumeration")
            if before["links"] == after["links"] == len(names):
                need(names == self.expected_names(group), "Current alias set has an unaccounted change")
                if hashes is not None:
                    if key not in hashes: hashes[key] = digest(sample)
                    need(hashes[key] == group["sha256"], "Alias group content SHA changed")
                    self.check_static(sample, group)
                serialized = ("\n".join(sorted((str(path) for path in names), key=str.casefold)) + "\n").encode("utf-8")
                self.observations[key] = dict(observed_links=len(names),
                    surviving_paths=sum(not m.inside(path) for path in names),
                    findnames_utf8_sha256=hashlib.sha256(serialized).hexdigest())
                return
        raise RuntimeError("Live aliases did not stabilize within three complete enumerations")

    def validate_file(self, row, hashes=None):
        path = m.checked(Path(row["path"]))
        actual = m.ident(m.low.regular(path)); key = pair(row["identity"])
        group = self.groups.get(key)
        if group is None:
            need(actual == row["identity"], "Unrelated protected file metadata changed: " + str(path))
        else:
            need(nonlink(actual) == nonlink(row["identity"]), "Original file metadata changed: " + str(path))
            expected_links = row["identity"]["links"] - self.removed_counts[key] + len(self.additions[key])
            if actual["links"] != expected_links:
                need(actual["links"] > expected_links, "Original or accepted alias link count decreased")
                self.reconcile(group, {})
                actual = m.ident(m.low.regular(path))
                need(nonlink(actual) == nonlink(row["identity"]) and
                     actual["links"] == row["identity"]["links"] - self.removed_counts[key] + len(self.additions[key]),
                     "File changed after complete alias reconciliation")
        if hashes is not None:
            if key not in hashes: hashes[key] = digest(path)
            need(hashes[key] == row["sha256"], "Original file content SHA changed: " + str(path))
            after = m.ident(m.low.regular(path))
            need(nonlink(after) == nonlink(row["identity"]), "Original file changed while hashing")
            if after["links"] != actual["links"]:
                need(group is not None and after["links"] > actual["links"], "Unrelated link change while hashing")
                self.reconcile(group, {})
        return path

    def removed_name(self, path, row):
        need(path not in self.removed and str(path) in self.groups[pair(row["identity"])]["target_paths"], "Unexpected removed name")
        self.removed.add(path); self.removed_counts[pair(row["identity"])] += 1

    def verify_all(self, hashes=None):
        for group in self.groups.values():
            self.reconcile(group, hashes)

    def addition_records(self):
        return [dict(device=key[0], file_id=key[1], sha256=self.groups[key]["sha256"],
                     original_links=self.groups[key]["identity"]["links"],
                     added_paths=sorted(str(path) for path in paths), **self.observations.get(key, {}))
                for key, paths in self.additions.items() if paths]

    def reclaimable_bytes(self):
        return sum(group["stored_bytes"] for key, group in self.groups.items()
                   if not group["surviving_aliases"] and not self.additions[key])

def preflight(plan, inventory, protection, diagnostics, seed=()):
    need(m.replacement_audit() == plan["replacements"], "Replacement pair changed")
    current_tree(inventory)
    state = LiveAliasState(inventory["groups"], seed)
    hashes = {}
    for row in inventory["files"] + protection["files"]: state.validate_file(row, hashes)
    print("READ_ONLY_FOLLOWUP=original-files-and-content-SHA-pass", flush=True)
    state.verify_all(hashes)
    need(m.sessions_audit() == protection["sessions"], "Candidate sessions/saves changed")
    users = m.user_save_audit()
    need(users["count"] >= protection["user_saves"]["count"], "Protected user save set shrank")
    m.request_audit(); processes = m.process_audit()
    for row in diagnostics["originals"]:
        raw = base64.b64decode(row["content_base64"], validate=True)
        need(len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"] and
             m.inside(Path(row["path"])) and Path(row["path"]).read_bytes() == raw, "Original diagnostics drifted")
    # Recheck exact target membership after all nonmutating preflight work.
    current_tree(inventory)
    return state, users, processes

def main():
    need(not any((OUT / name).exists() for name in
         ("plan.json", "application-started.json", "retired.json", "application-failed.json", "unlink-journal.jsonl")),
         "Follow-up outputs already exist; no replay")
    m.checked(OUT)
    original, inventory, protection, diagnostics = load_original()
    need(m.replacement_audit() == original["replacements"], "Replacement pair changed")
    state = LiveAliasState(inventory["groups"])
    changed_groups = 0
    for group in inventory["groups"]:
        path = Path(group["target_paths"][0])
        actual = m.ident(m.low.regular(path))
        need(nonlink(actual) == nonlink(group["identity"]), "Original sample metadata changed: " + str(path))
        if actual["links"] != group["identity"]["links"]:
            need(actual["links"] > group["identity"]["links"], "Original alias count decreased: " + str(path))
            state.reconcile(group, {})
            changed_groups += 1
    processes = m.process_audit()
    scripts = {name: dict(path=str(OUT / name), sha256=digest(OUT / name)) for name in ("prepare.py", "apply.py")}
    plan = dict(schema=SCHEMA, status="READY_FOR_ROOT_REVIEW_NO_DELETION", created_utc=datetime.now(timezone.utc).isoformat(),
        project=str(ROOT), targets=original["targets"], original_plan=dict(path=str(ORIGINAL / "plan.json"), sha256=ORIGINAL_PLAN_SHA),
        original_ledgers={key: original[key] for key in ("inventory", "protection", "diagnostics")},
        scripts=scripts, policy=POLICY, accepted_live_alias_additions=state.addition_records(),
        target_file_count=original["target_file_count"], protected_file_count=original["protected_file_count"],
        protected_user_saves=protection["user_saves"]["count"], protected_user_saves_verified_in_this_prepare=False,
        automated_test_saves=original["automated_save_disposition"]["count"],
        prepare_validation_scope="Original plan/code/ledger hashes, replacement reports, current process snapshot, every group link count, and complete FindNames/per-alias identity/content SHA for changed groups only.",
        full_preflight_required_before_delete=True, group_metadata_samples_checked=len(inventory["groups"]),
        changed_link_groups_reconciled=changed_groups,
        original_surviving_aliases=original["surviving_alias_path_count"],
        accepted_added_aliases=sum(len(paths) for paths in state.additions.values()),
        estimated_reclaimable_file_storage_bytes=state.reclaimable_bytes(), logical_bytes=original["logical_bytes"],
        processes=processes, volume_free_bytes_at_plan=shutil.disk_usage(ROOT).free,
        contract=["Original plan, ledgers, scripts and failed preflight evidence remain unchanged.",
                  "All original target names/tree/content/metadata and external aliases must remain identical.",
                  "Only positive same-file-ID DDS aliases under the exact live EA session source_assets/textures paths are admitted.",
                  "Preparation reuses the SHA-locked original ledgers; apply MUST perform full tree/file SHA/protection/user-save/diagnostic validation before any deletion.",
                  "Every addition is enumerated and checked; before unlink any changed link count triggers full group reconciliation.",
                  "After deletion all original surviving names and every admitted new name must still exist with original content and metadata.",
                  "Root reviews this new plan/code SHA before one exclusive apply; no live process is stopped."])
    ref = write_new("plan.json", plan)
    print(json.dumps(dict(status=plan["status"], plan=ref, files=plan["target_file_count"], protected=plan["protected_file_count"],
        user_saves_in_original_ledger=plan["protected_user_saves"], full_preflight_required_before_delete=True,
        added_aliases=plan["accepted_added_aliases"],
        reclaimable_bytes=plan["estimated_reclaimable_file_storage_bytes"]), ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
