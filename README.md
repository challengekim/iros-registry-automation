# IROS 등기부등본 자동화 도구

법인 등기부등본 일괄 다운로드를 위한 자동화 도구입니다.

## 전체 워크플로우

```
엑셀(사업자등록번호) → bizno 조회 → IROS 장바구니 → 수동결제 → 자동다운로드 → CDD 엑셀 생성
```

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
| `excel_sheet` | 엑셀 시트명 | `태우님 추가 요청` |
| `excel_pin_column` | 사업자등록번호 열 번호 | `6` |
| `excel_userid_column` | User ID 열 번호 | `10` |
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

### Step 2: IROS 장바구니 담기 (자동화)

```bash
python3 iros_cart.py
# 특정 인덱스부터 시작
python3 iros_cart.py config.json 50
```

1. 브라우저가 열리면 iros.go.kr **로그인**
2. 로그인 후 터미널에서 **Enter**
3. 자동으로 회사명 검색 → 법인등기부등본(말소사항포함) 선택 → 장바구니 담기

- 검색결과 없는 회사는 자동 skip
- 10건마다 로그 자동 저장, 중단 후 이어서 가능
- 완료 후 결제대상목록 페이지로 자동 이동

### Step 3: 결제 (수동)

- IROS는 한 번에 **최대 10건씩** 결제 가능
- 결제대상목록에서 10건 선택 → 결제 → 반복
- 모든 건 결제 완료까지 반복

### Step 4: 열람/저장/파일명변경 (자동화)

```bash
python3 iros_download.py 220
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

### Step 5: CDD 엑셀 생성

```bash
python3 cdd_generate.py
# 또는
python3 cdd_generate.py config.json
```

- bizno 정보 + User ID + 다운로드 상태를 종합하여 CDD 엑셀을 생성합니다
- 성공 → 실패 → 미완료 순으로 정렬됩니다
- 결과: `output/CDD_고객정보.xlsx`

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| "열람 버튼 못 찾음" | 결제 안 된 항목 | 결제 확인 후 재실행 |
| "저장 버튼 클릭 실패" | 문서 로딩 지연 | 스크립트 재실행 |
| "다운로드 안됨" | 네트워크 문제 | 재실행 |
| 장바구니에서 회사 검색 안됨 | 사명변경/해산/청산 | bizno에서 현재 상태 확인 |
| PermissionError: ~/Downloads | macOS 보안 정책 | 시스템 설정 > 개인정보 보호 > 전체 디스크 접근 허용 |
| bizno 조회 실패 | 네트워크 차단 | VPN 해제 또는 잠시 후 재시도 |

---

## 로그 리셋

처음부터 다시 실행하려면:

```bash
echo '{"completed":[],"failed":[],"skipped":[]}' > logs/cart_log.json
echo '{"completed":[],"failed":[],"skipped":[]}' > logs/download_log.json
```

캐시까지 초기화하려면:

```bash
rm data/bizno_cache.json data/bizno_results.json data/iros_companies.json
```

---

## 파일 구조

```
iros-cdd-automation/
├── README.md                # 이 문서
├── config.json.example      # 설정 예시
├── requirements.txt         # Python 패키지
├── bizno_scrape.py          # Step 1: bizno.net 조회
├── iros_cart.py             # Step 2: IROS 장바구니 자동화
├── iros_download.py         # Step 4: 열람/저장 자동화
├── cdd_generate.py          # Step 5: CDD 엑셀 생성
├── data/                    # 데이터 (gitignore 대상)
│   ├── bizno_cache.json     # 조회 캐시 (재실행 시 재사용)
│   ├── bizno_results.json   # bizno 조회 결과
│   └── iros_companies.json  # IROS 검색용 정제 회사명 목록
├── logs/                    # 로그 (gitignore 대상)
│   ├── cart_log.json        # 장바구니 담기 로그
│   └── download_log.json    # 다운로드 로그
└── output/                  # 결과물 (gitignore 대상)
    └── CDD_고객정보.xlsx
```

---

## 주의사항

- `config.json`은 `.gitignore`에 포함되어 있습니다. 커밋되지 않으니 직접 관리하세요.
- IROS 결제는 카드 정보가 필요하므로 반드시 수동으로 진행합니다.
- bizno.net 과부하 방지를 위해 요청 간 자동으로 대기합니다 (건당 약 2초).
- 대량 처리 시 IROS 서버 부하를 고려하여 열람 간격을 두는 것을 권장합니다.
