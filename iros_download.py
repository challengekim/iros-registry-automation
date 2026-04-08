#!/usr/bin/env python3
"""인터넷등기소 열람+저장+파일명변경 자동화
열람 후 항목이 사라지므로 항상 첫 번째 열람 버튼만 클릭합니다.
Usage: python3 iros_download.py [config.json] [건수]
"""
import json, sys, os, re, time, shutil
from datetime import datetime
from difflib import SequenceMatcher
from playwright.sync_api import sync_playwright


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


def find_best_match(name, companies):
    clean = re.sub(r'\(.*?\)', '', name)
    clean = re.sub(r'주식회사|유한회사|유한책임회사|사단법인|재단법인', '', clean).strip()
    best_score, best_match = 0, None
    for c in companies:
        c_clean = re.sub(r'[^가-힣a-zA-Z0-9]', '', c)
        n_clean = re.sub(r'[^가-힣a-zA-Z0-9]', '', clean)
        if c_clean == n_clean:
            return c
        if c_clean in n_clean or n_clean in c_clean:
            score = len(min(c_clean, n_clean, key=len)) / max(len(max(c_clean, n_clean, key=len)), 1)
            if score > best_score:
                best_score, best_match = score, c
        score = SequenceMatcher(None, c_clean, n_clean).ratio()
        if score > best_score:
            best_score, best_match = score, c
    return best_match if best_score > 0.5 else clean


def dismiss(page):
    try:
        page.evaluate("""() => {
            document.querySelectorAll('#_modal,.w2modal_popup').forEach(m => {
                m.style.display='none'; m.style.pointerEvents='none';
            });
        }""")
    except:
        pass


def snapshot_files(dl_dir):
    files = set()
    try:
        for f in os.listdir(dl_dir):
            fp = os.path.join(dl_dir, f)
            if os.path.isfile(fp):
                files.add(fp)
    except:
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


def click_save(page):
    try:
        page.click('input[id*="wframe_btn_download"]', timeout=5000, force=True)
        return True
    except:
        pass
    try:
        page.click('input[value="저장"]', timeout=3000, force=True)
        return True
    except:
        pass
    return False


def close_viewer(page):
    try:
        page.click('input[id*="wframe_btn_close"]', timeout=3000, force=True)
        page.wait_for_timeout(1500)
        return
    except:
        pass
    try:
        page.click('input[value="닫기"]', timeout=2000, force=True)
        page.wait_for_timeout(1500)
        return
    except:
        pass
    try:
        page.keyboard.press('Escape')
        page.wait_for_timeout(1500)
    except:
        pass
    dismiss(page)


def process_one(page, companies, log, dl_dir, save_dir):
    """한 건 처리: 항상 첫 번째 열람 버튼 클릭"""
    dismiss(page)

    # 1. 첫 번째 열람 버튼 클릭 + 상호 추출
    result = page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            if (b.offsetParent !== null && b.textContent.trim() === '열람') {
                const gp = b.parentElement ? b.parentElement.parentElement : null;
                let sangho = '';
                if (gp) {
                    const parts = gp.innerText.split('\\t');
                    if (parts.length > 4) sangho = parts[4].trim();
                }
                b.click();
                return {clicked: true, sangho: sangho};
            }
        }
        return {clicked: false, sangho: ''};
    }""")

    if not result.get("clicked"):
        return ("no_more", "")

    sangho = result.get("sangho", "")
    print(f"{sangho[:30]}", end=" ", flush=True)

    # 2. 확인 팝업
    page.wait_for_timeout(3000)
    for sel in [
        'input[id*="btn_confirm2"][value="확인"]',
        'a[id*="btn_confirm2"]',
        'input[value="확인"]',
        'button:has-text("확인")',
    ]:
        try:
            page.click(sel, timeout=2000)
            print("(확인)", end=" ", flush=True)
            break
        except:
            continue

    # 3. 문서 로딩 대기
    page.wait_for_timeout(8000)

    # 4. 저장
    before_files = snapshot_files(dl_dir)
    if not click_save(page):
        print("(저장실패)", end=" ", flush=True)
        close_viewer(page)
        return ("save_fail", sangho)
    print("(저장OK)", end=" ", flush=True)

    # 5. 변환 확인 팝업
    page.wait_for_timeout(2000)
    for sel in ['input[value="확인"]', 'button:has-text("확인")']:
        try:
            page.click(sel, timeout=3000)
            break
        except:
            continue

    # 6. 다운로드 대기
    dl_file = wait_for_new_file(before_files, dl_dir)
    if not dl_file:
        print("다운로드안됨 X")
        close_viewer(page)
        return ("dl_fail", sangho)

    # 7. 파일 처리: UUID 파일(.pdf 확장자 없음)이면 .pdf 추가
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
    except:
        pass

    matched = find_best_match(sangho, companies) if sangho else "unknown"
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', matched)
    new_path = os.path.join(save_dir, f"{safe_name}.pdf")
    if os.path.exists(new_path):
        new_path = os.path.join(save_dir, f"{safe_name}_{int(time.time())}.pdf")
    shutil.move(dl_file, new_path)
    print(f"-> {os.path.basename(new_path)} OK")

    close_viewer(page)
    return ("ok", sangho, matched, new_path)


def main():
    # 인자 파싱: config.json [건수] 또는 [건수] config.json
    cfg_path = "config.json"
    total = 999
    for arg in sys.argv[1:]:
        if arg.isdigit():
            total = int(arg)
        else:
            cfg_path = arg

    cfg = load_config(cfg_path)
    companies_path = cfg.get('companies_list', './data/iros_companies.json')
    log_path = cfg.get('download_log', './logs/download_log.json')
    dl_dir = cfg.get('download_temp', '/tmp/iros_pdf_downloads')
    save_dir = os.path.expanduser(cfg.get('save_dir', '~/Downloads/등기부등본'))

    with open(companies_path) as f:
        companies = json.load(f)
    log = load_log(log_path)

    os.makedirs(dl_dir, exist_ok=True)
    os.makedirs(save_dir, exist_ok=True)
    os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)

    print(f"건수: {total}, 이미완료: {len(log['completed'])}건")
    print(f"저장: {save_dir}")

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

        print("\n" + "=" * 50)
        print("  iros.go.kr 로그인 후 Enter")
        print("=" * 50)
        input(">>> ")

        # 신청결과 확인 페이지 이동
        print("신청결과 확인 페이지 이동...")
        try:
            page.evaluate("""() => {
                const el = document.getElementById(
                    'mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_1_gen_depth3_6_gen_depth4_0_btn_top_menu4'
                );
                if (el) el.click();
            }""")
        except:
            pass
        page.wait_for_timeout(4000)
        dismiss(page)

        ok, fail, done = 0, 0, 0
        consecutive_fails = 0

        while done < total:
            done += 1
            print(f"[{done}] ", end="", flush=True)

            try:
                result = process_one(page, companies, log, dl_dir, save_dir)

                if result[0] == "no_more":
                    print("열람 버튼 없음 - 완료")
                    break
                elif result[0] == "ok":
                    _, sangho, matched, filepath = result
                    log["completed"].append({
                        "sangho": sangho,
                        "matched": matched,
                        "file": filepath,
                        "time": datetime.now().isoformat(),
                    })
                    ok += 1
                    consecutive_fails = 0
                else:
                    status = result[0]
                    sangho = result[1] if len(result) > 1 else ""
                    log["failed"].append({
                        "sangho": sangho,
                        "reason": status,
                        "time": datetime.now().isoformat(),
                    })
                    fail += 1
                    consecutive_fails += 1

            except Exception as e:
                print(f"오류: {str(e)[:60]} X")
                log["failed"].append({
                    "sangho": "",
                    "error": str(e)[:100],
                    "time": datetime.now().isoformat(),
                })
                fail += 1
                consecutive_fails += 1
                close_viewer(page)
                page.wait_for_timeout(2000)
                dismiss(page)

            # 연속 3회 실패 시 페이지 복구
            if consecutive_fails >= 3:
                print("\n  [경고] 연속 3회 실패 - 페이지 복구 중...")
                try:
                    page.evaluate("""() => {
                        const el = document.getElementById(
                            'mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_1_gen_depth3_6_gen_depth4_0_btn_top_menu4'
                        );
                        if (el) el.click();
                    }""")
                    page.wait_for_timeout(4000)
                    dismiss(page)
                    consecutive_fails = 0
                except:
                    pass

            if done % 5 == 0:
                save_log(log, log_path)

        save_log(log, log_path)

        print(f"\n{'='*50}")
        print(f"  완료! 성공:{ok} 실패:{fail}")
        print(f"  저장: {save_dir}")
        print(f"{'='*50}")
        input(">>> Enter로 브라우저 닫기 ")
        browser.close()


if __name__ == "__main__":
    main()
