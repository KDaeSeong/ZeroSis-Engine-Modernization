# M7 retail save boundary

## Current boundary

Retail `.Civ5Save` compatibility still needs an outer-container/SDK-state adapter. `Source/Host/RetailSaveHeader.h` reads the first metadata prefix and `RetailSavePregame.h` now locates a supported uncompressed BNW Pregame boundary. These readers, the bounded `RetailSaveInflate.h` decoder and the `RetailSaveState.h` Game/Map-prefix inspector are separate components and are not integrated into the prepared Host. The active Host still writes and reads a private `.zssave` envelope. `Source/Host/NativeSaveArchive.h:44-45` explicitly distinguishes that envelope from a retail schema; its own framing and checksum do not prove retail compatibility. `GeneratedHostInterfaces.h:142-143` also leaves the original engine `SaveGame/LoadGame` requests unsupported.

`Source/Host/SdkGameSave.h:33-67` serializes Pregame, Game, Map, supporting data, Team, and Player streams into separate private sections. `SdkGameRestore.h:9-55,80-90` feeds them back to the SDK. The relevant source directory for the BNW provider is **`Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2`**, not its sibling `CvGameCoreDLL` directory. BNW entry points are `CvGame.cpp:9238,9468` (Game) and `:9457,9605` (supporting data), `CvMap.cpp:1362,1424`, `CvTeam.cpp:6814,6987`, `CvPlayer.cpp:21790,22356`, and `CvDllPreGame.cpp:511,1068`. These are component stream implementations, not the retail container writer.

BNW `CvGame.cpp:75` writes Game version **1**, while its `CvPreGame.cpp:3156-3158` writes archive version **6** and `:458-461` writes slot-hints version **3**. The sibling base-game implementation instead uses Game version 11 / Pregame archive version 5; Expansion 1 uses Game version 13. These numbers are also distinct from the outer metadata versions 7/8. Mixing them would select the wrong wire reader.

## Implemented metadata prefix

`RetailSaveHeader::ParsePrefix` consumes the signature, outer save version, raw game version/build, turn, mode, seven civilization/map strings, DLC records and mod records. Supported outer versions are 7 and 8. Strings, record counts and total prefix bytes are bounded before reads or allocations. On-disk DLC IDs, mod IDs, auxiliary words and raw string bytes remain intact. UTF-8 validity and the meaning of auxiliary words are not inferred.

The returned `consumedPrefixBytes` is only the end of these metadata records. It is **not** the start of compression, not a whole-file validation, and not an SDK state restore. This metadata-only API leaves later bytes unparsed; the separate Pregame component below handles one verified uncompressed layout. Complete compressed state is not yet framed or restored; the bounded Game/Map-prefix inspection below covers only its beginning.

The immutable reference is [js-civ5save commit 858ce8532725f634e64fa8acaf355aa8e50829bf](https://github.com/bmaupin/js-civ5save/tree/858ce8532725f634e64fa8acaf355aa8e50829bf). Exact property/string/list source blobs are retained under `evidence/retail_save_container/header_prefix/upstream`, with `upstream.json` recording identity. The MIT notice is `Source/Host/RetailSaveHeader.LICENSE.txt`.

Two public upstream fixture blobs were verified in memory. Only their metadata prefixes, **718 and 1,100 bytes**, are retained under `Tests/Fixtures/RetailSaveHeader`; no complete save or user save was retained. `fixtures.json` records their origin and hashes. `Tests/retail_save_header.cpp` checks independent upstream expectations, byte preservation, all prefix truncation boundaries, budgets and 2,048 bounded mutations. Actual AMD64 `/O2` and `/Od /RTC1` results, compiler dependency proof and imports are in `evidence/retail_save_container/header_prefix/build_result.json`. This is a pure component result; the prepared B11 Host was not rebuilt or executed.

## Uncompressed Pregame boundary component

`Source/Host/RetailSavePregame.h` reuses the metadata reader and walks player-info, slot-hints **3**, Pregame archive **6**, world-info **1/2**, and an eight-byte compression descriptor (format **1/2**, chunk-size **65,536**). It returns contiguous spans into the caller's input and a body offset. Per-string, per-array, total-array and total-prefix budgets are checked before reads or count multiplication. A prefix may be supplied without the compressed body: a successful prefix parse is not a successful save load.

The field sequence is grounded in active BNW `CvPreGame::saveSlotHints/writeArchive` and `CvInfos` serializers, plus pinned public wire references. `CvBaseInfo` has an ID followed by **eight length-prefixed strings**, including fields for which the public Go reader assumes an empty string. The retained original utility-library conformance proves **GameTypes uses one byte; GameMapTypes uses four**. Their C++ declarations alone do not establish wire width. Selected original-library/map/output/source identities were freshly rehashed in `pregame_boundary/source_conformance.json`; those older enum tests were not rerun or claimed as full-save proof.

The public `1.0.3.279.Civ5Save` example has metadata end **718**, player-info **76** bytes, slot-hints **3,098** bytes, archive **7,091** bytes and descriptor **8** bytes. Ordered parsing reaches compressed-body offset **10,991**; no search for a zlib signature is used. Only its disjoint **10,273-byte** uncompressed tail is retained. The public `issue8.Civ5Save` example has an archive word **0** at offset **5,522**; its disjoint **4,426-byte** tail ends after that word and is an explicit unsupported-layout rejection witness. Its meaning is not inferred as a working SDK version-0 contract. Neither complete save nor compressed body is retained, and the existing metadata fixtures are reused.

`Tests/retail_save_pregame.cpp` checks the supported public boundary, the unsupported witness, 16 independent synthetic combinations with arbitrary nonempty base-info strings, every prefix truncation (15,149 positions), budgets, typed errors, magic-byte decoys and 2,048 bounded mutations. Actual AMD64 `/O2` and `/Od /RTC1` both pass **56,133 checks**. These counts are per build mode, not distinct gameplay tests. The strengthened test oracles validate span offsets before unsigned subtraction and distinguish metadata/Pregame truncation errors. `pregame_boundary/build_result.json` records real compiler inputs, PE architecture/imports and results. Superseded component binaries and compiler intermediates have been retired with hash/identity ledgers.

These results do **not** establish compressed chunk framing, complete deflate termination/checksums, SDK state restoration, original save writing, retail/mod compatibility or UI/gameplay behavior. Unsupported layouts must remain explicit failures before live state is modified. No Host/GameCore/window or user save was accessed, and prepared runtime R11 remains unchanged.

## Bounded compressed-body inspection

`Source/Host/RetailSaveInflate.h` now inspects a single zlib stream with explicit input/output byte budgets, bounded decoder allocations and a call budget. `DecodeComplete` requires `Z_STREAM_END`, a verified Adler trailer and no trailing bytes. `Inspect` deliberately distinguishes incomplete output and a `NonFinalEmptyStoredBlockBoundary`; neither is permission to restore a save. It uses an unmodified inflate-only subset of official [zlib 1.3.2, commit da607da739fa6047df13e66a2af6b8bec7c2a498](https://github.com/madler/zlib/tree/da607da739fa6047df13e66a2af6b8bec7c2a498): 14 files, 246,003 bytes, with the zlib license and exact Git blob receipt retained in `Source/ThirdParty/zlib-1.3.2`. `Z_SOLO`/`NO_GZIP` exclude default heap allocation, gzip, unrelated archive code and large CRC tables. Decoder allocations use bounded callbacks; output bytes have a separate configurable limit. The retained `/MT` component libraries are test baselines, not a Host provider or deployment.

The immutable public BNW blob was verified in memory and the existing metadata/Pregame prefix matched through offset 10,991. Its **407,078** compressed bytes were passed to the two native test executables through a binary memory pipe; no public save, compressed-body file or decompressed-body file was retained. Both AMD64 modes produce **9,762,327** bytes with SHA-256 `1fdc3cf2c0d1fa5859f6be202cc7654ff97835ffc67abe91301d1fbceb9a93db`, equal to the bounded independent Python result. Test-only Windows CNG computes the native output hash; the production decoder has no Windows UI dependency.

Actual `Z_BLOCK` events expose **20 blocks**, ending at bit **3,256,624** with all compressed input consumed. The last block is verified from its original bit position as nonfinal stored, `LEN=0`/`NLEN=0xffff`, zero output delta and exact byte-aligned end. This is stronger than checking the suffix `0000ffff`; it is compatible with synchronization/full-flush output but does not prove which compressor operation was used. A file cut at an earlier genuine empty stored boundary can receive the same incomplete classification. The public result has `finalDeflateBlockSeen=false`, `adlerTrailerVerified=false` and strict decoding correctly rejects it. No marker/checksum was invented or appended.

The available original SDK headers and the static FireWorks archive did not establish a retail finish/trailer contract. Public symbols and anonymous-object disassembly are insufficient to justify accepting a missing trailer as a complete original save. `compression/upstream_contract_review.json` records that limit. The first decompressed SDK word is 1; this is not proof of subsequent SDK stream boundaries, whole-container completeness or restoration.

`Tests/retail_save_inflate.cpp` checks 16 independent vectors, hand-written RFC stored-block cases, genuine earlier boundaries, magic-byte decoys, dictionaries, checksums, trailing input, resource limits and 2,048 deterministic mutations. **19,527 strict truncations** reject; diagnostic inspection is allowed to return explicitly incomplete prefixes. Actual `/O2` and `/Od /RTC1` each pass **51,030 checks** and match the public SHA. Mutation return counts mean inspection returned, not that a save was accepted. Compiler dependencies, imports, exact subprocesses and cleaned object identities are recorded in `compression/build_result.json`. These native results do not prove the SDK state layout, original save writing or retail gameplay.

## Inflated Game and Map-prefix framing

`Source/Host/RetailSaveState.h`, `RetailSaveStateWire.h`, `RetailSaveGameFront.h` and `RetailSaveGameTail.h` frame already inflated bytes without calling the SDK or accessing files. The latest BNW profile consumes Game v1, populated vote FreeLists, release RNG v1, replay v2, plot extras, Deals1/Deal3/TradedItem2, Religions4/Religion4/Beliefs2, Culture2/GreatWork3, Leagues5/League14 and its independently versioned resolution layers, Trade3, and the declared embedded-database bytes. Map1 follows in the public corpus; only its fixed fields and two conditional hashed resource arrays are consumed. `RetailSaveState` stops there; the `RetailSaveMap` component below additionally frames Plot, area and landmass records. Supporting placement and Player records remain unresolved; the later Team witness is described below. The private archive's section order is not asserted as the retail order.

Fixed player/team arrays have no count words. Hash zero has no following value. The victory-rank inner width is absent from the wire and is a **required explicit profile input**, not a hidden default of five. `CvGlobals` replaces its initial value from `NUM_VICTORY_POINT_AWARDS`. Framing cannot establish ruleset/type-hash compatibility; both approval flags remain false. Debug RNG, unsupported nested versions and profiles are explicit failures. Signed counts, per-array/aggregate counts, strings, prefix/input bytes, embedded-database bytes and map dimensions have bounded checks before multiplication or traversal. Reader limits are copied so temporary arguments cannot leave a dangling reference.

Source cross-review corrected an initially incorrect 22-entry limit on league-project contributions: `FStaticVector` can grow, and its boolean template parameter means POD, not fixed capacity. A 23-entry fixture now succeeds. The Trade matrix really does serialize 22 by 22 integers and six origin/destination yield pairs. Another existing SDK difference is retained as evidence: the victory writer uses special-unit count for its outer rows while its reader uses victory-info capacity. Our private writer is therefore not used as an independent retail oracle. That Game/Map-prefix stage changed no SDK serializer or save schema; the later vector-count ABI correction is described below.

The immutable public BNW corpus, inflated to **9,762,327** bytes with the previously verified SHA-256, was passed through binary stdin only. Ordered parsing returns Game `[0,11254)`, embedded DB `[8182,11254)` (**3,072 bytes**), and Map header `[11254,11984)` (**730 bytes**, **40 by 24** plots). The next offset is a plot-data start, not the end of Map or a complete save. The exact declared database span independently has a valid SQLite header and three 1,024-byte pages and was opened only in memory. It contains no `NUM_VICTORY_POINT_AWARDS` value, so the test profile's width five remains an explicit assumption, not verified ruleset compatibility. No signature search determines any boundary. No public save, inflated body or database file is retained.

`Tests/retail_save_state.cpp` uses eight independent empty/populated fixtures with explicit widths 0/1/5/7, literal minimal-byte expectations, populated nested records, zero hashes, decoy SQLite/Map bytes, exact/short budgets, every synthetic-prefix truncation, invalid versions/bools/free lists and 2,048 deterministic mutations. Actual AMD64 `/O2` and `/Od /RTC1` each pass **41,613 checks**, including **12,999 truncations**; these are component checks, not gameplay tests. The 731 returned mutation inspections never claim save acceptance. Compiler dependency proof consumes all four production headers and no SDK; executable imports are only `kernel32.dll`. `game_state/build_result.json` records inputs, commands and the retired compiler objects. The current Host and prepared R11 remain separate, unmodified by these components, and unexecuted.

The public compressed input still ends at a nonfinal empty stored-block boundary, without a final block or verified Adler trailer. Successful Game/Map-prefix inspection does not resolve the original finish contract or authorize restore. Full Map and subsequent object framing, ruleset compatibility, original save writing and retail/candidate reopening remain required.

## Complete Map framing component

`RetailSaveMap.h`, `RetailSavePlot.h` and `RetailSaveMapTail.h` extend the inspected Game/Map prefix through every Plot v7, Area v1 and Landmass v1 record and the final AIMapHints word. The bounded cursor preserves the Game prefix's consumed record budget. All offsets refer to inflated input. This produces a complete Map span without SDK calls, ruleset/type-hash resolution or runtime mutation. It is not a whole-save approval or restoration.

The SDK's Plot arrays use REALLY_MAX_PLAYERS/TEAMS **80**, while Game arrays use 64. Each Plot includes short coordinates/yields/visibility, raw char fields, four DWORD reveal words, fixed `short[80][1]` invisibility with no count, optional script bytes, build presence plus a separately counted hash/short list, unit-ID pairs and archaeology v2. No native struct padding is consumed. Minimum Plot size is **1,569 bytes**. Area's first five arrays use 80 rows; target-city/yield loops use **64** rows, giving a **3,718-byte** minimum. Landmass is **22 bytes**. Both Map-tail containers use checked FreeListTrashArray metadata/links/IDs. Improvement hash 0 and 0xffffffff omit their value. Nonzero build hashes have a two-byte short; the SDK reader's unknown-hash fallback instead reads four bytes, an existing mismatch that this framing reader does not reproduce. Unresolved-hash SDK restore safety remains unverified.

Original and ported SDK Map, Plot, Area and Landmass writer bodies match after CRLF normalization; `map_state/writer_body_comparison.json` records those body identities. The pinned public Go reader stops at MapHeader and is not presented as a full-Map oracle. `source_conformance.json` records source identities and wire widths.

In the same immutable **9,762,327-byte** diagnostic output, both native modes frame all **960 plots**, **41 areas** and **26 landmasses**. Map is `[11254,1695150)` (**1,683,896 bytes**), plots `[11984,1518416)`, areas `[1518416,1694422)`, then landmasses and the final four-byte hint. The Map component alone leaves **8,067,177 following bytes unparsed**; the later Team witness below narrows that remainder without inferring a private section order. The Map span SHA-256 is `6a5d08789715c35d9eecd43b98dbc91fa9356a1d535eaa9dd808dc974799ec77`. Input SHA and the original nonfinal deflate termination are unchanged. Public save/body/database files are not retained.

`Tests/retail_save_map.cpp` reuses the earlier independent Game fixture writer without copying or modifying it. Four minimal/populated cases exercise 80/64 widths, hash sentinels, unequal outer/inner build counts, scripts with decoy bytes, populated area/landmass free lists, literal minimum-byte expectations, exact/short limits, invalid versions/bools/counts, all synthetic Map byte truncations and 2,048 mutations. Actual AMD64 `/O2` and `/Od /RTC1` each pass **51,927 checks**, including **12,612 truncations**. Returned mutated inspections do not approve saves. Compiler dependency evidence includes all seven production headers and no SDK; executables import only `kernel32.dll`. Objects and resolved failed/interrupted attempts are retired with small hash/identity ledgers. These are separate component tests, not original UI/gameplay proof or current Host integration.

The original compression finish contract, unsupported layouts, following state streams, ruleset compatibility, SDK restore/save wiring, original save writing and retail reopening remain required. Native Host/GameCore/window execution is still held during the user's original-game test.

## SDK vector-count correction and public Team witness

The x64 `CvInfosSerializationHelper.h` previously passed `std::vector::size()` directly to `FDataStream` in four writer overloads. Original Win32 `size_t` is four bytes; native x64 `size_t` is eight, while all four readers consume a four-byte `uint`. `WriteDataArray`, `WriteHashedDataArray`, `WriteTypeArray` and `WriteHashedTypeArray` now convert through `CvChecked::Integer<uint>` before the first stream write and use that same count for iteration. Values above `UINT_MAX` fail before output; payloads, IDs, keys and schemas are unchanged. The working port recipe and manifest reproduce the corrected header exactly. The current Host and frozen R11 were not rebuilt or promoted.

`Tests/sdk_type_array_count.cpp` authenticates exact extracted template bodies and uses the actual archived x86 SDK stream and the retained x64 stream provider. Only type/hash resolution uses deterministic test hooks; real database IDs are not verified. Twelve empty/single/populated cases per writer family compare literal little-endian counts, complete payloads, following sentinels and EOF positions. The original x86 run passes **188 checks** with count width four. Both x64 `/O2` and `/Od /RTC1` pass **28,972 checks**: original and pre-fix bodies produce eight-byte negative controls; the corrected bodies produce four bytes with identical payloads. The actual narrowing helper accepts `UINT_MAX` and rejects `UINT_MAX+1`, without allocating a giant vector. C++14 matches the retained SDK's legacy declarations; VC9's encoding-only C4819 is suppressed without rewriting its original header. Full SDK translation units have not been recompiled for this change.

`RetailSaveSupporting.h` provides only an explicitly supplied-offset framing API for **276 + 4 * plotCount** bytes: parent v1, Barbarians v1, two unprefixed short arrays, Goody v1 and 22 by 3 signed integers. Its independent fixtures cover plot counts 0/1/960, nonzero starts, valid negative payloads, budgets, versions and **14,094 truncations** in each x64 mode. This does not establish its retail placement.

On the same authenticated public input, `RetailSaveMap` first recomputes the full Map end using the explicit, still ruleset-unverified profile five. `RetailSaveTeam.h` then frames **64** Team v1/Techs v1 records with IDs **0 through 63** from **1695150** to **2309550**, spanning **614,400 bytes** and **41,792 counted array records**. Both native modes pass **29,044 checks** including this witness. There is no signature/version scanning. Team project-art row lengths come from preceding project counts; unresolved framing hashes are rejected rather than guessed. Supporting is rejected both directly after Map and at the obtained Team end. Therefore the private archive's Map/Supporting/Team order is not a retail oracle. **7,452,777 following bytes remain unframed**. Independent Team-specific synthetic/truncation/mutation coverage is recorded in the next section; this corpus witness does not replace it.

The public save, inflated body and embedded database are never retained as files. The original nonfinal compression termination, following Player/supporting state, unsupported layouts, ruleset compatibility, SDK restore, original save writing/reopening and actual UI/gameplay remain unresolved. `serialization/type_array_count/build_result.json` preserves exact inputs, real compiler/link evidence, commands and retired object identities. Prepared R11 still preserves B11's frozen graph and is not the latest working-source candidate. Host/GameCore/window execution remains held during the user's original-game test.

## Independent Team coverage and actual SDK syntax

`Tests/retail_save_team.cpp` independently constructs empty and populated Team v1/Techs v1 records with literal minimum-size and payload oracles. It exercises serialized IDs, fixed team/domain/yield widths, null/sentinel hashes, all technology columns, project counts and dependent art lengths, limits, invalid values, all prefix truncations of representative empty/populated structures and 2,048 deterministic mutations. Actual AMD64 `/O2` and `/Od /RTC1` each pass **19,282 checks** including **5,392 truncations**. Returned mutated inspections do not approve saves. Explicit count-field rows consume record budgets; fixed-width and derived project-art payloads remain bounded by input/prefix bytes. Original and ported Team/Techs writer bodies are equal after CRLF normalization; `team_state/source_conformance.json` records their identities. The earlier public 64-Team witness remains a separate input/corpus check, not a loader or ruleset approval.

The actual current x64 `CvTeam.cpp` translation unit and `Tests/sdk_vector_count_compile.cpp` both pass MSVC **`/Zs /Y-` syntax checks** using the real SDK headers. The latter explicitly instantiates all four corrected vector writer templates with `ResourceTypes` and no TestHooks. **155 project headers** were consumed and hash-checked against current sources/manifest. Syntax checks generate no object, PCH, linked library, DLL or game window. They do not establish full SDK code generation/link success or current Host integration. Compiler warnings are retained: CvTeam has C4819 **75**, C4091 **5**, C4996 **2**; the four-template probe has **66**, **5**, **2**, respectively. They concern encoding/ignored declarations/deprecated declarations; these are not reported as zero-warning builds. No pointer-width error was emitted. Exact commands, project includes and diagnostics are in `serialization/vector_count_syntax/build_result.json`.

At the sequential public Team end **2,309,550**, the first word is **16**, matching the retained `CvPlayer::Write` version. The source emits 209 four-byte scalar fields after the version; first bool is at relative **840**, Player ID at **864**, personality enum at **868**, and first vector count at **872**. The fixed observation gives ID **0** and vector count **6**. That initial observation established only source/prefix alignment. The later prefix reader below consumes the front and six nested states, while a complete Player and restore remain unsupported. `CvPlayerAI::Write` writes the whole base first, then its AI version one, so it is not a leading player tag. The generic STL vector count already uses checked u32 in the current x64 port and is not a new unresolved eight-byte-count defect. No version/signature scan or private archive ordering determines this boundary.

Player subobjects, ruleset/hash resolution, original container finish/write contracts, full SDK/Host rebuild, original save restore/reopen and actual UI/gameplay checks remain required. Original-game isolation and the prepared R11/B11 frozen inputs remain preserved. These component advances do not complete the full x64/multicore goal.

## Player prefix through GrandStrategyAI

`RetailSavePlayerPrefix.h`, `RetailSavePlayerFront.h`, `RetailSavePlayerAiEarly.h` and `RetailSavePlayerAiStrategy.h` now frame the Player v16 front and its next six nested states: Policies2 (PolicyAI1), Economic1, CitySpecialization2, Wonder1, Military1 and GrandStrategy1. All seven spans share one bounded Reader. The parser stops before DiplomacyAI; it does not frame a complete Player, PlayerAI, all players or a retail save, and performs no SDK mutation.

The front has a **1,028-byte** empty lower bound: version, 209 four-byte scalars, the actual bool/int mixture, ID at +864, then 26 int vectors, nine hash/int lists, two bool vectors and two narrow strings. PolicyAI always writes a weight after every hash, including zero; the six policy bool tables instead omit the bool only after zero. Economic exploration/goody tables use `FFastVector` u32 counts; purchase requests are three int32s. Military uses four unprefixed **63-entry** arrays, not 64 or 80. GrandStrategy has two **22-entry** arrays and an unprefixed priority array whose width comes from the ruleset. No native struct padding is consumed.

`RetailSavePlayerProfile` requires both the grand-strategy width and the initialized-building-catalog profile. There is no silent default, byte/version scan or inferred null catalog branch. Width zero is structurally allowed; above 4096 is an explicit inspector-profile rejection, not an asserted SDK limit. Full-prefix minimum size is **2407 + 4 * G** bytes. The public check explicitly uses G=4 and the earlier Game width five, with **ruleset compatibility still unverified**. Actual loading must obtain these widths/catalog conditions from validated rules, not from a plausible next version word.

`Tests/retail_player_prefix.cpp` builds four independent empty/populated cases with G=0/1/4/7, literal minimum/extents, nonzero starts, embedded string data, zero-hash policy weights, explicit-row budgets and boundary sentinels. Both AMD64 `/O2` and `/Od /RTC1` pass **30,623 checks**, **11,305 prefix truncations**, and **2,048 deterministic mutations** (845 structural returns, 1203 typed rejections). Returned mutations are not accepted game states. Invalid versions/bools/counts/profiles and exact/short input, prefix, array, aggregate and string limits are checked. Source dependency proof consumes the production headers, no SDK, and native imports are only `kernel32.dll`.

The same authenticated public diagnostic output is read sequentially as Game/Map, 64 Teams with ordered IDs, then Player ID **0**. Player prefix is **[2309550,2326136)**, **16,586 bytes**, with **2,551 explicit array rows**. The spans are front **10,349**, policies **2,993**, economic **489**, city specialization **26**, wonders **1,372**, military **1,153**, and grand strategy **204** bytes. The next exact word is the source's DiplomacyAI version **4**; that body and **7,436,191 remaining bytes** were unframed at this prefix stage; the next section records the subsequent extension. This is conditional prefix evidence, not approval of the compression finish contract, ruleset, Player restore or original save writing/reopening. Public save/body/database files are not retained.

`player_prefix/source_conformance.json` records source identities. The seven nested Write bodies and the Player front match Original/x64 after CRLF normalization. The full Player writer has one existing checked-u32 AIOperations-size difference outside this prefix; it is not falsely reported as byte-identical. Compiler objects were retired with size/hash/file-identity receipts. The current Host and R11 were not rebuilt or executed. Full SDK/Host integration, remaining Player state, actual original UI/gameplay and measured multicore behavior remain required for the overall goal.

## Player middle states through HomelandAI

`RetailSavePlayerAiMid.h` and its Diplomacy, ReligionTech and Tactical helpers extend the prior Player prefix by seven source-ordered nested states: DiplomacyAI4, PlayerReligions1, ReligionAI1, PlayerTechs1 (TechAI1), FlavorManager1, TacticalAI1 and HomelandAI1. A single bounded Reader preserves byte and declared-record budgets across them. It stops before MinorCivAI. Complete Player/CvPlayerAI, later players, ruleset compatibility and restore remain unsupported.

Diplomacy has exactly **71,856 bytes**, using serialized widths **22 major / 41 minor / 63 civilization players**, including **5,388 canonical bool bytes**. Its demand target is a **one-byte char**, not an int32. The logs are 1,320 records of eight bytes and 60 declarations of 21 bytes, without native padding; PlayerTypes in declarations uses the verified four-byte original codec. Version 4 is required. There are no on-wire counts in this fixed state, so its fixed rows consume the byte budget rather than the declared-count budget.

PlayerReligions writes two int32 scalars, despite the founding-religion field's `m_b` name. ReligionAI writes only its version. The **initialized tech catalog** is an explicit mandatory profile: the null branch silently omits seven hash arrays. Generic zero hashes omit their bool/int value; TechAI instead retains a weight even after hash zero. FlavorManager's signed count owns two unprefixed int columns. TacticalAI uses a u32 FStaticVector count and **24-byte** versioned temporary zones; their naval flag is an int32 and accepts nonzero integer values. HomelandAI is eight bytes. The combined empty lower bound is **71,944 bytes**; no technology/flavor width is guessed from a following version word.

`Tests/retail_player_ai_mid.cpp` independently writes empty, one-zone and populated thirteen-zone cases. The populated case deliberately exceeds the vector's capacity estimate of ten. Literal offsets exposed and corrected a three-byte fixture discrepancy before native execution. Both AMD64 `/O2` and `/Od /RTC1` pass **95,212 checks**, **72,463 byte-prefix cuts**, and **2,048 deterministic mutations** (725 structural returns / 1323 typed rejections). Every bool, nested version, invalid profile/count, exact/short byte and aggregate budget is tested. Structural returns are not accepted game states. Compiler warnings are rejected; actual dependencies consume all 16 required production headers and no SDK header. PE/import checks run before execution and permit only AMD64 PE32+ with `kernel32.dll`. Tests run hidden, at below-normal priority, without Host/GameCore or windows.

The authenticated public diagnostic stream advances from **2,326,136** to **2,403,477**, reading **77,341 bytes** and **724 declared rows**. The seven spans are Diplomacy **71,856**, player religion **12**, religion AI **4**, techs **5,137**, flavors **312**, tactical **12**, and homeland **8** bytes. The next exact word is MinorCivAI version **1**. Its body and **7,358,850 remaining bytes** were unread at the middle-state stage; the following section records the subsequent extension. Earlier Game width five, GrandStrategy width four and initialized building/tech catalogs remain explicit structural hypotheses, not authenticated ruleset compatibility. The original public compression finish/Adler contract is still unapproved.

`player_ai_mid/source_conformance.json` hashes eleven matching Original/ported writer bodies and the Player call segment. Native objects/setup were retired with identities and hashes; current test executables and small proof files are retained. No retail installation, MODS, user saves/settings or game processes were accessed. R11/B11, the default runtime and all full-game UI/gameplay/multicore/restore gates remain unchanged.

## Player late states and actual Traits count correction

`RetailSavePlayerAiLate.h` with Minor, Infrastructure and Traits helpers frames six more source-ordered Player states: MinorCivAI1 (Quest2), DealAI1, BuilderTaskingAI2, CityConnections1, DangerPlots1 and PlayerTraits19. It stops before Espionage0. It is still not a complete Player, PlayerAI, all-player stream, compatible ruleset or restore path. All spans share a bounded Reader and return approval flags false.

MinorAI requires exactly **22 initialized outer quest lists**, which are absent as a count on the wire. `RetailPlayerAiLateProfile::InitializedMinorQuests` is mandatory and never inferred from a plausible following version. The source has uncounted int[22][22], twelve int[22], six bool[22], two bool[80] and its final bool; minimum **3409 + 21Q** bytes. Each signed quest count charges declared rows; the capacity estimate of five is not a maximum. Builder uses a u32 FStaticVector count. City writes a u32 dimension D, interleaved raw-char cells of total **2D²** bytes and a four-byte city count read as signed. D is charged once as declared rows; its derived cells consume only byte budget. Original uint32 D² overflow is rejected before an O(1) bounded skip. Danger writes its player enum, allocated bool, signed map-grid count and uint32 values regardless of that flag. The public grid is compared with the already-framed Map's **960** plots.

Traits v19 has an empty minimum of **503 bytes**: 65 ints, 19 canonical bools, two four-byte enums, seven uncounted yield[6] columns, hash/int arrays, Maya choices, no-train flags, free units, combat columns, three counted vectors of unprefixed Firaxis::Array<int,6> rows and luxury areas. Generic zero hashes omit the value. The whole six-state empty minimum is **3955 bytes**. Independent empty/sparse/populated fixtures exercise seven quests (above the estimate), nonzero route matrices, false allocation with a populated danger grid, zero hashes, signed values and row counts. Both AMD64 modes pass **20,253 checks**, **4,520 byte-prefix cuts** and **2048 deterministic mutations** (681 structural returns / 1367 typed rejections). No returned mutation is approved as a game state. Production dependency evidence includes all 20 required headers and no SDK header; tests run hidden at below-normal priority, with PE/import checks before execution.

The authenticated public diagnostic stream now advances **[2403477,2421545)**, **18,068 bytes** and **1247 declared rows**. The spans are minor **3409**, deal **4**, builder **14**, connections **8204**, danger **3853**, and traits **2584** bytes. The next exact word is the source's **Espionage version 0**. **7,340,782 following bytes remain unframed**, including that observed four-byte version word. Game width five, strategy width four, initialized building/tech catalogs and initialized minor lists are structural hypotheses; the compression finish contract, full ruleset compatibility and retail restore remain unapproved. No public compressed/inflated save or embedded DB file is retained.

This investigation also corrected the actual working SDK writer. `CvPlayerTraits::Write` previously inserted native `.size()` for `std::vector<MayaBonusChoice>` and `std::vector<bool>`, producing **eight bytes on x64** where its reader consumes an int32. Its luxury-area `(int).size()` also narrowed unchecked. All three now pass `CvChecked::Integer<int>` **before the first stream write**, and write/iterate using those same checked counts. Values above **INT_MAX** are rejected before output. Valid payloads, IDs and version 19 remain unchanged. FreeTraitUnits, Builder and City containers are FStaticVector with an already-four-byte unsigned size; those writers were preserved. The port recipe reproduces the single changed SDK file exactly; source/recipe/manifest backups are changed-file gzip only.

`serialization/player_traits_count/build_result.json` binds exact extracted full writer bodies to actual x86/x64 SDK streams and native enum codecs, with explicit hash-resolution hooks and a uint-size free-unit shim. Original x86 passes **570 checks**; both x64 modes pass **1194 checks**, including **nine** oversized preflight rejections each. Three complete canonical writer/canary outputs match byte-for-byte across x86 and both x64 modes. The production Traits reader reaches the exact body end for all three canonical cases and rejects the exact end for all three legacy controls. Canonical wire comparison and oversized-count preflight rejection are component evidence, not actual ruleset/GameCore loading or complete save compatibility. `player_count_syntax/build_result.json` separately checks the actual full CvTraitClasses.cpp translation unit against 150 tracked headers, without code generation or linking; **78 existing legacy warnings** are recorded (71 encoding, five enum-declaration, two deprecated-library diagnostics). This is not a full SDK rebuild. Objects, duplicate/obsolete test outputs and setup files are retired with path/identity/hash receipts. R11/B11 and the default Host remain unchanged and do not include these working-source changes. Full original UI/gameplay, retail round trips and measured multicore behavior remain required.




## One complete PlayerAI wire object and the Player suffix

`RetailSavePlayerEnd.h` frames the real Army free list, every live Army v1,
all 20 factory operation types, the remaining Player v16 fields and the final
CvPlayerAI v1 word. Army formation slots contain three int32 values, including
the misleadingly named m_bStartedOnOperation. Operation inheritance is followed
exactly: an inherited serializer does not add another version. An outer map-key
and operation-body ID mismatch is observed, not silently repaired or rejected
as an extra wire rule. Object-reference integrity remains unverified.

The suffix contains replay-name strings, replay-value maps, vote/unit-cost
pairs, trimmed plot IDs, two counters, 64 conquest bools, an embarked-graphic
string and Achievement v1. The mandatory current writer profile requires 64
flags and excludes the obsolete popup queue from Player versions <=10. The
minimum canonical suffix is 144 bytes. Player achievements end the base class;
the actual CvPlayerAI object adds one uint32 version 1. Stopping before this
word would not frame a complete PlayerAI object.

`RetailSavePlayer.h` assembles all seven bounded stages with one shared record
budget. It returns completePlayerWireFramed only after the final word succeeds;
completePlayerVerified, completeSaveVerified, rulesetCompatibilityVerified and
restoreApproved remain false. Explicit catalog/writer profiles are hypotheses,
not verified ruleset identities. The original retail top-level save loop is not
available in the copied SDK. The private .zssave per-player sections are not
substituted for the contiguous retail stream.

Optimized and checked headless x64 builds each passed 20,398 checks,
3,751 truncations and 2,048 deterministic
mutations. Independent literal fixtures include real Army bodies and all 20
operation forms; budgets, versions, counts, bools and trailing bytes are checked.

The authenticated public RAM-only input follows Map, 64 Teams and every Player0
stage in source order, without byte-pattern searching. It reaches the suffix at
2,444,247 and the complete first PlayerAI end at 2,444,461.
The next exact offset is independently parsed as the next Player prefix with
ID 1. This confirms one structural Player0 boundary, not all 64 players, complete
save validation or restored gameplay. No full save body or embedded database is
retained.

Evidence: `evidence/retail_save_container/player_end/build_result.json` and
`source_conformance.json`. Remaining Players/Supporting, compression finish,
cross-object/ruleset validation, the Unit GreatWork writer defect, SDK restore,
UI/3D, full campaign and useful measured multicore performance remain unfinished.
Current Host/SDK bytes, default publication and native execution hold are
unchanged. This portable component is not integrated into the current Host.

## Player unit list and complete Unit v9 wire bodies

`RetailSavePlayerUnits.h` frames the actual free-list header and calls the Unit
v9 parser for every declared live object. `RetailSaveUnitArchive.h` follows C++
member declaration order, not the misleading constructor initializer-list order.
Its 147 registered values consist of 124 raw32 values, 11 bools, two opaque
strings and ten counted integer vectors, with a structural minimum of 555 bytes.
The first six values are owner, original owner, raw unit type, X, Y and unit ID.
Full archives omit count, version, name and delta-index metadata; the component
source evidence distinguishes retained original x86 evidence from the current
provider's implementation. No private full-save format is substituted.

The remaining v9 fields include scalar type hash/turn, sparse promotions, three
IDInfo pairs, a counted domain vector, three integers, a bool, 28 integers, the
current display name, scenario data, UnitReligion v2, GreatWork hash/tourism and
20-byte mission rows. Promotion hash zero still has a bool; its catalog size is
metadata, not an allocated dense table. Mission queue estimate 12 is not a cap.
A complete structural Unit has a minimum of 768 bytes, plus variable payloads.

The mandatory writer profile requires the GreatWork hash word that v9 Read
always consumes. The original Write database-query failure branch can omit this
word. That incomplete output is not inferred, scanned for, or repaired here;
this writer defect remains a separate gate before general save/restore approval.

Optimized and checked x64 headless builds each passed 9,590 checks,
3,161 truncated inputs and 2,048 deterministic
mutations. Literal fixtures cover nonempty vectors/promotions, opaque strings,
mission counts above the estimate, free-list holes and multiple real body reads.
Returned mutations demonstrate bounded framing, not semantic or ruleset validity.

The authenticated public RAM-only input follows Map, 64 Teams, all previous
Player stages and the empty city list to inflated offset 2,428,055. This stage
frames 9 actual Unit bodies and reaches inflated offset
2,444,247. IDs, owners, coordinates and the exact following
army-pool header are cross-checked in the standalone test. This is structural
public-wire evidence, not instantiated SDK state, resolved catalogs or restored
gameplay. No full save body or embedded database is retained.

Evidence: `evidence/retail_save_container/player_units/build_result.json` and
`source_conformance.json`. Armies, operations, remaining Players/Supporting,
compression finish, cross-object/ruleset validation, SDK restore, UI/3D, campaign
and useful multicore performance remain unfinished. The Host, SDK DLL, default
publication, prepared runtimes and native execution hold are unchanged. This
component is not integrated into the current Host and approves no restore.

## Player city list and complete CityAI wire bodies

`RetailSavePlayerCities.h` now frames the actual `FFreeListTrashArray<CvCityAI>`
header and calls the City v6 / CityAI v1 parser for every declared live object.
The header consists of five signed words, capacity next-free words and a signed
live count. Capacity is not a City version or a byte length. Free-chain and
count consistency are checked; complete object-ID placement is still unverified.

The portable City body covers buildings, production strategies, citizens,
religions, emphases, espionage, extra hit points and the CityAI tail. Minimum
CityAI size is 2,282 + 4P bytes, where P is an explicit project-catalog width.
Project weights omit their count on the wire. Initialized building/unit catalogs
and the six-yield source profile are explicit prerequisites, not ruleset proof.
CityAI writes two raw 80-int arrays; citizen plot flags are two raw 37-bool arrays.
The two appearances of the city name are intentional. CityCulture is not an
additional serialized member here. Zero-hash omission differs from ProcessAI's
mandatory hash/weight rows and is tested separately.

The optimized and checked x64 headless builds each passed 12,909
checks, 6,269 truncated inputs and 2,048
deterministic mutations. Independent occupied-city fixtures exercise project
widths, nonempty nested tables, free-list holes and multiple real body parses.
These generated bytes are component fixtures, not retail gameplay saves.

The authenticated public RAM-only stream follows Map, 64 Teams and the existing
Player stages into the city list at inflated offset 2,427,999. That particular
list has capacity 8 and **zero cities**, ending at 2,428,055. The next unread
word is a unit-pool field, not a discovered City version. Thus occupied CityAI
body compatibility has **not** been demonstrated on this public save. No full
save payload or embedded database was retained. The inflater finish contract,
units, armies, operations, remaining Players/Supporting, cross-object/ruleset
validation, SDK restore and real gameplay remain separate unfinished gates.

Evidence: `evidence/retail_save_container/player_cities/build_result.json` and
`source_conformance.json`. The current Host, SDK DLL, prepared runtime, default
publication and native execution hold are unchanged. This component is not
integrated into the current Host and does not approve restore or the full goal.

## Player fields from Traits to the city-object list

Four new portable headers frame the current BNW Player fields immediately after Traits: Espionage0 (nested Spy1), EspionageAI0, PlayerTrade2, TradeAI0, LeagueAI2, Culture6, optional Notifications2 and Treasury1. They then read the two counted six-yield matrices, UnitCycle, research queue, two bools, blocker enum/index and linked list of city names. The parser stops before `m_cities`; it does not frame the complete Player or restore any SDK state. Every span shares one bounded Reader.

Espionage maximum-cost and heist dimensions and Culture influence count are explicitly serialized as 22 by this supported writer profile; no catalog size or later version signature is guessed. Inline capacities are not maxima. The notification presence byte is outside the Notifications span. Notifications always writes 100 slots, including inactive ones; each minimum 41-byte slot keeps the payload for raw notification hashes zero and FFFFFFFF, and its PlayerTypes field is last. Two vectors of Firaxis::Array<int,6> use one uint32 outer count each and no row counts. UnitCycle/researchQueue/cityNames use signed linked-list counts. The empty combined minimum is **602 bytes without notifications / 4722 with notifications**, with 66 declared rows.

The independent C++ test constructs four literal cases (602/4722/815/5506 bytes; 66/66/80/132 declared rows), nonzero starts, unread city sentinels, nested strings and arrays beyond their inline estimates. AMD64 /O2 and /Od /RTC1 each pass **17,729 checks**, **5,519 byte-prefix cuts** and **2,048 deterministic mutations** (437 structural returns / 1611 typed rejections). Returned mutations are not approved game states. Exact/short byte, prefix, array, aggregate and string budgets and input immutability are checked. Actual compiler dependencies include all 24 portable headers and no SDK header; standalone test imports contain only kernel32.dll. The compiler and test programs run hidden with one build at a time and below-normal priority.

The same authenticated public diagnostic stream advances **[2421545,2427999)**: **6454 bytes**, **319 declared rows**. Source-ordered spans are espionage432, espionageAI653, trade12, tradeAI8, leagueAI8, culture238, notification presence1, notifications4120, treasury52 and pre-city fields930 bytes. The next exact word is eight and remains unread; it is not assumed to be a City record version. **7,334,328 following bytes remain unframed**. The existing Game/Map/64 Team/Player-prefix/middle/late chain is rechecked sequentially before this boundary, without searching signatures. All prior ruleset-profile assumptions and the nonfinal compression finish limit remain unapproved. Public compressed/inflated saves and embedded database bytes are not retained.

The source conformance helper records nine states including Spy, five container codecs and 43 pinned source/provenance inputs. It exactly reproduces the existing five Espionage/Culture checked-count edits and two runtime-initializer edits in memory, binds the retained compiled source/object witnesses and distinguishes the existing transactional AutoVector load from a wire change. No SDK source, recipe, binary or prepared runtime changes in this stage. The 346 protected input artifacts remain byte-identical before publication. Compiler objects and environment setup totaling **2,746,781 logical bytes** are retired with file identity/mtime/SHA records. Evidence is `evidence/retail_save_container/player_post_traits/build_result.json` and `source_conformance.json`. Cities, units, armies, operations, replay/player tail, all PlayerAI records, Supporting placement, full container completion, ruleset compatibility and actual retail restore remain required. Original UI/3D/campaign and measured multicore gates are unchanged.

## Finite direct SDK stream-count corrections

The preceding two static inventories are historical baselines. Their finite Expansion2 cpp query had 58 direct `.size()` insertions: 15 native-size width mismatches, three unchecked signed casts, 39 already-four-byte unsigned containers and one existing checked conversion. All **18 selected sites in eight copied SDK translation units** are now corrected. The other **40 sites remain unchanged**, and the same recorded query returns exactly 40 direct sites. This is not an exhaustive audit of indirect, templated or other serialization forms.

Army, Culture, DiplomacyRequests, Economic, PlayerEspionage, PopupReturn, ReplayInfo and ReplayMessage now preflight the selected counts before each writer's first output. Sixteen static sites match signed int32 readers and two match uint32 readers. Every count word and loop uses its checked local. PlayerEspionage checks all **22** heist lists before version 0; this makes **39 runtime guard evaluations** across the 18 static sites. ReplayInfo keeps version 1 and its separate child-message version 2; ReplayMessage itself has no version word and is checked before its first turn field. Valid payloads, version words, IDs, balance and schemas are unchanged. The ordered port recipe reproduces all eight files byte-for-byte in RAM; only eight manifest rows change. Ten changed-file gzip backups roundtrip correctly. No full generator or project copy was used.

`direct_stream_count_syntax/build_result.json` checks all eight actual translation units against **162 tracked headers**, without objects, PCH, code generation or linking. It records **620 legacy warning occurrences** across those files: C4091 40, C4819 564, C4996 16. These repeated diagnostics are not zero-warning evidence.

`direct_stream_counts/build_result.json` uses archived x86 and current x64 SDK streams. Native x86/O2 and x64/O2/Od pass **474/2136/2136 checks**. The actual complete PopupReturn writer bodies, with seven real `std::vector<int>` and one `std::vector<CvString>`, produce identical full wire bytes in three empty/single/populated cases, including empty, embedded-NUL and UTF-8 strings and boundary canaries. The other ten static count sites use authenticated entry guards, count statements and typed loop headers with visit-counter bodies; their record payloads are explicitly not tested. Two FStaticVector unsigned-size shims test size-return/guard policy only. Each x64 mode rejects **113** oversized entry cases without emitting bytes and accepts **39** inclusive guard limits, including all 22 heist positions. Native-size negative controls expose the former eight-byte counts. These are component ABI/count checks, not full writer, GameCore, save restore or ruleset compatibility proof.

Objects, environment setup, duplicate/negative-control fixture outputs and unneeded owned export intermediates are retired with identity/hash receipts. Only three canonical Popup fixtures are retained. R11/B11 and the default Host are unchanged, held, and do not contain these working-source changes. Full Player framing, container finish validation, actual save round trips, original UI/3D/full gameplay and measured multicore behavior remain required.

## Current full base SDK compile and link (not executed)

This later integration stage supersedes the earlier component snapshots only for current base-SDK compile/link readiness. Their syntax, wire and no-full-rebuild claims describe those earlier runs and retain their original scope. No historical component report is relabelled as a full build or runtime pass.

The current incremental x64 build validates all **161 translation units**: **37 recompiled, 124 reused**, with all **162 cached outputs** (161 AMD64 objects and one PCH) and **1,374 tracked inputs** authenticated. This is not a clean rebuild. The current checked vector-count helper, PlayerTraits and eighteen direct-count fixes in eight SDK cpp files are included in this base object set. Compiler exit code is zero, with no unique errors or critical numeric-conversion diagnostics; other legacy warnings are not claimed absent. Existing source, cache and provider paths were reused; no SDK tree or game data copy was created.

The actual linker consumes those current 161 objects, the **16 retained providers**, 14 explicit platform-library inputs and authenticated CRT/default libraries. Its exit code is zero with **zero unresolved symbols and zero linker warnings**. Static PE inspection confirms AMD64 PE32+, ASLR/NX, exactly the three definition exports and matching export addresses in the link map. The import-module set matches the earlier base DLL. Localized library-search lines are separate from final map owner/member evidence: searched inputs are not all claimed as selected. The Korean log emits no Loaded member lines; final archive membership comes from the map and is labelled accordingly. No DLL loading is involved.

The new base DLL is a build component, not a replacement for the prepared runtime DLL. SaveRestore, shared-Lua, FoundValue and other runtime object overlays are not used or rebased here. B11, prepared R11, the Host, launcher, release metadata and the original-game test hold remain unchanged. The retail-state framing readers are not made into a live retail loader by linking this DLL. SDK restore, retail save writing/reopening, full original UI/3D/campaign behavior and measured multicore performance remain unverified.

Exact inputs, child commands, PE/map checks and artifacts are recorded in `evidence/sdk_current/compile_result.json`, `base_link_result.json` and `base_link_validation.json`. Changed metadata is protected by changed-file gzip backups. Two obsolete validation PCHs totaling **9,830,400 bytes** and regenerated failed link attempts are retired with path/identity/hash receipts; the current object cache and verified base DLL remain retained.

## Current SDK with retained runtime overlays (not executed)

The current 714-patch SDK is now combined with the retained runtime-specific changes without reusing historical SDK overlay objects. Eleven SDK cpp files use C++14 and four bridge cpp files use their required C++17 mode, with `/MD`, strict floating-point behavior and `/Y-`. The link consumes **150 authenticated current base objects plus 15 current overlay/bridge objects, 165 total**. The eleven successful SDK compilations from the first attempt are authenticated and reused; only the four bridges are compiled during resume. The first attempt remains a failed attempt, caused by using C++14 for the first C++17 bridge. Thirteen small source/header overrides are generated (1,442,063 bytes), including one byte-identical PCH routing text header; no binary PCH, full SDK tree or game data copy is made.

Five retained save/runtime fixes are rebased: espionage-AI static-vector reset before reading, military player-array bounds, culture opinion defaults, the optional trait improvement default and operation reinforcement initialization. Eighteen map-startup/error-cleanup patches, exploration, city-site evaluation and shared-facts found-value behavior are reproduced from authenticated historical recipes. The old count patches are not reapplied. Four complete current serialization writer bodies remain byte-identical, so these overlays preserve the latest count guards. These are source-conformance and build facts, not proof of live state restoration.

The shared Lua import library replaces the static Lua provider exactly once. The retained Lua DLL has 124 exports including the native-exception callback boundary. Actual compiler dependency reports bind each new unit to prehashed inputs, and the linker succeeds with zero unresolved symbols and zero linker warnings. Static inspection verifies AMD64 PE32+, three public exports, the retained runtime import-module set, one borrowed-reference registry and the expected bridge symbols/owners. Old SaveRestore/NewGame/Explore/CitySite/FoundValue SDK objects are absent from the new link.

This produces a current runtime SDK candidate only. It is never loaded, copied into R11/B11 or promoted by the launcher. The Host, prepared runtime, default release and original-game test hold remain unchanged. A corrected preparation metadata key distinguishes SiteEvaluation cpp and header witnesses; the thirteen generated files remain unchanged, and the former plan/tool are recoverable from changed-file gzip backups. Full Host integration, actual new-game/turn/save/reload behavior, retail save compatibility, original UI/3D/campaign behavior and measured multicore performance remain required. Exact source preparation, compile/link inputs and outputs are in `evidence/sdk_runtime_current/overlay_plan.json` and `build_result.json`.

## Limits of external container evidence

[Civ5MapImage commit 4ecadf1b4ac656cc113ee2d8da64ce8c85db9d29](https://github.com/samuelyuan/Civ5MapImage/blob/4ecadf1b4ac656cc113ee2d8da64ce8c85db9d29/fileio/civ5save.go) reads Pregame followed by compression-format and chunk-size words and then uses a zlib reader. It does not establish every subsequent SDK stream boundary or implement original save writing; its permissive partial-decompression error handling is unsuitable as a loader acceptance rule. [rivarolle's parser](https://github.com/rivarolle/civ5-saveparser/blob/bb4e825d005a0e5c4e4903ba29c4691fa0c78fcf/FileReader.py) instead searches for zlib candidates and also does not prove container framing. Neither justifies treating a found compression signature as a validated state boundary.

## Historical read-only user sample identity

These identities came from an earlier read-only hash/metadata observation. They were not refreshed during the current retail-test isolation; their current existence/content is unverified. No current user-save content was read, parsed, modified or deleted. The public prefix fixtures above are separate inputs.

| Sample | Size (bytes) | SHA-256 |
|---|---:|---|
| `C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\Saves\single\아그네스 타키온 [ICON_PRODUCTION][ICON_RESEARCH]_0101 AD-0820.Civ5Save` | 8,540,689 | `93BC786DE4A60F9E3B51D3F6BCC11AF71C703FC6F72C78048D1986E814C3F4E7` |
| `C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\Saves\single\auto\AutoSave_0013 BC-3220.Civ5Save` | 546,217 | `36EDEC9DE4A6747B4DDF08F40768289D1E7C24BE04A3089DD7777766C775D0D4` |

## Current SDK prepared with retained host (not executed)

A separate current-SDK candidate is now prepared as `20261022T001546Z_7fba195072e4`. It uses the unchanged B11 AMD64 Host (SHA-256 `61c2fca40115642b46d933130d6a27960f68a4a5f6815f3754308e164391690c`) and the current 714-patch runtime SDK (SHA-256 `60984b68246d16bef42a4d0f5a159ae51104edb356a26c85ff917493279cbfe5`). All 80 current Host source files match their B11 frozen inputs. Of the 24 runtime filenames, only the SDK and exact bundle manifest hashes differ from R11. The existing R11 bundle and default launcher remain unchanged.

The actual production preparation path ran once under an audit guard, without Host execution, GameCore loading, windows, retail installation/MODS/user saves/settings/process access, SQLite connection or default promotion. Its 276 protected inputs were rehashed unchanged. The original terrain, unit package, owned font bank and six frontend tools are reused; no retail asset preparer runs. Current-SDK selection requires an explicit report digest, sealed terrain and owned private PolicyInfo input. It rejects smoke/resume mode before materialization, and its Resume launcher explicitly stops instead of opening a save. The existing default resume behavior is retained. The pure validation imports no longer preload the native probe dependency.

Fifteen immutable inputs use cache hardlinks: fourteen existing cache hits and one independent current-SDK cache snapshot (6,941,696 bytes). Two writable database copies total 57,501,696 bytes. New runtime/evidence/cache file identities add 76,748,370 logical bytes after excluding reused cache IDs; this scope excludes stage receipts, directory allocation and physical disk allocation. Preparation guard regressions and input tamper checks pass 53/53. Reproducible failed-preflight manifests and empty logs were removed after preserving concise failure summaries and exact path/size/hash receipts.

Evidence: `evidence/sdk_runtime_play/prepared.json`, its exact request, `evidence/sdk_runtime_current/preparation_tests.json` and `evidence/sdk_runtime_play/temporary_cleanup.json`. This is a prepared new-game-only candidate, not verified Host/SDK execution or a playable full-engine release. Original UI/3D/campaign behavior, retail save and mod compatibility, full player restore and measured multicore improvement remain required. The original-game execution hold is unchanged.

## Next implementation gate

1. Resolve unsupported Pregame profiles and the original container completeness/finish contract, then map the inflated SDK stream boundaries. The supported prefix and bounded decoder above do not establish a complete retail container. Do not infer unknown fields from historical user samples or equate the private section order with the retail stream order.
2. Connect validated retail state to the SDK restore/save registration paths. Preserve required DLC/mod identities and reject unsupported state layouts before changing live state. Metadata parsing alone cannot complete this step.
3. After the user's retail-test isolation is explicitly released, use protected copies of confirmed samples to verify retail-to-candidate loading and candidate-to-retail save/reopen, including game-state equivalence and unchanged originals. A `.zssave` round trip or a metadata-prefix pass cannot satisfy this gate.

## Working SDK Unit GreatWork save preflight (static candidate)

The current x64 `CvUnit::write` resolves a required GreatWork hash before its first stream write. Previously, an unavailable database or failed query could omit the required 32-bit field while the v9 reader still consumed it. `NO_GREAT_WORK` still writes zero without querying; successful lookups write the same hash once at the original field position. Database readiness, prepare, bind, step, null/empty type and zero hash failures now abort instead of silently omitting the field or substituting zero. Unit version 9, reader bytes, existing successful wire layout and balance are unchanged. Only the working x64 source and a pure serialization policy header changed; the original SDK and installed game remain untouched.

The portable O2 policy suite passes 872 checks, including 15 failure cases, 258 no-work cases, 257 valid cases and three literal wire suffixes. Its fake lookup/writer harness verifies failure short-circuiting and unchanged modeled destinations; it does not execute the real database, production Unit writer or real file persistence. A direct standard-library exception control separates permitted `exception_ptr` copies from the required exact exception type, payload and shared identity token.

The retained SDK output has 434 verified actual compiler inputs, including the new helper, and an AMD64 DLL linked from 165 direct objects with exactly 164 parent objects reused. Static PE/map inspection verifies the existing three exports, shared Lua import, four bridge owners and one borrowed registry. The original post-link tooling failure is preserved. Compiler/linker process exit codes were not retained; the completion report therefore certifies the existing binary outputs and input graph, not a new clean build or runtime execution. Static completion starts no child process and retires only the 144-byte environment script.

Evidence: `evidence/serialization/unit_great_work_save/source_change.json`, `test_8b8e74b2cccc64e26ca6/result.json`, `sdk_2bdcdf80a1695780f864/result.json` and `progress_update.json`. The old base-link SDK source-match flag is now false; the separate Host-only match remains true. Existing runtime/prepared bundles and the execution hold are unchanged. Real database failure behavior, actual save-file preservation, retail save/restore, original UI/3D/campaign behavior and measured multicore improvement remain unverified. This fix does not resolve the outstanding retail container/map/full-player framing failures or complete the full engine goal.


## Current length-prefix framing and public wire diagnostics

The previous flat compressed-tail diagnostic passed ten later four-byte length words into zlib. Both pinned public files instead cover their exact raw remainder with eleven little-endian length/payload frames. The new `RetailSaveChunkFrames.h` requires an explicit caller profile and returns zero-copy spans, with typed bounds and budget errors. It does not identify the producer finish contract or approve loading. Existing Pregame prefix fields, canonical bool default and wire schema are unchanged. The optional public diagnostic selects the existing SDK-byte bool policy explicitly.

The x64 O2 framing component passes 193 checks, including 52 rejected inputs and 34 small literal cuts. Three cuts exactly on complete-frame boundaries are correctly accepted; there is no invented final-frame marker. The two eleven-frame length controls use opaque synthetic payloads. Both component and public executables import only Kernel32; no SDK, GameCore, Host or window executes.

The actual C++ header spans feed one Python zlib decoder per public file, with no reset or flush. Only RAM holds raw, inflated and embedded database bytes. JPL produces 21,151,963 bytes, Riva 16,727,961 bytes, matching the independently recorded output hashes. Neither reaches zlib stream EOF; producer completeness remains unverified. The fixed profile is awards=5, grand=4, projects=6, SDK-byte booleans, and the caller-declared Game/Map/64 Teams/64 Players/Supporting sequence. Its outer order is still an experiment.

Both files frame all 4,160 plots and their Map tails; exact Map ends are 6,926,871 (JPL) and 6,862,029 (Riva), matching the separate coordinate trace. Both frame 64 ordered Teams. Riva additionally frames all 64 Players, 30 cities, 66 units, one army, one operation and the 16,916-byte Supporting tail, ending at byte 16,727,961 with zero remainder. These are structural wire observations, not semantic state or restore validation.

JPL frames 35 Players, with 1,038,283 completed array records. The unchanged shared default budget is 1,048,576, leaving 10,293 records when slot 35 begins; it rejects at byte 15,367,711. No automatic retry, profile guessing, resynchronization, limit change or load approval was added. This later stage supersedes the older corruption-driven Map/Player-prefix failures only for these exact inputs and declared profiles. The retained partial observations remain historical evidence.

Evidence: `evidence/retail_save_container/map_trace/chunk_frames_component/test_e852fb22b6c91ccf4959/result.json`, `public_result.json`, and `publication/progress_update.json`. Only one current component build and one public diagnostic build were added; objects and environment scripts were retired. Source backups contain changed files only. Existing SDK/runtime bundles, launcher, original game, MODS, settings and user saves are untouched. Producer finish/completeness, the remaining JPL record-budget gate, real SDK restore and save reopening, original UI/3D/full gameplay and measured multicore performance remain open.

## Explicit diagnostic record budget: second public sequence completed

The public probe now accepts an optional `--max-records` only in inflated mode. It requires a positive decimal integer up to 67,108,864 and rejects duplicate, zero, non-decimal and out-of-range values. The default remains the unchanged Reader limit of 1,048,576 records. The chosen value and whether it was explicitly selected are emitted in JSON. Input, prefix, per-array, string, object/version and semantic checks are unchanged. No production parser header, SDK source, game setting, ID or save schema changed.

One no-SDK x64 O2 build and seven process cases passed the declared diagnostic protocol: five bad argv cases reject before stdin, a one-byte default control retains the original budget, and the pinned JPL plaintext is inspected once with a caller-selected 2,097,152-record budget. The actual source diff and the previous 27,099-byte CPP are preserved in a small changed-file gzip. Compiler dependencies, Kernel32-only imports, bounded stdout/stderr and all nine child commands are recorded. No native inflate, SDK/GameCore/Host/window execution or original-game access occurs.

JPL now frames all 4,160 plots, 64 ordered Teams, 64 ordered Players, 24 cities, 54 units and the 16,916-byte Supporting tail. Its total is 1,805,777 array records, ending at inflated byte 21,151,963 with zero remainder. The old default-budget rejection is retained as the earlier diagnostic observation; no automatic retry or silent global limit change was added. Together with the earlier Riva result, both exact public inputs now have a complete structural sequence under the declared width/bool/outer-order profiles. Riva was not downloaded or re-executed in this later stage.

Evidence: `evidence/retail_save_container/map_trace/record_budget/source_change.json`, `result.json` and `publication/progress_update.json`. Raw and inflated public bytes remain RAM-only; frame spans are reused from the authenticated actual-C++ Header diagnostic. Both zlib EOF values remain false, the original producer finish contract and semantic compatibility remain unverified, and no retail-to-SDK restore or save reopening is approved. The original-game execution hold, prepared runtime, launcher and working SDK are unchanged. The next end-state gate is the exact retail-to-SDK section/PreGame/restore contract, followed by actual runtime validation after the hold is explicitly released.

## Actual canonical-boolean compatibility gate before SDK restore

Source inspection identifies the native restore path as `SdkGameRestore::LoadArchive`, with 133 configured sections ordered Bundle/Pregame/Game/Map/Supporting/64 Teams/64 Players. A retail adapter must extract Pregame from raw slotHints through archive end, keep the AI trailer in each Player span and reorder Supporting into section 4. The SDK reads Game, Map, Supporting, Teams and Players in that execution order, checks each entire nonempty section after reading, and requires the exact owned bundle identity, turn/active-player agreement, owner-thread lock and a fresh context. Pregame key binding already needs a compatible database before the later Game database restoration. These source contracts do not yet approve raw payload compatibility.

The current SDK provider rejects bool bytes above one. The existing no-SDK probe was therefore reused twice, without a new build, using the same pinned inflated bytes and explicit canonical boolean selection. JPL still frames all 64 Teams/64 Players/Supporting with zero remainder under its explicit 2,097,152-record budget. Riva rejects in Player slot 1: inflated byte 7,795,644 is 68 and Reader reports the next position, 7,795,645. The preceding SDK-byte diagnostic frames that exact file through byte 16,727,961 with zero remainder. This is a concrete canonical-byte gate mismatch; it is not yet proof that the particular source member or provider should be changed. No actual SDK bool provider or GameCore code executes in this comparison. Pregame boolean positions were skipped by the existing prefix inspector and remain separately unverified.

Supporting's source layout is 276+4P bytes, where P is the validated Map size; both public P=4,160 inputs yield 16,916 bytes. Its SDK reads mutate existing state after Map initialization. Whole-section consumption is checked only after a reader returns, and `loadedGame` is set before the payload reads. Neither that check nor a disposable in-memory context proves rollback of possible file effects. A failed restore context must not be claimed reusable without further implementation and evidence.

Evidence: `evidence/retail_save_container/map_trace/restore_booleans/result.json`, `publication/restore_contract_audit.json` and `publication/progress_update.json`. The next focused step is to identify the Riva byte's precise Player subrecord and source boolean field, then choose an explicit compatibility policy while preserving default native-archive validation. Producer finish, Pregame bool compatibility, ruleset identity, actual SDK restore/save reopening and the original UI/3D/full-game/multicore goal remain open. Existing runtime, SDK/provider source, launcher, original game, settings and saves remain unchanged and held. Goal-turn metadata backups from the record-budget stage are reused rather than copied again.


## Source-identified operation boolean: explicit import candidate

A focused no-SDK x64 O2 Player diagnostic locates Riva's byte 7,795,644 in Player 1's ending [7,795,480, 7,799,422). A bounded source-order walk consumes a 56-byte army pool, one 72-byte ArmyAI, a four-byte operation count and an eight-byte key/type. The base body begins at 7,795,620. Its version and five signed 32-bit fields place CvAIOperation::m_bShouldReplaceLossesWithReinforcements at base+24, exactly byte 68. Both original and current SDK declare bool and read/write at this position. No signature search or resynchronization is used.

Static reading of the retained original SDK reference executable verifies the 17-byte Read/Write wrappers: each transfers one raw byte through a virtual stream call without value normalization. This does not establish all virtual stream implementations or original C++ semantics for invalid bool representations. The current provider retains canonical 0/1 validation.

An explicit legacy-nonzero-truth experiment preserves the authenticated original inflated bytes in RAM, changes only byte 7,795,644 from 68 to 1 in a separate RAM copy, and runs the existing canonical no-SDK probe once. It frames 64 Teams, 64 Players, 30 cities, 66 units, one army, one operation and the 16,916-byte Supporting tail through byte 16,727,961, with zero remainder and 713,024 array records. All eight structural metadata groups match the preceding SDK-byte result. Original bytes, limits, boundaries and default provider policy remain unchanged. Raw and converted save bytes are not written to disk.

The Reset fix already exists as initialize_operation_reinforcement_flag_in_reset in save_restore_patches.json. Its assignment is present in the current runtime overlay, whose exact hash is recorded as the consumed CvAIOperation.cpp compiler input. No duplicate Reset edit, SDK compilation or provider change is made. Missing original initialization is a possible source of noncanonical bytes; the historical origin of this exact 68 is not proven.

Evidence: evidence/retail_save_container/map_trace/restore_booleans/player1_trace/result.json, member_audit.json, import_candidate.json and publication/source_contract_audit.json. The earlier unidentified-member observation is superseded for this exact sample only. A general production import adapter remains unimplemented. Producer finish, Pregame bool compatibility, ruleset identity, SDK restore/save reopening, full original UI/3D/gameplay and measured multicore benefit remain unverified. Runtime remains held; original game, settings, MODS and user saves are untouched.

Changed progress/document files receive new small gzip recovery copies. Two superseded metadata backups from the framing publication are retired after hash, identity, link, reparse and newer-recovery checks. Their identity/deletion receipt remains, and older framing receipts now reference retired historical backups. The focused diagnostic's three build files, sources, current evidence, recent metadata recovery and runtime dependencies are retained.


## Explicit inflated-body preparation component

RetailSaveBodyImport.h now provides a reusable preparation boundary for an already inflated body with a mandatory declared Game/Map/64 Teams/64 Players/Supporting layout, catalog widths, limits and boolean policy. RequireCanonical preserves strict input validation. The opt-in OperationReinforcementNonzeroTruth policy internally frames the whole source, re-walks only the resulting operation spans using the existing base/derived readers, and edits only noncanonical m_bShouldReplaceLossesWithReinforcements at base+24 in one owned RAM copy. No external patch offsets are accepted.

Every converted copy undergoes a complete canonical reinspection with the same original limits. All main spans, IDs, record totals, object counts and operation spans must remain equal. Reinspection does not spend the shared record budget twice. Only a fully successful value is returned; exceptions preserve the caller's original bytes and previous output. Derived/non-target bools remain unmodified and are rejected by the final strict pass. An outer map key differing from body ID retains the existing allowed wire behavior. The returned Game/Map/Supporting/Team/Player spans describe the owned bytes at return; later byte mutation invalidates that evidence.

One x64 O2 no-SDK executable imports only Kernel32 and consumes exactly 39 project headers. Its actual self-test passes 13,361 assertions: 20 operation types by all 256 raw bytes, 284 truncations, 35 directed corruptions and 338 failure-output atomicity cases. Two synthetic slot labels test operation ownership; they are not synthetic full Players. The two pinned public bodies then pass 171 and 175 additional checks. JPL has no edits and remains canonical. Riva has exactly one edit at 7,795,644, 68 to 1, Player slot 1 operation 0. Both have 64 Teams/64 Players and zero remainder. Each matches all eight independently retained structural metadata groups, including every Team/Player boundary.

Actual full Prepare also passes at its exact record total and rejects one-record-short, one-byte-short, invalid-policy/layout, non-target conquest bool and trailing-byte inputs. Riva's non-target failure starts with the original 68: a local target edit occurs before the final strict rejection, while the original and previous output remain unchanged. Every output byte outside its reported edits is checked unchanged. Public source bytes, converted bytes and embedded databases remain RAM-only; neither the original SDK nor Host/GameCore/window runs.

Evidence: evidence/retail_save_container/body_import/result.json, its five-command build/run trace, compile_e01172b90489a8586745/build_result.json and publication/source_change.json. This is a production preparation component exercised by portable tests, not an implemented external import menu or SDK restore entrypoint. Producer finish, Pregame bool conversion, matching bundle/ruleset identity, native section packing, SDK restoration/save reopening, full original UI/3D/gameplay and measured multicore benefit remain open. No runtime/prepared bundle or launcher is promoted and the execution hold remains unchanged.

The new build's object/environment intermediates are retired. The superseded single-Player bool-trace build's three files and the oldest before-record-budget metadata gzip pair are also retired after exact identity/link/hash/reparse and retained-recovery checks. The current body-import build, existing canonical baseline, source/evidence and two most recent metadata recovery pairs remain. Historical receipts still identify the retired files but no longer imply their physical retention. Source, original game data and user saves are outside cleanup.


## Typed Pregame and owned payload-section preparation

RetailSavePregameImport.h validates SlotHints v3, Archive v6 and WorldInfo v1/v2 in the source serializer's order, including all 17 scalar bool fields and nine bool vectors. Only exact 0/1 is accepted at these typed sites; signed one-byte GameTypes, int32 option values and other non-bool bytes are not normalized. Every span/error offset remains relative to the original raw file, while the owned Pregame copy starts at SlotHints and ends at archive.end. The compression-format word and first frame-length word remain outside the prepared section. Names longer than 63 bytes or containing NUL are observed by the typed parser and rejected by the current native candidate gate because CustomOption stores char[64].

RetailSaveImportSections.h composes this checked Pregame with the existing explicitly profiled body preparation. It returns 132 nonempty bounded payload views in native reader order: Pregame, Game, Map, Supporting, 64 Teams and 64 Players. Supporting is physically last in this retail body and is presented before Teams without rewriting its payload bytes. The views reference the two owned buffers and must cover every owned byte exactly once. A later verified Bundle would be the 133rd section; no Bundle section, native envelope encoder, file writer, import menu or SDK load call is added here.

Game turn and active player come from typed Pregame. Elapsed turns come from Game+8, after version and m_iEndTurnMessagesSent at +4. The retail preview header's turn equality is diagnostic only because the native restore compares Pregame against its own envelope, not the external preview. Exactly 64 original network IDs are inspected and preserved; an existing assignment is observed without resetting or silently approving it. This does not establish catalog compatibility, source/converted-body association or safe restoration.

The actual single O2 x64 portable build imports only Kernel32, consumes exactly 43 project headers and includes no game SDK. Self-test passes 7,102 checks, 2,120 truncations, 86 directed corruptions, 2,218 failure-output atomicity cases, 23 elapsed cases and six option-name cases. The two pinned public inputs additionally pass 449 and 851 checks. All original bytes and failure outputs remain unchanged, and both bodies still match all eight previous canonical structural groups.

Actual public Pregame observations are explicit:
- JPL: raw Pregame [683,11580), 10,897 bytes; Archive begins 4,220; turn/elapsed 19, active player 4, GameTypes=2 (hotseat). All 417 bool bytes are canonical and all 64 network IDs unassigned. The offline single-player candidate gate rejects it at raw offset 4,220 and returns zero sections. This rejection is not successful retail import.
- Riva: raw Pregame [436,11219), 10,783 bytes; Archive begins 3,899; turn/elapsed 12, active player 0, GameTypes=0 (single player). All 417 bool bytes are canonical and all 64 network IDs unassigned. Preparation returns 132 views with complete owned-byte coverage. Its body retains the existing opt-in single operation reinforcement-bool edit. This is payload preparation, not SDK restoration or proven original-save compatibility.

Each public invocation also exercises a separately labeled intentionally unpaired synthetic Pregame with that public body, so the complete 132-view success path is covered independently of actual Pregame eligibility. These two controls establish ownership/layout behavior only and do not count toward the one accepted and one rejected authentic public candidate. The runner authenticates the exact raw/inflated fixture pair using the retained C++ frame spans and pinned hashes; the C++ preparation helper itself still reports compressedBodyAssociationVerified=false.

Evidence: evidence/retail_save_container/import_sections/result.json, its exact five-command trace, compile_dbcd81696bb2493d7ec0/build_result.json and publication/source_change.json. Frozen public raw bytes, inflated bodies, prepared bytes and embedded databases remain in RAM. Existing providers, held SDK/Host runtime, launcher, original installation, MODS, settings and user saves remain unchanged and unexecuted.

Remaining gates include verified matching Bundle and catalog/ruleset identity before Pregame lookups, producer-finish/completeness, production compressed-body association, native envelope/import adapter, SDK restoration/reopening, original UI/3D/full-campaign behavior and measured multicore benefit. No native runtime is promoted or executed, and the runtime hold is unchanged.

The new build's object/environment intermediates are retired. After replacement success and identity/link/hash/reparse checks, the superseded record-budget diagnostic's three build files and oldest before-operation metadata gzip pair are also retired. The current import-section and body-preparation builds, sources, reports, current runtime inputs and latest two metadata recovery pairs remain. Historical receipts identify retired build files but do not imply their continued physical retention. Storage totals are limited to this stage's unique AllocationSize data and authorized retirements, not a new whole-project scan.


## Shared native V1 envelope codec and actual SDK-produced save

NativeSaveEnvelope.h now owns the production V1 data model, fixed 64 Team/64 Player configuration, 133-section validation and Encode/Decode wire operations with an injected 32-byte SHA-256 callable. NativeSaveArchive retains its existing API and delegates to that shared model. The original CNG digest, Windows transaction, Read and WriteAtomic bodies are byte-identical to the changed-file backup. SDK slot counts are statically required to match the wire configuration. Reverse transformation of only the declared class/slot/digest substitutions reproduces the old codec text exactly. Native V1 magic, version, fields, payload ordering, bounds, error paths and checksum placement are unchanged; this is not a retail .Civ5Save schema migration.

One O2 no-SDK C++17 console imports only Kernel32 and includes only the portable envelope header. Its actual self-test passes 17,947 checks, four official SHA known-answer vectors, 3,453 truncations, 148 directed corruptions, 3,603 failure-output atomicity cases and 3,614 digest-callback cases. The SHA implementation is test-only; production continues using unchanged Windows CNG. Independent Python construction matches the full 2,740-byte literal V1 sample and both payload/wire hashes.

The newly authorized retained runtime produced a real 9,612,910-byte native initial autosave. A separate stdin-only console invocation performs 273 checks and decodes/re-encodes every byte identically, with 133 nonempty ordered sections, owned decoded storage and an unchanged source. Its 2,048-byte Bundle payload exactly matches the retained runtime manifest. The actual SDK-backed archive consumer also compiles as C++14 /c, with no SDK executable created or run by this verifier. Its dependency report has 422 occurrences, 391 unique files and 31 repeated include visits; the current snapshot is the historical 390 unique files plus the new envelope header. Historical HostFiles changes predate this stage. These results prove this native envelope boundary, not payload semantics, retail conversion, SDK restoration or save reopening.

Evidence: evidence/native_save_archive/portable_envelope/result.json, five exact child commands, compile_e7df5df8b738d5f4adc1/build_result.json, the retained stdin input and the prechange gzip. Two earlier verifier preflight errors are preserved: missing bounded-read arguments and treating repeated historical includes as distinct files. Both stopped before any build/test command and were repaired without changing generic helpers or production codec behavior. The final build succeeds with empty stderr and no compiler warnings; object/environment intermediates and the compile-only SDK object are retired.

## Authorized isolated runtime trial and human UI stop

The human explicitly authorized resuming the already prepared isolated 64-bit candidate, then approved the Computer Use app access. The restricted first attempt initialized the SDK and wrote its initial native save, but failed on a font-cache hardlink with WinError 5 before presenting a window. Equivalent approved unrestricted attempts prepared the UI without that failure, without changing font-cache attributes, ACLs or source. The first failed session is retired only after its failure report and hashes are retained.

Actual target-window metadata and a fresh activated target screenshot confirm the retained candidate's strategic map window, turn 0 / 4000 BC, selected Settler 2/2 and partial original unit panel. An initial occluded capture showed unrelated foreground content; no input was sent from it, and the exact target was activated and recaptured before the attempted action. The human then stopped Computer Use with physical Escape, so no post-action observation exists and city founding/turn advance are not claimed. No further Computer Use or runtime launch followed the stop. All three bounded backend handles are now terminal; the later trials ended at their configured deadlines, so graceful window close and save reopening remain unverified.

The retained runtime's 24 immutable inputs, original installation, MODS, settings and user saves remain unchanged. This native trial used the retained B11/SDK candidate, not the new source refactor. The old system-freeze hold receipt is historical and unchanged; the direct authorization and subsequent UI stop are recorded separately in evidence/goody_hut/runtime_fonts/isolated_resume_20261024/summary.json and user_stop.json. Further UI automation requires a direct human resumption. Host source is now newer than its retained linked candidate and the current progress index marks that explicitly.

Cleanup removes only the first failed owned session's 15 files/seven empty directories and the oldest body-stage metadata recovery pair. That first native save differs from the retained stdin save: this is retirement of a superseded failed experiment, not identical-content deduplication. The actual stdin save, latest UI session, sources, source rollback, current component build and latest two metadata recovery pairs remain. Storage reporting covers this stage's unique file identities and AllocationSize data, excludes already-existing shared inputs, and does not claim a new whole-project scan or an unmeasured prior source-file allocation delta.

Remaining full-goal gates include matching retail bundle/catalog/ruleset and producer/compression contracts, native retail import, SDK restore and reopening, a newly linked Host for this source revision, full original UI/3D/full-campaign behavior and measured multicore benefit.


## Current native V1 codec linked into a complete private Host

The retained B11 build supplied 544 attested compiler dependencies. Only NativeSaveArchive.h changed, and NativeSaveEnvelope.h added one dependency. All five complete Host units were recompiled with their original flags, including C++17 for the terrain renderer and UTF-8 for the world renderer. The unchanged 18,815,822-byte generated UI header was reused without regenerating installed game assets or copying the project.

The new private Host, 20261024T021245Z_18bbd0dd26e7, is an actual 6,485,504-byte AMD64 PE32+ executable. Its dependency closure has 545 files, its source manifest has 81 entries and all 67 catalog payloads match the preserved catalog byte for byte in the actual PE. The shared native V1 codec is consumed by HostMain; the format, CNG implementation and opaque section semantics remain unchanged.

The first link failed with LNK1104 because uuid.lib was absent from the restricted library search. The five successful COFF objects were retained and only linking was continued. UUID was bound to an existing attested snapshot, making eight fixed default-library candidates and six actual MAP contributors. The raw ten-command history preserves the failed link as well as the successful retry; no repeated compilation, fabricated success or suppressed diagnostic is claimed.

The independent static verifier also identifies two historical external Python frontend revisions after the older Goody seal. Both are outside the Host compiler/source closure and are bound through the authorized runtime request, launcher support-manifest hash and frozen support inventory. All other historical seal rows remain exact. This is not frontend/UI acceptance for the new Host.

Evidence is evidence/native_save_archive/host_relink/18bbd0dd26e70e623276/attestation.json, run.json, link_retry01/authority.json and retirement/result.json, together with the current build_result.json. Two terminated precompile snapshots and the five attested objects were retired after verification: 586 file paths and 58 empty directories, 70,499,616 logical bytes, but only 21,954,704 allocated file-data bytes eligible for reclamation. Shared donor aliases were excluded from physical reclamation and their attributes, file IDs and content were preserved. The prior candidates, sources, linked executable, frozen dependency inputs and private native saves remain.

The new Host has not been executed or installed into the retained prepared runtime. The current SDK implementation changes, including the earlier Great Work correction, are not newly linked into that runtime by this Host-only build. The human Escape stop remains in force for further UI automation. Native restoration/reopening, retail producer/catalog/ruleset contracts, original UI/3D/full-campaign acceptance, save/mod compatibility and measured multicore benefit remain full-goal gates.


## Current Host and Great Work SDK private preparation, 2026-10-24

The current attested Host (20261024T021245Z_18bbd0dd26e7, b96055dc...) and the retained Great Work SDK delta (430f3122...) are now paired in the private new-game-only runtime 20261024T031412Z_e06aeb61ed6a. This is preparation only: no Host, GameCore or window was executed. The default release and older private candidates/saves remain unchanged. The earlier physical Escape stop still requires direct human resumption before any new native/UI trial.

The production runner now validates the exact attested Host after its five final objects were retired. It rehashes all retained dependencies and binds the two historical documentation identities to their exact gzip recovery copies. The SDK validator accepts the distinct pinned retained-static schema, validates its parent and 165 objects (164 reused plus the replacement CvUnit), and preserves the unknown historical compiler/linker exit codes as not_retained. The old CvUnit identity is provenance, not a claim that its live source still has the old hash. Component and preparation regression coverage totals 67 tests; these are not game/runtime proof.

The actual prepared runtime has 24 backend inputs. Only Host, GameCore and bundle.manifest differ from the previous candidate; fifteen inputs are read-only cache hardlinks and thirteen preexisting cache file identities are reused. The two writable private databases remain separate file identities, and six current frontend tools are freshly frozen. Original terrain/unit data are reused. The changed Host and SDK hashes produce a new bundle identity; older native saves were not migrated, and the save-loading launcher remains disabled.

Two preparation-only failures are preserved. The first exposed a guard incorrectly interpreting Python bytecode as a filesystem path; its regression test now passes. The second hit the restricted environment's read-only hardlink permission, before any runtime input was installed; its two empty runtime/evidence directories were removed. The bounded preparation succeeded with the same cache inputs in the approved environment. No repeated SDK/Host compilation was needed.

Evidence is evidence/sdk_runtime_play/latest_pair_preparation/materialization_retry02/{result,audit}.json and evidence/interactive_game/20261024T031412Z_e06aeb61ed6a/request.json. The scoped allocation audit records 81,703,872 bytes (about 77.9 MiB) for this new runtime, evidence and selected new cache data, excluding thirteen existing shared file identities. It excludes changed source/test files, later publication receipts and an unmeasured whole-project net. Small failed-attempt receipts and changed-file recovery gzip files remain for provenance; there are no failed binary snapshots or test fixtures to retain.

Execution, new-save/reopen with this exact pair, SDK restore, retail conversion, original UI/3D/full campaign, original save/mod compatibility and measured multicore benefit remain unverified full-goal gates.


## Source-order native restore contract in the current private Host

The current private Host is 20261024T042219Z_e6399c82ee5c (6,513,152-byte AMD64 PE32+, SHA256 2212f0e5...).
Four production restore paths now use a shared source-order contract instead of excluding the entire Game section.
It parses GameFront, GameTail and embedded database through exact EOF, requires the other 132 sections byte for byte,
and permits only audited SDK reload effects: session/replay increments, exact localized text, AI and game-state
normalization, advisor set reordering with exact unique values, and the actual NEW_RANDOM_SEED policy. Jon RNG
reseeding preserves call count and advances its unsigned reset count; Map RNG remains exact. Unsafe signed session
increments are rejected before SDK stream reads. Victory width and seed policy come from the active SDK state.
Native V1 fields and version are unchanged.

Portable O2 and Od/RTC1 each pass 1,244 checks, including 102 truncations, 242 directed corruptions, 352 failure-output
atomicity cases and 36 valid cases. The older native fixture and latest prepared pair's actual initial/final saves
pass complete source-order Game inspection with the explicit width-five profile. The initial/final saves are from
one live session, not a restore pair; their differences do not prove restore corruption or accepted reload deltas.
Python independently checks checksums and Bundle identity; test-only SHA does not replace production Windows CNG.

The private build reuses 585 immutable frozen aliases (70,549,125 logical bytes) and copies 201,983 source bytes.
All five units compile once with retained C++14/C++17 and charset settings, then one UUID-inclusive link succeeds:
seven child commands including environment setup. Dependencies are 465/266/270/279/301, union 549, with 85 source
manifest rows and 592 current-source rows. Independent static inspection confirms the same 24 PE imports, all 67
exact ordered UI payloads and one read-only contract marker. Marker inclusion does not prove runtime restoration.

The resumed prior b9/430f3122 pair, 20261024T031412Z_e06aeb61ed6a, showed its turn-zero window and exited normally
after 76.622 seconds with initial/final native saves and GameCore unload recorded. Physical Escape stopped Computer
Use before a confirmed city-found or turn-advance action. Its 24 immutable inputs remain exact. This used the prior
b9 Host and does not contain the new contract. The default runtime is unchanged; another native/UI trial requires
direct human resumption. The new current Host is linked but has not been executed or prepared into a new runtime.

Evidence: evidence/native_restore_contract/component_retry01/result.json, latest_pair_saved_game_retry01/result.json,
host_build/e6399c82ee5c15c73b86/{run,attestation}.json and retirement/result.json, together with
evidence/sdk_runtime_play/latest_pair_execution/terminal_audit.json. The first portable compile's narrowing warning
is preserved; explicit int16_t literals fix it without warning suppression. A follow-up wrapper's working-directory
guard stopped before execution; four corrected stdin-only inspections succeeded without another build. Independent
audit codec setup rejections are retained in its attestation.

After static validation, five COFF objects and the environment script are retired: 22,120,027 logical bytes and
22,130,832 allocated file-data bytes measured before last-link deletion; six empty directories are removed. The
executable, maps, source/dependency inputs, command/log receipts, gzip recovery and native saves remain. No large
object backup is created. These are scoped file-data metrics, not a whole-project or volume-free delta. Full SDK
restore/reopen, retail producer/catalog/ruleset conversion, original UI/3D/campaign, original save/mod compatibility
and measured multicore benefit remain incomplete.


## Current restore-contract Host and SDK private pair preparation

The linked e639 restore-contract Host (2212f0e5...) is now paired with the existing 430f3122... Great Work SDK in private run 20261024T050152Z_fd0465b26387. Both actual input gates passed without native execution. All 24 runtime inputs and 87 protected inputs were rehashed; 15 immutable cache hardlinks include 14 existing identities and one new Host cache payload. The two writable databases have private identities; six UI tools are frozen.

The new gate component suite passed 20 tests. Existing regression tests passed 73 checks; one retained test still expects the older 60984 SDK and correctly rejects the current CvUnit delta. The selected 430f SDK was independently validated successfully. The original failing receipt is preserved rather than relabelled as a passing suite.

This candidate remains new-game-only, with its save-loading launcher disabled. The preceding b9 trial and its native saves, the default release, original game, mods, settings and saves are retained. No Host/SDK/UI was started. The second physical Escape hold remains in force. City founding, turns, actual SDK restore/reopen, retail saves, original UI/3D/full campaign and measured multicore acceptance remain unverified.
