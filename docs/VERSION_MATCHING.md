# 버전 판정과 과거 기록 호환성

0.4는 공개 OSV 스냅샷에 대한 **릴리스 버전 포함 여부**를 판정한다. 패키지의 실제 악용 가능성, 최신 취약점 전체, 배포판 backport까지 판정하는 도구는 아니다.

| 입력 | 처리 |
|---|---|
| `affected.versions`의 명시 일치 | `exact_version` |
| PyPI `ECOSYSTEM` 범위 | `packaging.version.Version`의 PEP 440 순서 |
| `SEMVER` 범위 | `semver.Version`의 엄격한 SemVer 2.0 순서 |
| `introduced` / `fixed` | 시작 포함 / 수정 경계 제외 |
| `last_affected` | 마지막 영향 버전 포함 |
| 여러 구간·순서가 섞인 이벤트 | 정렬 후 상태 전이; 여러 range는 합집합 |
| `introduced: "0"` / `limit: "*"` | 모든 버전보다 앞선 시작 / 무한 상한 |
| 여러 `limit` | 하나 이상의 상한보다 작은 버전만 범위 검사 |
| 버전 누락 | `version_missing` |
| 알 수 없는 ecosystem·잘못된 버전·잘못된 이벤트 | `ambiguous` |
| PyPI local build (`+localpatch`) | 명시 목록에 없으면 `ambiguous`; upstream과 임의 동일시하지 않음 |
| release range 없이 GIT 범위만 있음 | `ambiguous`; commit graph는 조회하지 않음 |

`range_version`은 해석 가능한 범위에 들어간 버전이다. `exact_version`과 동일하게 영향 버전 판정이 가능하지만, CVSS가 없으면 우선순위는 계속 사람이 검토한다. 공급자가 임의로 판정이나 출처를 바꾸면 독립 verifier가 거부한다.

릴리스 문자열 질의에서 GIT 범위는 비교 가능한 릴리스 범위와 별도로 취급한다. 같은 affected 항목에 release range가 있으면 그것을 평가하고, GIT commit hash와 패키지 버전 문자열을 비교하지 않는다. 해석 가능한 범위 중 하나라도 포함하면 후보로 남긴다. 포함 범위는 없지만 해석 불가능한 release range가 남으면 불확실 후보로 보존한다. 모든 적용 가능한 범위 밖에 있는 경우에도 출력의 `unmatched`는 **해당 스냅샷에서 후보가 없다는 뜻**이다.

명시된 affected 목록과 범위의 합집합이 기준이며, package PURL에 버전이 들어 있다는 사실만으로 영향 버전이라고 판정하지 않는다. 현재 PURL identity는 qualifier를 보존하고 정확히 비교한다. 생태계별 모든 package-name alias, Maven·Conda·Debian 버전 순서 및 Git reachability는 지원 범위에 포함하지 않는다.

## 기존 분석 기록

- 이전 `result.schema_version = 2.0`은 당시의 명시 버전·불확실 범위 규칙으로 다시 검증한다.
- 새 실행은 `2.1`을 저장하고 릴리스 범위를 평가한다. 실행 기록 자체를 새 판정으로 덮어쓰지 않는다.
- `tests/fixtures/legacy-v03`는 공개 0.3 커밋 `b7ee438`에서 생성한 합성 배포 사례의 고정 산출물이다. 기존 5개 후보와 검토 해시를 보존하고, 같은 입력의 새 실행에서는 3개 후보가 되는 것을 회귀 테스트로 확인한다.
- 과거 검토는 과거 결과에만 해당한다. 새 규칙으로 재분석한 결과를 승인하려면 새 검토가 필요하다.

## 명세와 검증

구현·경계 검사는 [OSV schema](https://ossf.github.io/osv-schema/), [PEP 440 버전 비교](https://packaging.pypa.io/en/stable/version.html), [SemVer 2.0](https://semver.org/)를 기준으로 한다. 고정 경계·prerelease·epoch·post-release·local build·복수 구간·상한·잘못된 이벤트 및 미지원 타입을 테스트한다. 공개 출처에서 만든 72개 사례는 계약 검사이며 독립 전문가 라벨의 정확도 평가가 아니다.
