#!/usr/bin/env python3
"""인터넷등기소 자동화 마법사 (iros.go.kr)
일반 사용자용 인터랙티브 메뉴로 법인/부동산 등기부등본 자동화를 실행합니다.
Usage: python3 iros_wizard.py
"""
import json
import os
import subprocess
import sys


CHECKLIST = """
========================================================
 인터넷등기소 자동화 마법사 (iros.go.kr)
========================================================

시작 전 확인:
 1. Chrome/Chromium 브라우저 설치됨
 2. TouchEn nxKey 보안 프로그램 사전 설치 권장
    (설치 안 되어 있으면 중간에 설치 페이지가 뜨며, 이 경우
     브라우저 재시작 후 처음부터 다시 실행해야 합니다)
 3. iros.go.kr 회원가입 + 공동인증서/간편인증 수단 준비
 4. 결제는 반드시 수동 (법인: 10만원 미만 일괄 / 부동산: 페이지당 10건)
 5. 로그인은 스크립트 실행 중 브라우저에서 직접 진행 (자동화 불가)

메뉴별 필요 입력 파일 (선택한 메뉴만 준비하면 됩니다):
 [1-A] 법인 장바구니(상호명)      → data/iros_companies.json
        예: ["스마트솔루션", "디지털마케팅"]
 [1-B] 법인 장바구니(법인등록번호) → data/iros_corpnums.json
        예: {"110111-1234567": "스마트솔루션"}
 [2]   법인 열람·저장              → 별도 파일 불필요 (결제된 항목 자동 열람)
 [3]   부동산 장바구니              → data/iros_realties.json
        예: [{"label":"우리집","address":"서초대로 219","unit":"101동 1203호"}]
        (파일이 없으면 1건 직접 입력도 가능합니다)
 [4]   부동산 열람·저장             → 별도 파일 불필요
 [5]   사업자번호 조회(bizno)       → data/고객리스트.xlsx (사업자등록번호 컬럼 포함)
 [6]   종합 리포트 생성             → data/bizno_results.json + 다운로드된 PDF들

계속하시려면 Enter (중단: Ctrl+C)
"""


MENU = """
[1] 법인등기부등본 — 장바구니 담기
    └ 1-A: 상호명 기반 (사명변경 시 실패 가능)
    └ 1-B: 법인등록번호 기반 (정확도 ↑, 기본 권장)
[2] 법인등기부등본 — 결제 후 열람·저장
[3] 부동산등기부등본 — 장바구니 담기
[4] 부동산등기부등본 — 결제 후 열람·저장
[5] 사업자번호 → 법인정보 조회 (bizno 스크래핑)
[6] 다운로드된 법인등기 PDF → 종합 리포트 엑셀 생성
[q] 종료
"""


REALTY_EXAMPLE = """[
  {"label": "우리집", "address": "서초대로 219", "unit": "101동 1203호"},
  {"label": "상가",   "address": "세종대로 110", "unit": "", "building_name": "시청별관"}
]"""


MANUAL_REMINDER = (
    "\n[안내] 브라우저가 열리면 iros.go.kr에 수동 로그인 후 Enter를 누르세요.\n"
    "      결제는 수동 진행 (법인: 10만원 미만 일괄 / 부동산: 페이지당 10건).\n"
)


def root_dir():
    return os.path.dirname(os.path.abspath(__file__))


def load_config(cfg_path):
    if not os.path.exists(cfg_path):
        print(f"[오류] 설정 파일이 없습니다: {cfg_path}")
        print(f"       config.json.example을 복사해서 config.json을 먼저 만들어주세요.")
        return None
    with open(cfg_path) as f:
        return json.load(f)


def ensure_input_file(path, kind):
    """입력 파일이 있는지 확인. 없으면 안내."""
    if os.path.exists(path):
        return True
    print(f"\n[안내] 입력 파일이 없습니다: {path}")
    if kind == "companies":
        print("  상호명 목록(JSON 배열) 예시:")
        print('    ["스마트솔루션", "디지털마케팅"]')
    elif kind == "corpnums":
        print("  법인등록번호 목록(JSON 객체) 예시:")
        print('    {"110111-1234567": "스마트솔루션"}')
    elif kind == "realty":
        print("  부동산 목록(JSON 배열) 예시:")
        print(REALTY_EXAMPLE)
        return prompt_realty_input(path)
    print(f"  위 형식으로 {path}를 만든 뒤 다시 선택해주세요.")
    return False


def prompt_realty_input(path):
    """부동산 입력 파일이 없을 때 대화식으로 1건 입력 옵션 제공."""
    ans = input("\n지금 1건 입력해서 파일을 생성할까요? (y/N) ").strip().lower()
    if ans != "y":
        return False
    print("\n— 부동산 1건 입력 —")
    address = input("주소 (지번 또는 도로명): ").strip()
    if not address:
        print("  주소가 비어있어 취소합니다.")
        return False
    unit = input("동/호수 (집합건물이면 필수, 토지/단독건물이면 Enter): ").strip()
    building = input("건물명 (선택): ").strip()
    label = input("식별 라벨 (파일명용): ").strip() or "입력1"
    entry = {
        "label": label,
        "address": address,
        "unit": unit,
        "building_name": building,
    }
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([entry], f, ensure_ascii=False, indent=2)
    print(f"\n저장 완료: {path}")
    return True


def run_script(script_name, extra_args=None):
    """프로젝트 루트의 파이썬 스크립트를 subprocess로 실행."""
    script_path = os.path.join(root_dir(), script_name)
    if not os.path.exists(script_path):
        print(f"[오류] 스크립트가 없습니다: {script_path}")
        return False
    cmd = [sys.executable, script_path]
    if extra_args:
        cmd.extend(extra_args)
    print(f"\n실행: {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd, cwd=root_dir())
        return True
    except KeyboardInterrupt:
        print("\n[중단됨]")
        return False


def cart_by_company(cfg, cfg_path):
    companies_path = cfg.get('companies_list', './data/iros_companies.json')
    if not ensure_input_file(companies_path, "companies"):
        return
    print(MANUAL_REMINDER)
    input("Enter로 시작 (Ctrl+C 취소)")
    run_script("iros_cart.py", [cfg_path])


def cart_by_corpnum(cfg, cfg_path):
    corpnum_path = cfg.get('corpnum_list', './data/iros_corpnums.json')
    if not ensure_input_file(corpnum_path, "corpnums"):
        return
    print(MANUAL_REMINDER)
    input("Enter로 시작 (Ctrl+C 취소)")
    run_script("iros_cart_by_corpnum.py", [cfg_path])


def download_corp(cfg_path):
    print(MANUAL_REMINDER)
    total = input("받을 건수 (기본 999): ").strip() or "999"
    input("Enter로 시작 (Ctrl+C 취소)")
    run_script("iros_download.py", [cfg_path, total])


def cart_realty(cfg, cfg_path):
    realty_path = cfg.get('realty_list', './data/iros_realties.json')
    if not ensure_input_file(realty_path, "realty"):
        return
    print(MANUAL_REMINDER)
    print("[안내] '검색결과가 많아...' 팝업이 뜨면 자동으로 skip 처리됩니다.")
    print("      이 경우 동/호수/건물명을 추가해 입력을 구체화한 뒤 재실행하세요.\n")
    input("Enter로 시작 (Ctrl+C 취소)")
    run_script("iros_cart_realty.py", [cfg_path])


def download_realty(cfg_path):
    print(MANUAL_REMINDER)
    max_batches = input("최대 배치 수 (기본 99, 페이지당 10건 일괄): ").strip() or "99"
    input("Enter로 시작 (Ctrl+C 취소)")
    run_script("iros_download_realty.py", [cfg_path, max_batches])


def run_bizno(cfg_path):
    run_script("bizno_scrape.py", [cfg_path])


def run_report(cfg_path):
    run_script("corp_info_report.py", [cfg_path])


def main():
    print(CHECKLIST)
    try:
        input(">>> ")
    except KeyboardInterrupt:
        print("\n중단됨")
        return

    cfg_path = os.path.join(root_dir(), "config.json")
    if not os.path.exists(cfg_path):
        cfg_path = "config.json"
    cfg = load_config(cfg_path)
    if cfg is None:
        return

    while True:
        print(MENU)
        choice = input("선택 > ").strip().lower()
        if choice in ("q", "quit", "exit"):
            print("종료합니다.")
            break
        elif choice == "1":
            sub = input("  1-A(상호명) / 1-B(법인등록번호, 기본 권장) [A/B] (기본 B): ").strip().lower()
            if sub == "a":
                cart_by_company(cfg, cfg_path)
            else:
                cart_by_corpnum(cfg, cfg_path)
        elif choice == "2":
            download_corp(cfg_path)
        elif choice == "3":
            cart_realty(cfg, cfg_path)
        elif choice == "4":
            download_realty(cfg_path)
        elif choice == "5":
            run_bizno(cfg_path)
        elif choice == "6":
            run_report(cfg_path)
        else:
            print("  [!] 알 수 없는 선택입니다. 메뉴 번호를 다시 입력해주세요.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단됨")
