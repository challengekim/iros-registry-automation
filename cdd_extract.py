#!/usr/bin/env python3
"""
등기부등본 PDF 추출 파이프라인
config.json 경로 기반으로 PDF를 파싱하여 회사명, 주소, 임원, 사업목적,
등록번호, 설립일, 주식 정보를 추출합니다.

Usage:
    python3 cdd_extract.py [config.json]
"""

import subprocess
import re
import os
import sys
import json
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


# ─── Step 1: PDF 텍스트 추출 ─────────────────────────────────────

def extract_text(pdf_path: str) -> str:
    """pdftotext -layout 을 사용하여 PDF 텍스트 추출."""
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")

    text = result.stdout
    # 열람일시 푸터 제거
    text = re.sub(r'열람일시\s*:.*?\d+/\d+', '', text)
    # 중복 페이지 헤더 제거 (등기번호 N)
    lines = text.split('\n')
    cleaned = []
    seen_first_header = False
    for line in lines:
        if re.match(r'^\s*등기번호\s+\d+\s*$', line):
            if not seen_first_header:
                seen_first_header = True
                cleaned.append(line)
        else:
            cleaned.append(line)
    return '\n'.join(cleaned)


# ─── Step 2: 필드 파싱 ──────────────────────────────────────────

def parse_company_name(text: str) -> tuple:
    """상호(한글/영문) 추출."""
    m = re.search(r'상\s*호\s+(.+)', text)
    if not m:
        m = re.search(r'명\s*칭\s+(.+)', text)
    if not m:
        return ("", "")

    section_match = re.search(
        r'(?:상\s*호|명\s*칭)\s+(.*?)(?=본\s+점|주사무소)',
        text, re.DOTALL
    )
    if not section_match:
        line = m.group(1).strip()
        kor = re.sub(r'\s*\(.*?\)\s*$', '', line).strip()
        eng_m = re.search(r'\((.+?)\)', line)
        eng = eng_m.group(1) if eng_m else ""
        return (kor, eng)

    section = section_match.group(1)
    name_lines = []
    for line in section.split('\n'):
        line = line.strip()
        if not line or line == '. .' or re.match(r'^\d{4}\.\d{2}\.\d{2}', line):
            continue
        if re.match(r'^[\d\.\s]*(변경|등기|경정)\s*$', line):
            continue
        if line:
            name_lines.append(line)

    if not name_lines:
        return ("", "")

    current = name_lines[0]
    kor = re.sub(r'\s*\(.*?\)\s*$', '', current).strip()
    eng_m = re.search(r'\((.+?)\)', current)
    eng = eng_m.group(1) if eng_m else ""
    return (kor, eng)


def parse_address(text: str) -> str:
    """본점 섹션에서 현재 주소 추출 (마지막 주소 = 현재)."""
    section_match = re.search(
        r'(?:본\s+점|주사무소)\s+(.*?)(?=공고방법|1주의\s*금액|발행할\s*주식|출자\s*1좌|목\s+적)',
        text, re.DOTALL
    )
    if not section_match:
        return ""

    section = section_match.group(1)
    addresses = []
    current_addr = ""

    for line in section.split('\n'):
        stripped = line.strip()
        if not stripped or re.match(r'^\.[\s.]*\.?$', stripped):
            continue
        if re.match(r'^\d{4}\.\d{2}\.\d{2}\s+(변경|등기|도로명|경정)', stripped):
            continue
        if stripped in ('명주소', '도로명주소') or re.match(r'^(명주소|도로명)', stripped):
            continue

        is_addr_start = re.match(
            r'^(서울|경기|인천|부산|대구|대전|광주|울산|세종|강원|충청|충남|충북|전라|전남|전북|경상|경남|경북|제주)',
            stripped
        )

        if is_addr_start:
            if current_addr:
                addresses.append(current_addr)
            current_addr = stripped
        elif current_addr and re.search(r'[가-힣\)a-zA-Z]', stripped) and not re.match(r'^\d{4}', stripped):
            if re.match(r'^[\.\s]+$', stripped) or '변경' in stripped or '등기' in stripped:
                continue
            current_addr += " " + stripped

    if current_addr:
        addresses.append(current_addr)

    if not addresses:
        return ""

    return re.sub(r'\s+', ' ', addresses[-1]).strip()


def parse_representatives(text: str) -> list:
    """임원에 관한 사항에서 현재 대표자 목록 추출."""
    section_match = re.search(
        r'임원에\s*관한\s*사항\s*\n(.*?)(?=회사성립연월일|종류주식의\s*내용|지점에\s*관한|$)',
        text, re.DOTALL
    )
    if not section_match:
        return []

    section = section_match.group(1)

    officer_pattern = re.compile(
        r'((?:공동)?대표이사|각자대표이사|사내이사|기타비상무이사|사외이사|이사|감사|업무집행자)\s+'
        r'(?:([\w가-힣]+국인|[\w가-힣]+국적)\s+)?'
        r'([\w가-힣]{1,10})\s+'
        r'(\d{6})-\*{7}'
    )
    officer_pattern2 = re.compile(
        r'((?:공동)?대표이사|각자대표이사|사내이사|기타비상무이사|사외이사|이사|감사|업무집행자)\s+'
        r'([\w가-힣]{1,10})\s+'
        r'(\d{6})-\*{7}'
    )
    officer_foreign = re.compile(
        r'((?:공동)?대표이사|각자대표이사|사내이사|기타비상무이사|사외이사|이사|감사|업무집행자)\s+'
        r'([\w가-힣]+국인|[\w가-힣]+국적|[\w가-힣]+인)\s+'
        r'([\w가-힣a-zA-Z]{1,20})\s+'
        r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일생'
    )
    event_pattern = re.compile(
        r'(\d{4})\s*년\s+(\d{1,2})\s*월\s+(\d{1,2})\s*일\s+'
        r'(취임|사임|퇴임|중임|임기만료|해임|주소변경|사임\s*및|퇴임\s*및)'
    )

    persons = {}
    lines = section.split('\n')
    current_person_key = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        m = officer_pattern.search(stripped)
        if m:
            role = m.group(1)
            nationality_prefix = m.group(2) or ""
            name = m.group(3)
            dob = m.group(4)
            nationality = "한국"
            if nationality_prefix:
                nat_m = re.match(r'([\w가-힣]+?)(국인|국적)', nationality_prefix)
                if nat_m:
                    nationality = nat_m.group(1)
            key = (name, dob)
            if key not in persons:
                persons[key] = {"roles": set(), "events": [], "nationality": nationality}
            persons[key]["roles"].add(role)
            current_person_key = key
            continue

        m2 = officer_pattern2.search(stripped)
        if m2:
            role = m2.group(1)
            name = m2.group(2)
            dob = m2.group(3)
            nationality = "한국"
            nat_check = re.search(r'([\w가-힣]+?)(국인|국적)', stripped)
            if nat_check and nat_check.start() < stripped.index(name):
                nationality = nat_check.group(1)
            if re.search(r'[a-zA-Z]', name):
                nationality = "외국"
            key = (name, dob)
            if key not in persons:
                persons[key] = {"roles": set(), "events": [], "nationality": nationality}
            persons[key]["roles"].add(role)
            current_person_key = key
            continue

        m3 = officer_foreign.search(stripped)
        if m3:
            role = m3.group(1)
            nat_prefix = m3.group(2)
            name = m3.group(3)
            year, month, day = m3.group(4), m3.group(5).zfill(2), m3.group(6).zfill(2)
            dob = f"{year[2:]}{month}{day}"
            nationality = re.sub(r'(국인|국적|인)$', '', nat_prefix)
            key = (name, dob)
            if key not in persons:
                persons[key] = {"roles": set(), "events": [], "nationality": nationality}
            persons[key]["roles"].add(role)
            current_person_key = key
            continue

        for em in event_pattern.finditer(stripped):
            year, month, day, event = em.groups()
            event_date = f"{year}{month}{day}"
            if current_person_key and current_person_key in persons:
                persons[current_person_key]["events"].append((event_date, event))

    active_officers = []
    for (name, dob), info in persons.items():
        events = sorted(info["events"], key=lambda x: x[0])
        status_events = [(d, e) for d, e in events if e in ('취임', '사임', '퇴임', '중임', '임기만료', '해임')]
        is_active = True
        if status_events:
            last_event = status_events[-1][1]
            if last_event in ('사임', '퇴임', '임기만료', '해임'):
                is_active = False

        if is_active:
            role_priority = ['대표이사', '공동대표이사', '각자대표이사', '사내이사', '이사', '업무집행자', '기타비상무이사', '사외이사', '감사']
            best_role = "기타"
            for rp in role_priority:
                if rp in info["roles"]:
                    best_role = rp
                    break
            active_officers.append({
                "name": name,
                "dob": dob,
                "nationality": info["nationality"],
                "role": best_role,
                "roles": list(info["roles"])
            })

    role_order = {'대표이사': 0, '공동대표이사': 1, '각자대표이사': 2, '사내이사': 3, '이사': 4, '업무집행자': 5}
    active_officers.sort(key=lambda x: role_order.get(x["role"], 99))

    reps = [o for o in active_officers if o["role"] in ('대표이사', '공동대표이사', '각자대표이사')]
    if not reps:
        reps = [o for o in active_officers if o["role"] == '사내이사'][:1]
    if not reps:
        reps = [o for o in active_officers if o["role"] != '감사'][:1]

    return reps


def parse_business_purposes(text: str) -> str:
    """목적 섹션에서 사업목적 추출."""
    section_match = re.search(
        r'목\s+적\s*\n(.*?)(?=임원에\s*관한\s*사항)',
        text, re.DOTALL
    )
    if not section_match:
        return ""

    section = section_match.group(1)
    purposes = []
    current_item = ""

    for line in section.split('\n'):
        stripped = line.strip()
        if not stripped or stripped == '. .':
            continue
        if re.match(r'^<?\d{4}\.\d{2}\.\d{2}', stripped):
            if '삭제' in stripped and current_item:
                current_item = ""
            continue
        if re.match(r'^1\s*[.\s]', stripped):
            if current_item:
                purposes.append(current_item)
            current_item = re.sub(r'^1\s*[.\s]\s*', '', stripped).strip()
        elif current_item:
            current_item += " " + stripped

    if current_item:
        purposes.append(current_item)

    seen = set()
    unique = []
    for p in purposes:
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            seen.add(p_clean)
            unique.append(p_clean)

    return ", ".join(unique)


def parse_registration_number(text: str) -> str:
    """등록번호 추출."""
    m = re.search(r'등록번호\s+(\d+-\d+)', text)
    return m.group(1) if m else ""


def parse_establishment_date(text: str) -> str:
    """회사성립연월일 추출."""
    m = re.search(r'회사성립연월일\s+(\d{4})\s*년\s+(\d{2})\s*월\s+(\d{2})\s*일', text)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}"
    return ""


# ─── Step 3: 주식 파싱 ──────────────────────────────────────────

def parse_authorized_shares(text: str) -> dict:
    """발행할 주식의 총수 섹션 파싱.

    등기부등본에 이력이 연대순으로 기재됩니다 (가장 오래된 것 먼저).
    말소(취소선)는 pdftotext로 감지 불가하므로, 마지막 항목 = 현재(후),
    직전 항목 = 이전(전)으로 처리합니다.

    Returns:
        {
            "전": {"총수": "100,000", "date": "2017.08.24"},
            "후": {"총수": "10,000,000", "date": "2023.06.30"}
        }
        항목이 1개뿐이면 전은 빈 dict.
    """
    # 섹션: "발행할 주식의 총수" 헤더 줄 ~ "발행주식의 총수와" 또는 "1주의 금액" 전까지
    # pdftotext -layout 출력에서 첫 값이 헤더와 같은 줄에 나옴:
    #   발행할 주식의 총수        100 주
    #                      1,000,000 주
    section_match = re.search(
        r'(발행할\s*주식의\s*총수\s+[\d,]+\s*주.*?)(?=발행주식의\s*총수와|1주의\s*금액|목\s+적)',
        text, re.DOTALL
    )
    if not section_match:
        return {"전": {}, "후": {}}

    section = section_match.group(1)

    # 주식수를 포함하는 모든 줄에서 값 추출 (같은 줄에 날짜가 있을 수 있음)
    entries = []
    share_re = re.compile(r'([\d,]+)\s*주')
    date_re = re.compile(r'(\d{4}\.\d{2}\.\d{2})\s*(?:변경|등기|경정)?')

    lines = section.split('\n')
    for i, line in enumerate(lines):
        sm = share_re.search(line)
        if not sm:
            continue
        # "발행가능한 주식수" 등 본문 텍스트 제외 — 한글이 많은 줄은 데이터가 아님
        hangul_count = len(re.findall(r'[가-힣]', line))
        if hangul_count > 15:
            continue
        share_val = sm.group(1)
        # 같은 줄 또는 다음 몇 줄에서 날짜 찾기
        date_val = ""
        dm = date_re.search(line)
        if dm:
            date_val = dm.group(1)
        else:
            for j in range(i + 1, min(i + 5, len(lines))):
                dm2 = date_re.search(lines[j])
                if dm2:
                    date_val = dm2.group(1)
                    break
        entries.append({"총수": share_val, "date": date_val})

    if not entries:
        return {"전": {}, "후": {}}

    if len(entries) == 1:
        return {"전": {}, "후": entries[0]}

    return {"전": entries[-2], "후": entries[-1]}


def parse_issued_shares(text: str) -> dict:
    """발행주식의 총수와 그 종류 및 각각의 수 섹션 파싱.

    블록들이 연대순으로 기재됩니다. 마지막 블록 = 현재(후).

    각 블록 구조 예:
        발행주식의 총수  1,034,953 주
        보통주식         720,133 주
        전환상환우선주식  138,820 주
        자본금의 액      금 5,174,765,000 원
        YYYY.MM.DD 변경등기

    Returns:
        {
            "전": {
                "발행주식의 총수": "1,033,953 주",
                "보통주식": "719,133 주",
                ...
                "자본금": "금 5,169,765,000 원",
                "date": "2025.12.16"
            },
            "후": { ... }
        }
    """
    # 섹션 경계: "발행주식의 총수와" 헤더 ~ "목 적" 전까지
    # pdftotext에서 "그 종류 및 각각의 수"가 다음 줄에 나올 수 있음
    section_match = re.search(
        r'발행주식의\s*총수와\s*(.*?)(?=\n\s*목\s+적)',
        text, re.DOTALL
    )
    if not section_match:
        return {"전": {}, "후": {}}

    section = section_match.group(1)

    # 블록 분리: "발행주식의 총수  N 주" 가 블록 시작
    # 각 블록을 수집
    block_start_re = re.compile(r'발행주식의\s*총수\s+([\d,]+)\s*주')
    blocks_raw = re.split(r'(?=발행주식의\s*총수\s+[\d,]+\s*주)', section)

    parsed_blocks = []
    for block in blocks_raw:
        bm = block_start_re.search(block)
        if not bm:
            continue

        entry = {}
        entry["발행주식의 총수"] = bm.group(1) + " 주"

        # 주식 종류 파싱
        stock_type_re = re.compile(
            r'(보통주식|전환상환우선주식|전환우선주식|우선주식|상환전환우선주식|상환우선주식|'
            r'전환사채|신주인수권부사채|[가-힣]+주식)\s+([\d,]+)\s*주'
        )
        for stm in stock_type_re.finditer(block):
            entry[stm.group(1)] = stm.group(2) + " 주"

        # 자본금의 액: "자본금의 액" 헤더는 별도 줄이고, "금 N 원"은 데이터 줄에 있음
        # pdftotext에서 "금 10,000,000 원"이 주식 종류와 같은 줄에 나옴
        capital_re = re.compile(r'금\s*([\d,]+)\s*원')
        capital_matches = capital_re.findall(block)
        if capital_matches:
            # 마지막 자본금 값 사용 (블록 내 가장 아래 것이 최종)
            entry["자본금"] = f"금 {capital_matches[-1]} 원"

        # 날짜
        date_re = re.compile(r'(\d{4}\.\d{2}\.\d{2})\s*(?:변경|등기|경정)?')
        dates = date_re.findall(block)
        if dates:
            entry["date"] = dates[-1]
        else:
            entry["date"] = ""

        if entry:
            parsed_blocks.append(entry)

    if not parsed_blocks:
        return {"전": {}, "후": {}}

    if len(parsed_blocks) == 1:
        return {"전": {}, "후": parsed_blocks[0]}

    return {"전": parsed_blocks[-2], "후": parsed_blocks[-1]}


# ─── Step 4: 단일 PDF 파싱 ──────────────────────────────────────

def parse_one_pdf(pdf_path: str) -> dict:
    """PDF 1건 파싱 → 구조화된 CDD 데이터 반환."""
    text = extract_text(pdf_path)

    company_kor, company_eng = parse_company_name(text)
    address = parse_address(text)
    reps = parse_representatives(text)
    purposes = parse_business_purposes(text)
    reg_number = parse_registration_number(text)
    est_date = parse_establishment_date(text)
    authorized = parse_authorized_shares(text)
    issued = parse_issued_shares(text)

    rep_names = ", ".join(r["name"] for r in reps) if reps else ""
    rep_dobs = ", ".join(r["dob"] for r in reps) if reps else ""
    rep_nationalities = ", ".join(r["nationality"] for r in reps) if reps else ""
    rep_roles = ", ".join(r["role"] for r in reps) if reps else ""

    def fmt_issued(block: dict) -> str:
        """발행주식 블록을 읽기 쉬운 문자열로 변환."""
        if not block:
            return ""
        lines = []
        for k, v in block.items():
            if k == "date":
                continue
            lines.append(f"{k}: {v}")
        if block.get("date"):
            lines.append(f"변경일: {block['date']}")
        return " / ".join(lines)

    return {
        "filename": os.path.basename(pdf_path),
        "company_kor": company_kor,
        "company_eng": company_eng,
        "reg_number": reg_number,
        "address": address,
        "rep_names": rep_names,
        "rep_dobs": rep_dobs,
        "rep_nationalities": rep_nationalities,
        "rep_roles": rep_roles,
        "business_purposes": purposes,
        "establishment_date": est_date,
        # 발행할 주식의 총수 (전/후)
        "authorized_shares_before": authorized["전"].get("총수", ""),
        "authorized_shares_after": authorized["후"].get("총수", ""),
        # 발행주식 상세 (전/후)
        "issued_shares_before": fmt_issued(issued["전"]),
        "issued_shares_after": fmt_issued(issued["후"]),
        # 자본금 (전/후)
        "capital_before": issued["전"].get("자본금", ""),
        "capital_after": issued["후"].get("자본금", ""),
    }


# ─── Step 5: 배치 실행 ──────────────────────────────────────────

def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
    cfg = load_config(cfg_path)

    pdf_dir = os.path.expanduser(cfg.get('pdf_dir', cfg.get('save_dir', '~/Downloads/등기부등본')))
    output_path = cfg.get('extract_output', cfg.get('cdd_output', './output/cdd_extract_results.json'))
    errors_path = os.path.splitext(output_path)[0] + '_errors.json'

    print(f"=== 등기부등본 PDF 추출 ===")
    print(f"PDF 디렉토리: {pdf_dir}")

    if not os.path.exists(pdf_dir):
        print(f"오류: PDF 디렉토리가 없습니다: {pdf_dir}")
        sys.exit(1)

    pdf_files = sorted([
        os.path.join(pdf_dir, f)
        for f in os.listdir(pdf_dir)
        if f.lower().endswith('.pdf')
    ])
    print(f"PDF 파일 수: {len(pdf_files)}")

    # 기존 결과 로드 (이어하기)
    existing = {}
    if os.path.exists(output_path):
        with open(output_path, 'r', encoding='utf-8') as f:
            existing = {r["filename"]: r for r in json.load(f)}
        print(f"기존 결과 로드: {len(existing)}건")

    results = list(existing.values())
    errors = []
    skipped = 0

    for i, pdf_path in enumerate(pdf_files):
        filename = os.path.basename(pdf_path)
        if filename in existing:
            skipped += 1
            continue

        try:
            data = parse_one_pdf(pdf_path)
            results.append(data)
            if (i + 1) % 20 == 0 or i == len(pdf_files) - 1:
                print(f"  [{i+1}/{len(pdf_files)}] 성공: {len(results)}, 실패: {len(errors)}")
        except Exception as e:
            errors.append({
                "filename": filename,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })

    # 결과 저장
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if errors:
        with open(errors_path, 'w', encoding='utf-8') as f:
            json.dump(errors, f, ensure_ascii=False, indent=2)

    print(f"\n=== 결과 ===")
    print(f"성공: {len(results)}건")
    print(f"실패: {len(errors)}건")
    print(f"스킵(기처리): {skipped}건")
    print(f"결과 파일: {output_path}")

    # 샘플 출력
    if results:
        print(f"\n=== 샘플 (처음 3건) ===")
        for r in results[:3]:
            print(f"  {r['company_kor']} | {r['address'][:40]} | "
                  f"자본금(후): {r['capital_after']}")


if __name__ == "__main__":
    main()
