---
name: iros
description: Bulk-issue Korean corporate/realty registry copies (등기부등본) from iros.go.kr. Use for 법무·회계·VC·M&A workflows that need 수십~수천 건 등기 일괄 발급. Login + payment remain manual.
type: workflow
languages: [ko, en]
---

# IROS 등기부등본 자동화 스킬

## When to invoke

이 스킬을 사용하는 경우:
- 사용자가 **등기부등본**, **인터넷등기소**, **iros**, **법인등기**, **부동산등기** 를 언급하고 **대량 발급** 또는 **자동화** 맥락이 있을 때
- 수십~수천 건의 법인/부동산 등기부등본을 일괄로 장바구니에 담거나 다운로드해야 할 때
- M&A 실사, VC 포트폴리오 검토, 법무법인/회계법인 대량 등기 조회가 필요할 때
- `data/iros_corpnums.json` 또는 `data/iros_companies.json` 파일을 준비해 자동 발급 요청을 할 때

## When NOT to invoke

이 스킬을 **사용하지 않는** 경우:
- 단건 수동 조회 (브라우저에서 직접 검색하는 것이 더 빠름)
- 이미 결제 완료된 항목을 IROS UI 일괄열람에서 다시 받으려 할 때 (IROS 웹 UI 사용 권장)
- **결제 자동화** 요청 — 결제는 수동 전용, 이 도구는 결제 자동화를 지원하지 않음

## Prerequisites

1. **Chrome/Chromium** 설치 (`playwright install chromium`)
2. **TouchEn nxKey** 보안 프로그램 사전 설치 (IROS 로그인 페이지에서 안내에 따라 설치)
3. **IROS 계정** (iros.go.kr 회원가입 + 공동인증서/간편인증 수단 준비)
4. **패키지 설치**:
   ```bash
   pip install iros-registry-automation
   playwright install chromium
   ```
5. **설정 파일 준비**:
   ```bash
   cp config.json.example config.json
   # config.json 편집: download_dir, corpnum_list 등 경로 확인
   ```

## Available subcommands

| 명령어 | 설명 | 필요 입력 파일 |
|--------|------|----------------|
| `iros wizard` | 대화형 메뉴 실행 (전체 기능) | — |
| `iros corp-cart --by-corpnum` | 법인등록번호 기반 장바구니 담기 (기본 권장) | `data/iros_corpnums.json` |
| `iros corp-cart --by-name` | 상호명 기반 장바구니 담기 | `data/iros_companies.json` |
| `iros corp-download [--total N]` | 법인등기 결제 후 열람·저장 | 없음 (결제 완료 후) |
| `iros realty-cart` | 부동산 장바구니 담기 | `data/iros_realties.json` |
| `iros realty-download` | 부동산 결제 후 열람·저장 | 없음 (결제 완료 후) |
| `iros bizno` | 사업자번호 → 법인정보 조회 | `data/고객리스트.xlsx` |
| `iros report` | 다운로드된 PDF → 종합 리포트 엑셀 생성 | `data/bizno_results.json` + PDF |

모든 명령에 `--config PATH`로 설정 파일 경로를 지정할 수 있습니다 (기본: `./config.json`).

## Recommended flow — 법인등기 대량 발급

```bash
# 1. 법인등록번호 목록 준비
# data/iros_corpnums.json 예시: {"110111-1234567": "스마트솔루션", ...}

# 2. 장바구니 담기 (자동)
iros corp-cart --by-corpnum

# 3. [수동] 브라우저에서 iros.go.kr 로그인 후 장바구니 결제
#    법인: 페이지당 10건 제한

# 4. 결제 완료 후 자동 열람·저장
iros corp-download --total 100

# 5. 사업자번호 조회 (선택)
iros bizno

# 6. 종합 리포트 생성
iros report
```

## Manual steps — 에이전트가 사용자에게 위임해야 하는 단계

다음 단계는 자동화가 불가능하며, **반드시 사용자가 직접** 수행해야 합니다:

1. **로그인**: iros.go.kr 공동인증서/간편인증 로그인 (스크립트가 브라우저를 열면 직접 로그인)
2. **결제**: 장바구니 담기 완료 후 브라우저에서 직접 결제 (법인: 페이지당 10건 / 부동산: 10만원 미만 일괄)
3. **TouchEn nxKey 설치**: 보안 프로그램 미설치 시 안내 페이지에서 수동 설치 후 PC 재시작

## MCP alternative

`iros-mcp`는 동일한 기능을 MCP 서버로 제공합니다. Claude Code MCP 설정에서:

```bash
pip install "iros-registry-automation[mcp]"
iros-mcp   # stdio MCP server
```

Claude Code `settings.json`에 추가:
```json
{
  "mcpServers": {
    "iros": {
      "command": "iros-mcp",
      "args": []
    }
  }
}
```

MCP tools: `corp_cart`, `corp_download`, `realty_cart`, `realty_download`, `bizno_lookup`, `generate_report`
