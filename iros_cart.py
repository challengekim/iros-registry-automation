#!/usr/bin/env python3
"""인터넷등기소 장바구니 자동화
회사명 목록을 읽어 IROS에서 법인등기부등본(말소사항포함)을 장바구니에 자동으로 담습니다.
Usage: python3 iros_cart.py [config.json] [시작인덱스]
"""
import json, os, sys, time, re
from datetime import datetime
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# 설정 로드
# ---------------------------------------------------------------------------

def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)

def load_log(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {"completed": [], "failed": [], "skipped": []}

def save_log(log, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def save_skip_fail(log, log_path, name, reason, bizno_results=None):
    """실패/스킵 기록 + bizno 상태 첨부"""
    entry = {"name": name, "reason": reason, "time": datetime.now().isoformat()}
    if bizno_results:
        for r in bizno_results:
            if r.get('company_name', '') == name or name in r.get('company_name', ''):
                entry['biz_status'] = r.get('biz_status', '')
                entry['pin'] = r.get('formatted_pin', r.get('pin', ''))
                break
    if reason == "skip":
        log["skipped"].append(entry)
    else:
        log["failed"].append(entry)
    save_log(log, log_path)

# ---------------------------------------------------------------------------
# Playwright 헬퍼
# ---------------------------------------------------------------------------

def dismiss(page):
    """모달/팝업 숨기기"""
    try:
        page.evaluate("""() => {
            document.querySelectorAll('#_modal, .w2modal_popup, .ui-dialog').forEach(m => {
                m.style.display = 'none';
                m.style.pointerEvents = 'none';
            });
        }""")
    except:
        pass

def wait_ready(page, timeout=10000):
    """페이지 로딩 대기"""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        pass

def select_valid(page, selector, timeout=5000):
    """선택자로 요소를 찾아 클릭, 없으면 None 반환"""
    try:
        el = page.wait_for_selector(selector, timeout=timeout)
        if el:
            el.click()
            return True
    except:
        pass
    return False

def click_ok_button(page):
    """확인/OK 버튼 클릭 시도"""
    for sel in [
        'input[value="확인"]',
        'button:has-text("확인")',
        'a:has-text("확인")',
        '.btn_confirm',
    ]:
        try:
            page.click(sel, timeout=2000)
            return True
        except:
            continue
    return False

# ---------------------------------------------------------------------------
# 핵심 처리 함수
# ---------------------------------------------------------------------------

def search_company(page, name):
    """회사명 검색"""
    # 검색창 클리어 후 입력
    for sel in ['input[id*="inp_sText"]', 'input[name*="sText"]', '#inp_sText']:
        try:
            page.fill(sel, '', timeout=3000)
            page.fill(sel, name, timeout=3000)
            page.keyboard.press('Enter')
            page.wait_for_timeout(2500)
            return True
        except:
            continue

    # WebSquare API 시도
    try:
        page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input[type="text"]');
            for (const inp of inputs) {{
                if (inp.id && inp.id.includes('sText')) {{
                    inp.value = '{name}';
                    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    break;
                }}
            }}
        }}""")
        page.keyboard.press('Enter')
        page.wait_for_timeout(2500)
        return True
    except:
        pass
    return False

def get_search_results(page):
    """검색 결과 행 수 반환"""
    try:
        result = page.evaluate("""() => {
            const rows = document.querySelectorAll('tr[id*="gridRow"], .w2grid_row, tr.datarow');
            return rows.length;
        }""")
        return result or 0
    except:
        return 0

def select_corp_type(page):
    """법인 유형 선택 (법인등기부등본 말소사항포함)"""
    # 등기부 유형 선택 시도
    for sel in [
        'input[id*="rdo_0"][value*="법인"]',
        'label:has-text("법인")',
        'input[id*="reg_type_2"]',
    ]:
        try:
            page.click(sel, timeout=2000)
            page.wait_for_timeout(500)
            break
        except:
            continue

    # 말소사항 포함 선택
    for sel in [
        'input[id*="malso"][value*="포함"]',
        'label:has-text("말소사항포함")',
        'input[id*="chk_malso"]',
    ]:
        try:
            page.click(sel, timeout=2000)
            page.wait_for_timeout(500)
            break
        except:
            continue

def add_to_cart(page):
    """장바구니 담기 버튼 클릭"""
    for sel in [
        'input[id*="btn_cart"]',
        'button:has-text("장바구니")',
        'a:has-text("장바구니")',
        'input[value*="장바구니"]',
    ]:
        try:
            page.click(sel, timeout=3000)
            page.wait_for_timeout(1500)
            return True
        except:
            continue
    return False

def process(page, name, log, log_path, bizno_results=None):
    """회사 한 건 처리: 검색 -> 선택 -> 장바구니"""
    dismiss(page)

    # 검색
    if not search_company(page, name):
        print(f"  [{name}] 검색창 접근 실패 - skip")
        save_skip_fail(log, log_path, name, "search_fail", bizno_results)
        return "fail"

    page.wait_for_timeout(2000)
    row_count = get_search_results(page)

    if row_count == 0:
        print(f"  [{name}] 검색 결과 없음 - skip")
        save_skip_fail(log, log_path, name, "skip", bizno_results)
        return "skip"

    # 첫 번째 검색 결과 클릭
    try:
        page.evaluate("""() => {
            const rows = document.querySelectorAll('tr[id*="gridRow"], .w2grid_row, tr.datarow');
            if (rows.length > 0) rows[0].click();
        }""")
        page.wait_for_timeout(1000)
    except:
        pass

    # 법인 유형 선택
    select_corp_type(page)
    page.wait_for_timeout(500)

    # 장바구니 담기
    if not add_to_cart(page):
        print(f"  [{name}] 장바구니 버튼 없음 - fail")
        save_skip_fail(log, log_path, name, "cart_fail", bizno_results)
        return "fail"

    # 확인 팝업 처리
    page.wait_for_timeout(1000)
    click_ok_button(page)
    page.wait_for_timeout(500)
    dismiss(page)

    print(f"  [{name}] 장바구니 담기 완료")
    log["completed"].append({
        "name": name,
        "time": datetime.now().isoformat()
    })
    return "ok"

# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    # 인자 파싱
    cfg_path = "config.json"
    start_idx = 0
    for arg in sys.argv[1:]:
        if arg.isdigit():
            start_idx = int(arg)
        else:
            cfg_path = arg

    cfg = load_config(cfg_path)
    companies_path = cfg.get('companies_list', './data/iros_companies.json')
    log_path = cfg.get('cart_log', './logs/cart_log.json')

    # bizno 결과 로드 (스킵 이유 기록용)
    bizno_results = []
    bizno_path = cfg.get('bizno_results', './data/bizno_results.json')
    if os.path.exists(bizno_path):
        with open(bizno_path) as f:
            bizno_results = json.load(f)

    with open(companies_path) as f:
        companies = json.load(f)

    log = load_log(log_path)
    completed_names = set(c['name'] for c in log.get('completed', []))
    skipped_names = set(c['name'] for c in log.get('skipped', []))

    pending = [c for c in companies[start_idx:] if c not in completed_names]
    total = len(pending)
    print(f"대상: {total}건 (전체: {len(companies)}, 시작: {start_idx})")
    print(f"이미완료: {len(completed_names)}건, 스킵: {len(skipped_names)}건")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=100,
            args=["--window-size=1400,900"]
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="ko-KR"
        )
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())

        page.goto("https://www.iros.go.kr/index.jsp", wait_until="domcontentloaded", timeout=30000)

        print("\n" + "=" * 50)
        print("  iros.go.kr 로그인 후 Enter")
        print("=" * 50)
        input(">>> ")

        # 부동산 등기 열람/발급 메뉴 이동
        print("등기 검색 페이지 이동 중...")
        try:
            page.evaluate("""() => {
                const links = document.querySelectorAll('a');
                for (const a of links) {
                    if (a.textContent.includes('열람') || a.textContent.includes('부동산')) {
                        a.click(); break;
                    }
                }
            }""")
        except:
            pass
        page.wait_for_timeout(3000)
        dismiss(page)

        ok, fail, skip = 0, 0, 0

        for i, name in enumerate(pending):
            print(f"[{i+1}/{total}] {name}", end=" ... ", flush=True)

            result = process(page, name, log, log_path, bizno_results)

            if result == "ok":
                ok += 1
            elif result == "skip":
                skip += 1
            else:
                fail += 1

            # 10건마다 저장
            if (i + 1) % 10 == 0:
                save_log(log, log_path)
                print(f"  --- 진행: {i+1}/{total} (성공:{ok} 실패:{fail} 스킵:{skip}) ---")

            page.wait_for_timeout(1000)

        save_log(log, log_path)

        print(f"\n{'='*50}")
        print(f"  완료! 성공:{ok} 실패:{fail} 스킵:{skip}")
        print(f"{'='*50}")

        # 결제대상목록으로 이동
        print("결제대상목록 페이지로 이동 중...")
        try:
            page.evaluate("""() => {
                const links = document.querySelectorAll('a');
                for (const a of links) {
                    if (a.textContent.includes('결제') || a.textContent.includes('장바구니')) {
                        a.click(); break;
                    }
                }
            }""")
            page.wait_for_timeout(3000)
        except:
            pass

        input(">>> Enter로 브라우저 닫기 ")
        browser.close()

if __name__ == "__main__":
    main()
