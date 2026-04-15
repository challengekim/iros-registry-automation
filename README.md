# IROS 등기부등본 자동화 도구

법인 등기부등본 일괄 다운로드를 위한 자동화 도구입니다.

## 전체 워크플로우

```
엑셀(사업자등록번호) → bizno 조회 → IROS 장바구니 → 수동결제 → 자동다운로드 → CDD 엑셀 생성
```

## 장바구니 검색 방식 비교

| 항목 | 상호명 기반 (`iros_cart.py`) | 법인등록번호 기반 (`iros_cart_by_corpnum.py`) |
|------|------|------|
| 검색 키 | 회사명 (예: "스마트솔루션") | 법인등록번호 13자리 (예: "110111-1234567") |
| 입력 파일 | JSON 배열 `["회사A", "회사B"]` | JSON 객체 `{"번호": "회사명"}` |
| 장점 | 회사명만 있으면 됨 | 정확한 검색, 동명이인 없음 |
| 단점 | 사명변경/특수문자 시 검색 실패 가능 | 법인등록번호를 미리 알아야 함 |
| 권장 상황 | 일반적인 대량 처리 | 상호명 검색 실패 건 재시도 |

> **추천**: 먼저 상호명 기반으로 전체 처리 → skip/fail 건을 법인등록번호 기반으로 재시도

---

## 사전 준비

### 설치

```bash
pip install -r requirements.txt
playwright install chromium
```

### 설정

`config.json.example`을 복사하여 `config.json` 생성 후 경로 수정:

```bash
cp config.json.example config.json
```

주요 설정 항목:

| 키 | 설명 | 기본값 |
|----|------|--------|
| `excel_path` | 고객 엑셀 파일 경로 | `./data/고객리스트.xlsx` |
| `excel_sheet` | 엑셀 시트명 | `Sheet1` |
| `excel_pin_column` | 사업자등록번호 열 번호 | `6` |
| `excel_userid_column` | User ID 열 번호 | `10` |
| `companies_list` | 상호명 기반 검색용 회사 목록 | `./data/iros_companies.json` |
| `corpnum_list` | 법인등록번호 기반 검색용 목록 | `./data/iros_corpnums.json` |
| `save_dir` | PDF 저장 경로 | `~/Downloads/등기부등본` |
| `cdd_output` | CDD 엑셀 출력 경로 | `./output/CDD_고객정보.xlsx` |

### 필요 계정

- IROS (인터넷등기소): https://www.iros.go.kr 회원가입

---

## 사용 방법

### Step 1: Bizno 조회 (사업자등록번호 → 법인정보)

```bash
python3 bizno_scrape.py
# 또는 설정 파일 지정
python3 bizno_scrape.py config.json
```

- 엑셀에서 사업자등록번호를 읽어 bizno.net에서 법인명, 연락처, 법인등록번호 등을 조회합니다
- 휴폐업 상태(계속사업자/폐업자/휴업자)도 자동 확인합니다
- 중간에 중단해도 캐시 덕분에 이어서 실행 가능합니다
- 결과: `data/bizno_results.json`, `data/iros_companies.json`

---

### Step 2: IROS 장바구니 담기 (자동화)

두 가지 방식 중 선택하여 사용합니다.

#### 방법 A: 상호명 기반 검색 (iros_cart.py)

회사명으로 IROS를 검색하여 장바구니에 담습니다. 대부분의 경우 이 방식을 먼저 사용합니다.

**입력 파일 형식** (`data/iros_companies.json`):
```json
[
  "스마트솔루션",
  "디지털마케팅",
  "클라우드서비스"
]
```

> Step 1 (bizno_scrape.py) 실행 시 자동 생성됩니다.

**실행**:
```bash
# 처음부터 시작
python3 iros_cart.py

# 설정 파일 지정 + 50번째부터 시작 (중단 후 재개)
python3 iros_cart.py config.json 50
```

**실행 과정**:
1. 터미널에서 스크립트 실행
2. 브라우저가 자동으로 열림
3. iros.go.kr에 **수동 로그인** (공인인증서/간편인증)
4. 로그인 완료 후 터미널에서 **Enter** 입력
5. 자동 처리 시작:
   - 회사명 검색
   - 검색 결과에서 "살아있는 등기" 선택 (없으면 폐쇄등기도 선택)
   - 법인등기부등본(말소사항포함) 체크
   - 장바구니에 추가
   - 다음 회사로 반복

**터미널 출력 예시**:
```
총 220개, 이미처리 0개, index 0부터 시작

[1/220] 스마트솔루션 ✓ cart:10 (total:1)
[2/220] 디지털마케팅 ✓ cart:11 (total:2)
[3/220] 클라우드서비스 - skip
[4/220] 웹에이전시 ✓ cart:12 (total:3)

  >> 완료:3 실패:0 건너뜀:1
```

**상태 설명**:
- `✓ cart:N` — 성공. N은 현재 장바구니 항목 수
- `- skip` — 검색결과 없음 (사명변경, 특수문자 등)
- `✗ error:...` — 실패. 네트워크 오류 또는 로그인 세션 만료

**로그 파일**: `logs/cart_log.json`
```json
{
  "completed": ["스마트솔루션", "디지털마케팅"],
  "failed": [{"name": "실패회사", "error": "error:timeout", "time": "2026-04-09T12:34:56"}],
  "skipped": ["검색안되는회사"]
}
```

#### 방법 B: 법인등록번호 기반 검색 (iros_cart_by_corpnum.py)

법인등록번호(13자리)로 IROS를 검색합니다. 상호명 검색이 실패한 건을 정확하게 재시도할 때 사용합니다.

**입력 파일 형식** (`data/iros_corpnums.json`):
```json
{
  "110111-1234567": "스마트솔루션",
  "134511-0012345": "디지털마케팅코리아",
  "110111-9876543": "클라우드서비스"
}
```

> 키: 법인등록번호 (하이픈 있어도/없어도 OK, 자동 제거됨)
> 값: 회사명 (로그 식별용, 검색에는 사용 안 함)

**입력 파일 만드는 방법**:

bizno_scrape.py 결과(`data/bizno_results.json`)에서 법인등록번호가 있는 건을 추출합니다:

```python
import json

with open("data/bizno_results.json") as f:
    data = json.load(f)

# 상호명 검색 실패 목록 (skip/fail 건)
with open("logs/cart_log.json") as f:
    cart_log = json.load(f)

failed_names = set(cart_log.get("skipped", []))
failed_names.update(item["name"] if isinstance(item, dict) else item for item in cart_log.get("failed", []))

# 법인등록번호 매핑 생성
corpnums = {}
for item in data:
    name = item.get("company_name", "")
    corp_reg = item.get("corp_reg_number", "")
    if corp_reg and name in failed_names:
        corpnums[corp_reg] = name

with open("data/iros_corpnums.json", "w") as f:
    json.dump(corpnums, f, ensure_ascii=False, indent=2)

print(f"법인등록번호 {len(corpnums)}건 추출")
```

**실행**:
```bash
# 기본 설정으로 실행
python3 iros_cart_by_corpnum.py

# 설정 파일 지정
python3 iros_cart_by_corpnum.py config.json
```

**실행 과정**:
1. 터미널에서 스크립트 실행
2. 브라우저가 자동으로 열림
3. iros.go.kr에 **수동 로그인**
4. 로그인 완료 후 터미널에서 **Enter** 입력
5. 자동 처리 시작:
   - "등록번호검색" 탭으로 전환
   - 법인등록번호 입력 (13자리, 하이픈 자동 제거)
   - 검색 결과 선택
   - 법인등기부등본(말소사항포함) 체크
   - 장바구니에 추가
   - 다음 건으로 반복

**터미널 출력 예시**:
```
총 15개, 이미처리 0개, 남은 15개

[1/15] 110111-1234567 (스마트솔루션) ✓ cart:221 (total:1)
[2/15] 134511-0012345 (디지털마케팅코리아) ✓ cart:222 (total:2)
[3/15] 110111-9876543 (클라우드서비스) - skip
```

**로그 파일**: `logs/cart_corpnum_log.json`

> **팁**: 상호명 기반에서 이미 장바구니에 담긴 건수 위에 추가되므로, cart 숫자가 이전 결과에서 이어집니다.

---

### Step 3: 결제 (수동 필수)

> **이 단계는 반드시 사람이 직접 수행해야 합니다.**
> IROS 결제는 카드 정보 입력이 필요하며, 현재 **한 번에 최대 10건까지만** 결제할 수 있습니다.

장바구니 스크립트 완료 후 자동으로 결제대상목록 페이지로 이동합니다.

**결제 과정**:
1. 결제대상목록에서 좌측 전체선택 또는 10건 선택
2. 결제하기 버튼 클릭
3. 카드 정보 입력 → 결제 완료
4. 남은 건이 있으면 1-3번 반복

**결제 횟수 계산**:
- 200건이면 → 10건씩 20번 결제
- 217건이면 → 10건 × 21번 + 7건 × 1번 = 22번 결제

> 💡 혹시 10건 이상 한 번에 결제하는 방법을 발견하시면 [Issue](https://github.com/challengekim/iros-cdd-automation/issues)로 제보 부탁드립니다!

---

### Step 4: 열람/저장/파일명변경 (자동화)

```bash
python3 iros_download.py 220          # 220 = 결제 완료된 총 건수
# 또는
python3 iros_download.py config.json 220
```

1. 브라우저가 열리면 iros.go.kr **로그인**
2. 로그인 후 터미널에서 **Enter**
3. 자동으로: 열람 → 확인 → 저장 → 파일명변경 → 닫기 반복

동작 원리:
- 열람 후 항목이 목록에서 사라지므로 항상 첫 번째 버튼을 클릭합니다
- `~/Downloads/등기부등본/회사명.pdf`로 자동 저장됩니다
- 연속 3회 실패 시 신청결과 페이지로 자동 복구합니다
- 중단 후 재실행 시 이미 받은 파일은 폴더에 있으므로 건너뜁니다

> ⚠️ **모니터링 필요**: 약 100건마다 브라우저가 멈출 수 있습니다. 멈추면 브라우저를 닫고 다시 실행하세요.

---

### Step 5: CDD 엑셀 생성

```bash
python3 cdd_generate.py
# 또는
python3 cdd_generate.py config.json
```

- bizno 정보 + User ID + 다운로드 상태를 종합하여 CDD 엑셀을 생성합니다
- 결과: `output/CDD_고객정보.xlsx`

---

## 중단 후 재개

모든 스크립트는 로그 파일에 진행 상황을 저장하므로, 중단 후 재실행하면 이미 처리된 건은 자동으로 건너뜁니다.

```bash
# 상호명 기반 — 50번 인덱스부터 재개
python3 iros_cart.py config.json 50

# 법인등록번호 기반 — 자동으로 미처리 건만 실행
python3 iros_cart_by_corpnum.py

# 다운로드 — 이미 받은 파일은 건너뜀
python3 iros_download.py 220
```

---

## 로그 리셋

처음부터 다시 실행하려면:

```bash
# 상호명 기반 로그 초기화
echo '{"completed":[],"failed":[],"skipped":[]}' > logs/cart_log.json

# 법인등록번호 기반 로그 초기화
echo '{"completed":[],"failed":[],"skipped":[]}' > logs/cart_corpnum_log.json

# 다운로드 로그 초기화
echo '{"completed":[],"failed":[],"skipped":[]}' > logs/download_log.json
```

캐시까지 초기화하려면:

```bash
rm data/bizno_cache.json data/bizno_results.json data/iros_companies.json
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 장바구니에서 회사 검색 안됨 | 사명변경/해산/청산/특수문자 | 법인등록번호 기반으로 재시도 |
| "등록번호검색" 탭 전환 안됨 | IROS 페이지 로딩 지연 | 스크립트 재실행 |
| "열람 버튼 못 찾음" | 결제 안 된 항목 | 결제 확인 후 재실행 |
| "저장 버튼 클릭 실패" | 문서 로딩 지연 | 스크립트 재실행 |
| "다운로드 안됨" | 네트워크 문제 | 재실행 |
| 브라우저 멈춤 (약 100건마다) | IROS 서버 부하 | 브라우저 닫고 인덱스 지정하여 재실행 |
| PermissionError: ~/Downloads | macOS 보안 정책 | 시스템 설정 > 개인정보 보호 > 전체 디스크 접근 허용 |
| bizno 조회 실패 | 네트워크 차단 | VPN 해제 또는 잠시 후 재시도 |
| "신청사건 처리중" 팝업 반복 | IROS 서버 처리 지연 | 자동 dismiss 처리됨 (최신 버전) |

---

## 파일 구조

```
iros-cdd-automation/
├── README.md                    # 이 문서
├── config.json.example          # 설정 예시
├── requirements.txt             # Python 패키지
├── bizno_scrape.py              # Step 1: bizno.net 조회
├── iros_cart.py                 # Step 2A: 장바구니 (상호명 기반)
├── iros_cart_by_corpnum.py      # Step 2B: 장바구니 (법인등록번호 기반)
├── iros_download.py             # Step 4: 열람/저장 자동화
├── cdd_generate.py              # Step 5: CDD 엑셀 생성
├── data/                        # 데이터 (gitignore)
│   ├── bizno_cache.json         # 조회 캐시
│   ├── bizno_results.json       # bizno 조회 결과
│   ├── iros_companies.json      # 상호명 목록 (Step 2A용)
│   └── iros_corpnums.json       # 법인등록번호 목록 (Step 2B용)
├── logs/                        # 로그 (gitignore)
│   ├── cart_log.json            # 상호명 기반 장바구니 로그
│   ├── cart_corpnum_log.json    # 법인등록번호 기반 장바구니 로그
│   └── download_log.json        # 다운로드 로그
└── output/                      # 결과물 (gitignore)
    └── CDD_고객정보.xlsx
```

---

## 주의사항

- `config.json`은 `.gitignore`에 포함되어 있습니다. 커밋되지 않으니 직접 관리하세요.
- IROS 결제는 카드 정보가 필요하므로 반드시 수동으로 진행합니다.
- bizno.net 과부하 방지를 위해 요청 간 자동으로 대기합니다 (건당 약 2초).
- 대량 처리 시 IROS 서버 부하를 고려하여 약 100건마다 브라우저 상태를 확인하세요.
