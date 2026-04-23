#!/usr/bin/env python3
"""인터넷등기소 부동산등기부등본 일괄열람출력 자동화
결제 완료된 부동산등기부등본을 페이지 단위로 일괄열람출력합니다.
한 페이지의 모든 항목을 선택 후 일괄열람출력 버튼으로 PDF 1개로 저장.
Usage: python3 iros_download_realty.py [config.json] [max_batches]

주의:
- TouchEn nxKey 보안 프로그램 사전 설치 필수.
- 로그인은 수동. 로그인 후 Enter 입력.
- 일괄 PDF는 건별 파일명 매칭이 불가합니다. 내용으로 식별해주세요.
"""
import json, sys, os, re, time, shutil
from datetime import datetime
from playwright.sync_api import sync_playwright


# ─── 셀렉터 ────────────────────────────────────────────────────

# 부동산 신청결과 확인 (열람·발급) 메뉴 ID
BTN_MENU_REALTY_APPLY_RESULT = (
    'mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_0'
    '_gen_depth3_6_gen_depth4_0_btn_top_menu4'
)


# ─── 유틸 ─────────────────────────────────────────────────────

def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def load_log(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {"completed": [], "failed": [], "skipped": []}


def save_log(log, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def dismiss(page):
    try:
        page.evaluate("""() => {
            document.querySelectorAll('#_modal,.w2modal_popup').forEach(m => {
                m.style.display='none'; m.style.pointerEvents='none';
            });
        }""")
    except Exception:
        pass


def detect_security_install(page):
    try:
        txt = page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:
        return False
    if not txt:
        return False
    return any(kw in txt for kw in ["보안 프로그램 설치", "보안프로그램 설치", "TouchEn", "nxKey"])


def snapshot_files(dl_dir):
    files = set()
    try:
        for f in os.listdir(dl_dir):
            fp = os.path.join(dl_dir, f)
            if os.path.isfile(fp):
                files.add(fp)
    except Exception:
        pass
    return files


def wait_for_new_file(before_files, dl_dir, timeout=30):
    for _ in range(timeout):
        time.sleep(1)
        current = snapshot_files(dl_dir)
        new_files = current - before_files
        for f in new_files:
            if not os.path.basename(f).endswith('.crdownload'):
                return f
    return None


def confirm_popups(page):
    """변환중/저장 등 확인 팝업 처리."""
    for sel in [
        'input[id*="btn_confirm2"][value="확인"]',
        'a[id*="btn_confirm2"]',
        'input[value="확인"]',
        'button:has-text("확인")',
    ]:
        try:
            page.click(sel, timeout=2000)
            return True
        except Exception:
            continue
    return False


# ─── 핵심 헬퍼 함수들 ──────────────────────────────────────────

def select_all_on_page(page) -> bool:
    """헤더 체크박스 클릭(이미 체크되어 있으면 skip). 성공 여부 반환."""
    result = page.evaluate("""() => {
        // 방법 1: thead 안의 첫 번째 checkbox
        const theads = document.querySelectorAll('thead');
        for (const th of theads) {
            const cb = th.querySelector('input[type="checkbox"]');
            if (cb && cb.offsetParent !== null) {
                if (!cb.checked) {
                    cb.click();
                }
                return {found: true, method: 'thead'};
            }
        }
        // 방법 2: "번호" 또는 "결제일시" 텍스트를 포함하는 행의 checkbox
        const rows = document.querySelectorAll('tr');
        for (const row of rows) {
            const txt = row.innerText || '';
            if (txt.includes('번호') || txt.includes('결제일시')) {
                const cb = row.querySelector('input[type="checkbox"]');
                if (cb && cb.offsetParent !== null) {
                    if (!cb.checked) {
                        cb.click();
                    }
                    return {found: true, method: 'header-row'};
                }
            }
        }
        return {found: false, method: 'none'};
    }""")
    return result.get("found", False)


def click_bulk_view(page) -> bool:
    """텍스트='일괄열람출력' 버튼 클릭."""
    result = page.evaluate("""() => {
        // button, input[type=button/submit], a 모두 검색
        const candidates = [
            ...document.querySelectorAll('button'),
            ...document.querySelectorAll('input[type="button"]'),
            ...document.querySelectorAll('input[type="submit"]'),
            ...document.querySelectorAll('a'),
        ];
        for (const el of candidates) {
            const text = (el.textContent || el.value || '').trim();
            if (text === '일괄열람출력' && el.offsetParent !== null) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    return bool(result)


def has_pending_rows(page) -> int:
    """현재 페이지에 미열람 상태 행 개수."""
    count = page.evaluate("""() => {
        let n = 0;
        const rows = document.querySelectorAll('tbody tr');
        for (const row of rows) {
            const txt = row.innerText || '';
            // 미열람 텍스트 포함 또는 행 체크박스가 비활성화되지 않은 경우
            const hasPending = txt.includes('미열람');
            const cb = row.querySelector('input[type="checkbox"]');
            const hasActiveCb = cb && !cb.disabled && cb.offsetParent !== null;
            if (hasPending || hasActiveCb) {
                n++;
            }
        }
        return n;
    }""")
    return int(count or 0)


def go_next_page(page) -> bool:
    """다음 페이지 이동. 다음 페이지 없으면 False."""
    result = page.evaluate("""() => {
        // 방법 1: aria-label="다음"
        const ariaNext = document.querySelector('[aria-label="다음"]');
        if (ariaNext && ariaNext.offsetParent !== null) {
            ariaNext.click();
            return true;
        }
        // 방법 2: id에 pageList_next 포함
        const idNext = document.querySelector('a[id*="pageList_next"]');
        if (idNext && idNext.offsetParent !== null) {
            idNext.click();
            return true;
        }
        // 방법 3: class에 w2pageList_next_btn 포함
        const clsNext = document.querySelector('.w2pageList_next_btn');
        if (clsNext && clsNext.offsetParent !== null) {
            clsNext.click();
            return true;
        }
        // 방법 4: 텍스트가 "다음"인 링크/버튼
        const all = [...document.querySelectorAll('a, button')];
        for (const el of all) {
            if ((el.textContent || '').trim() === '다음' && el.offsetParent !== null) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    return bool(result)


def process_batch(page, dl_dir, save_dir, batch_idx) -> str:
    """한 페이지 분량 일괄 처리. 'ok' | 'empty' | 'no_button' | 'dl_fail' | 'error:<msg>'"""
    dismiss(page)
    page.wait_for_timeout(1000)

    # 1. 미열람 행 확인
    pending = has_pending_rows(page)
    if pending == 0:
        return 'empty'

    print(f"  미열람 {pending}건 감지 - 전체 선택 중...", end=" ", flush=True)

    # 2. 헤더 체크박스로 전체 선택
    if not select_all_on_page(page):
        print("(헤더 체크박스 없음)", end=" ", flush=True)
    else:
        print("(전체선택OK)", end=" ", flush=True)
    page.wait_for_timeout(1000)

    # 3. 일괄열람출력 버튼 클릭
    if not click_bulk_view(page):
        print("일괄열람출력 버튼 없음 X")
        return 'no_button'
    print("(일괄열람출력클릭)", end=" ", flush=True)

    # 4. 확인 팝업 처리 (변환중 / 저장)
    page.wait_for_timeout(3000)
    confirm_popups(page)
    page.wait_for_timeout(2000)
    confirm_popups(page)

    # 5. 다운로드 대기 (30초)
    before_files = snapshot_files(dl_dir)
    dl_file = wait_for_new_file(before_files, dl_dir, timeout=30)
    if not dl_file:
        print("다운로드안됨 X")
        return 'dl_fail'

    # 6. 확장자 보정
    if not dl_file.endswith('.pdf'):
        pdf_file = dl_file + '.pdf'
        os.rename(dl_file, pdf_file)
        dl_file = pdf_file

    # PDF 헤더 검증
    try:
        with open(dl_file, 'rb') as fh:
            header = fh.read(4)
        if header != b'%PDF':
            print("(PDF아님)", end=" ", flush=True)
    except Exception:
        pass

    # 7. 파일명 변경: realty_bulk_{YYYYMMDD_HHMMSS}_{batch_idx}.pdf
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"realty_bulk_{ts}_{batch_idx}.pdf"
    new_path = os.path.join(save_dir, new_name)
    if os.path.exists(new_path):
        new_path = os.path.join(save_dir, f"realty_bulk_{ts}_{batch_idx}_{int(time.time())}.pdf")
    shutil.move(dl_file, new_path)
    print(f"-> {os.path.basename(new_path)} OK")

    return 'ok'


def main():
    cfg_path = "config.json"
    max_batches = 99
    for arg in sys.argv[1:]:
        if arg.isdigit():
            max_batches = int(arg)
        else:
            cfg_path = arg

    cfg = load_config(cfg_path)
    log_path = cfg.get('realty_download_log', './logs/download_realty_log.json')
    dl_dir = cfg.get('download_temp', '/tmp/iros_pdf_downloads')
    save_dir = os.path.expanduser(
        cfg.get('realty_save_dir', '~/Downloads/부동산등기부등본')
    )

    log = load_log(log_path)

    os.makedirs(dl_dir, exist_ok=True)
    os.makedirs(save_dir, exist_ok=True)
    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)

    print(f"최대 배치: {max_batches}, 이미완료: {len(log['completed'])}배치")
    print(f"저장: {save_dir}")
    print("\n[사전 확인] TouchEn nxKey 보안 프로그램 설치 필수.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=50,
            args=["--window-size=1400,900"],
            downloads_path=dl_dir,
        )
        ctx = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="ko-KR",
            accept_downloads=True,
        )
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())

        page.goto("https://www.iros.go.kr/index.jsp", wait_until="domcontentloaded", timeout=30000)

        print("=" * 50)
        print("  iros.go.kr 로그인 후 Enter")
        print("=" * 50)
        input(">>> ")

        # 부동산 신청결과 확인 페이지 이동
        print("신청결과(부동산) 확인 페이지 이동...")
        try:
            page.evaluate(f"""() => {{
                const el = document.getElementById('{BTN_MENU_REALTY_APPLY_RESULT}');
                if (el) el.click();
            }}""")
        except Exception:
            pass
        page.wait_for_timeout(4000)
        dismiss(page)

        if detect_security_install(page):
            print("\n[중단] TouchEn nxKey 보안 프로그램 설치 페이지 감지")
            print("  TouchEn nxKey 설치 후 브라우저 재시작 → 스크립트 재실행 필요")
            input(">>> Enter로 브라우저 닫기 ")
            browser.close()
            return

        batch_idx = 0
        consecutive_fails = 0

        while batch_idx < max_batches:
            print(f"\n[배치 {batch_idx + 1}] ", end="", flush=True)

            try:
                status = process_batch(page, dl_dir, save_dir, batch_idx)
            except Exception as e:
                status = f"error:{str(e)[:80]}"

            if status == 'empty':
                print("미열람 없음 - 완료")
                break
            elif status == 'ok':
                log["completed"].append({
                    "batch_idx": batch_idx,
                    "file": f"realty_bulk_{batch_idx}.pdf",
                    "time": datetime.now().isoformat(),
                    "items_in_batch": "N/A",
                })
                save_log(log, log_path)
                batch_idx += 1
                consecutive_fails = 0

                # 다음 페이지 이동 시도
                page.wait_for_timeout(2000)
                dismiss(page)
                if not go_next_page(page):
                    print("  다음 페이지 없음 - 완료")
                    break
                page.wait_for_timeout(3000)
                dismiss(page)
            else:
                print(f"  실패: {status}")
                log["failed"].append({
                    "batch_idx": batch_idx,
                    "reason": status,
                    "time": datetime.now().isoformat(),
                })
                save_log(log, log_path)
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    print("\n  [중단] 연속 3회 실패")
                    break
                # 페이지 복구 시도
                try:
                    page.evaluate(f"""() => {{
                        const el = document.getElementById('{BTN_MENU_REALTY_APPLY_RESULT}');
                        if (el) el.click();
                    }}""")
                    page.wait_for_timeout(4000)
                    dismiss(page)
                except Exception:
                    pass

        save_log(log, log_path)

        print(f"\n{'='*50}")
        print(f"  완료! 처리배치:{batch_idx} 실패:{len(log['failed'])}")
        print(f"  저장: {save_dir}")
        print(f"{'='*50}")
        print("※ 일괄 PDF는 건별 파일명 매칭이 불가합니다. 내용으로 식별해주세요.")
        input(">>> Enter로 브라우저 닫기 ")
        browser.close()


if __name__ == "__main__":
    main()
