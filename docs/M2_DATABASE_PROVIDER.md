# Database x64 provider: bounded native component verified

2026-09-24: three AMD64 objects produce a real DLL and import library (113 exports after the explicit Results assignment export).
All 41 current GameCore database imports have exported method bodies and import
members. The actual seven-provider GameCore link changes from 113 to 72 unresolved
symbols, with no additions; no GameCore DLL is generated or loaded.

Five original-x86/candidate-x64 trace pairs match exactly, including logger text,
return values, Unicode, type conversions and 1,024 six-column rows. Both architectures
write a 257-row database; both readers load each file read-only and run integrity_check.
The two files are byte-identical in this fixture and remain unchanged by all four reads.
The candidate fixes the original double-query crash, passes 82 lifecycle/bounds/key
checks, and passes 131,460 assertions in a fresh process with eight workers, 64 separate
connection lifetimes and 32,768 inserted rows. These are native component observations,
not gameplay, full-save compatibility or measured engine speedup.

## Required behavior and boundaries

Implement the SDK Connection, Results, SingleResult and ResultsCache contracts as a real
AMD64 DLL with a matching import library. The current GameCore compilation imports 41
database methods. Its objects and this provider must use the same ported SDK headers
and /MD runtime. The original SDK/game files and installed MODS remain unchanged.
No game or GameCore is loaded by component tests. Stage is a review bundle, never a
game deployment. Mod IDs, schemas, saved keys, balance and user databases are unchanged.

SQLite 3.7.17 is deliberately pinned to isolate architecture/wrapper changes from SQL
version changes. Its actual original runtime source ID matches the official release:
https://www.sqlite.org/releaselog/3_7_17.html . This is a compatibility baseline, not a
claim of an up-to-date database library. A maintained SQLite upgrade needs its own
SQL/schema/ordering regression gate before adoption.

## Actual original observations

The isolated VC9 executable loads a verified copy of the original database DLL and its
Lua dependency after checking their direct imports; neither imports GameCore.
Only owned in-memory databases are used by the first probes.

- Open's default flags=0 fails. READWRITE|CREATE succeeds.
- Column names are case sensitive. Duplicate names select the last column.
- Release retains cached column positions; attaching another command clears them.
  Projection strings are owned copies, and Results copies reprepare the SQL without
  copying bound values or the current cursor position.
- ColumnTypeName describes the current value, not the SQL declared type. The special
  bool type requires the exact lowercase declared type `boolean`.
- GetBool uses a 32-bit integer test, or the first text byte t/T. Real values are false.
- SingleResult steps immediately on attachment. Reset clears bindings only after a
  successful sqlite reset; TryReset clears even after constraint failure.
- TryExecute returns true for SQLITE_CONSTRAINT and SQLITE_ABORT. Execute returns
  true only for SQLITE_DONE; Step returns true only for SQLITE_ROW.
- BeginTransaction/EndTransaction are SAVEPOINT _ / RELEASE _. The other Begin variants
  require CommitTransaction. RollbackTransaction is a complete ROLLBACK.
- TotalChanges actually returns sqlite3_changes (last statement), not total_changes.
- The boolean FK-validation argument does not reject SQL NULL in the observed case.
- The original double SelectAt overload passes a double to a `%d ... %s` format and
  crashes with access violation for a valid 3.0 query. Candidate must fix it with binding.

## Acceptance gates

1. Pinned official source and native AMD64 DLL/import library; no stub symbols.
2. Same-source original-x86/candidate-x64 result/log/return comparisons for valid cases.
3. Explicit candidate tests for original defects, bounds and the tested ownership paths.
4. Independent-connection concurrency with barriers and reproducible final rows.
5. GameCore link delta, export/map provenance, full input hashes, Stage integrity.

## Scope, differences and remaining work

The live-command registry detaches prepared Results when their Connection is closed or
destroyed. Its shared bookkeeping is synchronized; operations on one Connection or
Results object still require caller serialization even with OPEN_FULLMUTEX. SQLite
initialization uses call_once. The protected-owner-page test destroys a connection,
makes its storage inaccessible, and then operates on and destroys three detached
results, including a copy and a cached result.

Candidate fixes use bound double values, quoted identifiers, bounded-length SQL error
logging, UTF-16 length overflow rejection, and full-tuple composite foreign-key checks.
The memory statistics diagnostic uses a new format. Results now declares an explicit copy-assignment method in the x64 SDK. It prepares
a fresh statement, projection and column map, then swaps ownership without allocating.
Self-assignment preserves the current cursor and bindings. Other assignment follows
the original copy constructor: SQL is reprepared with cleared bindings and a fresh
cursor. If preparation fails, it throws and keeps the old destination.

A separate fault DLL reuses the exact three production objects and overrides C++ and
SQLite allocation only in that test build. It passes 551 checks covering same/different
connections, empty/prepared sources, self-assignment, schema invalidation and owner
closure. All 30 injected failures (14 C++, 16 SQLite) preserve the prior destination;
four full allocation sequences succeed. Map evidence proves the replacement allocator
binding, and the production export table contains no fault controls. GameCore attempt
015 recompiles all 161 units against 480 patches in 61 SDK files; object and saved
layouts remain unchanged.

The new wrapper and both x64 harnesses compile with /W4 /WX without warnings. The
unchanged SQLite compatibility source has three reviewed /W3 warnings: C4996 at its
GetVersionExA call and two C4101 unused authorization variables. Pointer truncation
warnings are errors in this build. This does not clear the separate GameCore warning
inventory or modernize SQLite itself.

Three frozen copies of the 2026-09-07 game caches now pass original-x86/candidate-x64
read comparisons: 748 tables, 188,675 rows and 1,116,126 values. Each table hashes
ordered row identifiers, typed getter results and full SQL hex bytes (including embedded
NUL and blob content). All six native readers pass integrity checks and produce equal
traces and SHA-256 digests. Original caches are never opened by a harness; their hashes
are checked before and after copying and execution. The frozen copies remain sealed
inputs, while the original paths are historical provenance and may change in a later
game session. This is historical cache-read coverage, not fresh-game or SQL-write proof.

Still pending: game/mod SQL mutation corpus, full game cache/save compatibility, allocation-failure hardening outside
the tested Results copy/assignment paths, shared-connection concurrency policy,
BinaryIO/XMLSerializer/Lua exposure/host consumers, and a complete engine build plus
separately authorized fresh-game runtime checks. Closing 41 imports alone does not
close these gates or establish gameplay compatibility.

## Traceable artifacts

- Source: Source/Providers/Database/SdkDatabase.cpp, SdkDatabaseResults.cpp and two support headers.
- Tests: Tests/sdk_database_trace.cpp, sdk_database_hardening.cpp, sdk_database_assignment.cpp and sdk_database_fault_allocator.cpp.
- Assignment evidence: evidence/database/assignment/conformance.json and allocator/SQLite fault logs.
- Cached content: evidence/database/corpus/conformance.json, six native traces, frozen fixture hashes; tools/verify_database_corpus.py reproduces it and database_corpus_evidence.py validates its scope and artifacts.
- Build: Build/Database/x64/ZeroSisDatabase_x64.dll and ZeroSisDatabase_x64.lib.
- Native evidence: evidence/database/conformance.json, probe_comparison.json and reference/candidate logs.
- Link evidence: evidence/database/link_delta.json; unresolved 113 -> 72, exactly 41 resolved and zero added.
- Review copy: Stage/GameCore_x64/Providers/Database; no installed-game deployment.
