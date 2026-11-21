# 현지화 문자열 저장과 문법 기준 기록

2026-09-25 갱신이랍니다. SDK의 `SharedString`과 `StringParameter` 저장·복사 코드를 x64로 구현했사와요. 이 문서는 현지화 내부 부품의 구현과 검증 기록이며, 후속 [문장·사전 통합](M2_LOCALIZATION_INTEGRATION.md)에서 GameCore의 현지화 16개 가져오기를 모두 연결했사와요. 전체 현지화 API와 실게임 검증은 여전히 남아 있답니다.

## 요구사항과 결과

| ID | 요구사항 | 확인한 범위 |
|---|---|---|
| LV01 | SDK 선언과 객체 배치 유지 | SDK 헤더 수정 없이 실제 SharedString 메서드를 AMD64 DLL로 구현 |
| LV02 | 원본 바이트·부분 문자열·복사 의미 | VC9 원본 DLL과 x64 DLL의 50줄 실행 기록 정확히 일치 |
| LV03 | 길이 계산과 잘못된 입력 방어 | size_t 덧셈 넘침을 피하는 범위 검사, NULL/비영 길이와 최대 크기 거부, 기존 부분 문자열 범위 보존 |
| LV04 | 공유 저장소 수명 | 원래 객체를 비운 뒤 복사본 내용 유지, 작업자 4개의 독립 복사본 4,096개 내용·부분 범위 확인 |
| LV05 | 중첩 매개변수 복사 | x64에서 자식 매개변수 벡터 복사 후 원본 변경이 복사본에 전파되지 않음 |
| LV06 | 원본 문법과 변경 의미 조사 | 공유 저장·형태 메타데이터·문법·대입의 4개 원본 실행 모드 기록 |

직접 작성한 x64 구현과 시험 프로그램은 `/W4 /WX`에서 경고 없이 빌드되었사와요. SDK 헤더는 외부 헤더로 분류하며 기존 선언의 경고 수준은 별도로 관리하와요. x86 참조에는 기존 SDK의 C4251 경고가 있답니다. 두 시험 실행 파일의 직접·전이 DLL 가져오기를 검사했으며 Civ V나 GameCore를 로드하지 않았사와요.

## 확인한 저장 계약

- 기본 생성 객체에는 버퍼가 없고, 명시적으로 만든 0 길이 문자열에는 종료 문자 1바이트가 있사와요. `(NULL, 0)`도 원본처럼 1바이트 빈 버퍼를 소유하와요.
- 버퍼 전체 길이에는 종료 문자가 포함되고, 논리 문자열 길이에는 포함되지 않사와요. 내장 NUL은 별도 길이로 보존하와요.
- 복사본은 불변 바이트 저장소를 공유하지만 offset·length는 각각 소유하와요. 버퍼 끝 바로 다음 위치의 0 길이 부분 문자열까지 허용하되 그 포인터를 역참조하지 않사와요.
- 범위를 벗어난 부분 문자열 요청은 실패하며 이전 범위를 유지하와요. `offset + length`의 넘침으로 유효 범위라고 판단하지 않도록 뺄셈 기반으로 검사하와요.
- `StringParameter`의 생성·복사·소멸은 공개 SDK에 선언되어도 실제 원본 import library에서 찾을 수 없었사와요. 따라서 이 내부 형식의 초기화·깊은 복사는 새 구현의 계약 검사이며 원본 바이너리 동등성으로 주장하지 않사와요.

## 원본 문법 조사에서 확인한 다음 구현의 조건

아래 내용은 원본 시험 기록이며 아직 새 `Localization::String` 구현의 통과 결과가 아니랍니다.

- `|`는 형태를 나누며 빈 형태와 마지막 빈 형태도 유지하와요. 중괄호 안의 `|`도 먼저 형태를 나누는 동작을 확인했사와요.
- 유효한 형태의 기본 성별·복수형은 각각 masculine·1이었고, 잘못된 형태 번호의 조회는 0을 반환했사와요.
- 성별 자료의 `|`는 형태 구분, `:`는 같은 형태의 추가 속성 구분이와요. 복수형 자료도 `|`로 형태를 나누며 현재 언어가 지원하지 않는 번호는 거부하와요.
- C 문자열을 대입해도 기존에 넣은 인수는 유지하와요. 따라서 단순히 모든 필드를 비우는 대입 구현은 원본과 다르답니다.
- 변환 없는 `{TXT_NESTED}`는 바깥 인수로 내부 문구를 합성하지만, 변환이 붙은 조회는 같은 전파를 보장하지 않았사와요. 중첩 분기·인수·문구 키를 구분해 구현해야 하와요.
- `plural`은 값 자체가 아닌 언어의 복수형 번호로 분기를 선택하와요. 시험의 영어 규칙에서는 1만 단수, 0·2·3은 두 번째 형태였사와요. 마지막 선택지를 끝내는 `;`의 유무도 결과에 영향을 주었답니다.
- 숫자 하나를 받는 `SetPlurality(size_t)`는 정상처럼 보이는 입력에도 false를 반환하고, 문자열 `SetPlurality("2")`는 두 형태를 변경했사와요. 이 차이는 다음 메타데이터 구현에서 결함인지 의도인지 검토할 항목이랍니다.
- `HasForm`과 `GetArgumentCount` 등 일부 선언도 원본 연결 라이브러리에 없었사와요. 헤더 계약과 실제 비교 가능한 동작을 구분하와요.

## 산출물과 재현

구현은 `Source/Providers/Localization/SdkLocalizationValues.cpp`, 독립 DLL·연결 라이브러리는 `Build/Localization/values_x64`, 기록은 `evidence/localization/values_candidate`, 원본 관찰은 `values_reference`와 `grammar_reference`에 있사와요. 검토용 묶음은 `Stage/LocalizationValues`랍니다.

프로젝트 폴더에서 아래 순서로 재현하와요. 기존 현지화 숫자 참조 빌드가 먼저 필요하와요.

```powershell
python tools/probe_localization_grammar.py --kind values
python tools/build_localization_values.py
python tools/verify_localization_values.py
python tools/probe_localization_grammar.py
python tools/stage_localization_values.py
python tools/verify_project.py
```

새 실행 없이 기록만 검사하려면 `python tools/localization_values_evidence.py`를 사용하와요. 이 문서는 값 저장 구성요소의 검증 기록이랍니다. 문장·사전·언어 수명을 연결한 후속 단계에서 전체 연결 요구를 **36개**로 줄였사와요. 모든 할당 실패·전체 현지화 API·실게임 호환성은 남아 있답니다. [후속 통합 기록](M2_LOCALIZATION_INTEGRATION.md)을 참고하시와요.
