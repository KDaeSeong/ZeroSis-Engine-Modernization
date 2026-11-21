"""Read-only preservation index for the private Build intermediate cleaner."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

INTERMEDIATE = r'\.(obj|o|pch|ipch|ilk|tlog|pyc)(["\\\s]|$)'
HASH = re.compile(r"^[0-9a-fA-F]{32,64}$")
SCOPES = {
    "unreferenced_final_UI_host_object_files_only",
    "unreferenced_nonfrozen_compiler_intermediates_in_private_Build",
}


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_text(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def collect(root: Path):
    build_prefix = os.path.normcase(str(root / "Build")) + os.sep
    references = set()
    documents = []
    ledgers = []

    def add(path):
        if not isinstance(path, str) or not os.path.isabs(path):
            return
        full = os.path.normcase(os.path.abspath(path))
        if full.startswith(build_prefix):
            references.add(full)

    query = subprocess.run(
        ["rg", "-l", "-i", "--hidden", "--no-ignore", "--glob", "*.json",
         INTERMEDIATE, str(root)],
        capture_output=True, encoding="utf-8", check=False,
    )
    if query.returncode not in (0, 1):
        raise RuntimeError(query.stderr)
    for name in query.stdout.splitlines():
        document = Path(name)
        raw = document.read_bytes()
        text = read_text(raw)
        if not re.search(r"sha256|sha_256|md5|hash", text, re.I):
            continue
        node = json.loads(text, object_pairs_hook=unique_pairs)
        relative = document.relative_to(root).parts
        if (len(relative) == 4 and relative[0] == "evidence" and
                relative[1] in ("build_tidy", "intermediate_tidy") and
                relative[3] == "cleanup.json"):
            if not isinstance(node, dict) or node.get("scope") not in SCOPES:
                raise ValueError(f"Unrecognized cleanup ledger: {document}")
            node.pop("candidates", None)
            node.pop("removed", None)
            ledgers.append(str(document))
        pending = [node]
        while pending:
            current = pending.pop()
            if isinstance(current, list):
                pending.extend(current)
            elif isinstance(current, dict):
                if any(str(k).lower() in ("sha256", "sha_256", "md5", "hash")
                       and isinstance(v, str) and HASH.fullmatch(v)
                       for k, v in current.items()):
                    add(current.get("path"))
                for key, value in current.items():
                    if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value):
                        add(key)
                    if isinstance(value, (dict, list)):
                        pending.append(value)
        documents.append({"path": str(document), "sha256": hashlib.sha256(raw).hexdigest()})
    return {"references": sorted(references), "documents": documents,
            "deletion_ledgers": ledgers}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args.root.resolve()), ensure_ascii=False, separators=(",", ":")))
