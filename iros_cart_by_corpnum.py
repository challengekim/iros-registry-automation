#!/usr/bin/env python3
"""인터넷등기소 장바구니 자동화 - 법인등록번호 기반 검색
법인등록번호 목록을 읽어 IROS에서 법인등기부등본(말소사항포함)을 장바구니에 자동으로 담습니다.
Usage: python3 iros_cart_by_corpnum.py [config.json]

검색 방식: 법인등록번호(등록번호) 검색
- 상호명 기반 검색은 iros_cart.py 사용
- 상호명 검색이 실패하는 경우(사명변경, 특수문자 등) 법인등록번호로 정확 검색 가능

입력 파일: {"법인등록번호": "회사명", ...} 형태의 JSON
"""
import json, os, sys
from datetime import datetime
from playwright.sync_api import sync_playwright


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


def load_log(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"completed": [], "failed": [], "skipped": []}


def save_log(log, path):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def dismiss(page):
    """팝업 닫기 + 모달 숨기기 (신청사건 처리중 팝업 포함)"""
    page.evaluate("""() => {
        document.querySelectorAll('a,button,input').forEach(b => {
            if (b.offsetParent !== null) {
                const t = (b.textContent || b.value || '').trim();
                const id = b.id || '';
                if (id.includes('btn_confirm2') && t === '확인') b.click();
                else if (id.includes('popup') && id.includes('btn_cancel2') && t === '취소') b.click();
                else if (id.includes('popup') && id.includes('btn_confirm1') && t === '확인') b.click();
            }
        });
        document.querySelectorAll('#_modal,.w2modal_popup').forEach(m => {
            m.style.display='none'; m.style.pointerEvents='none';
        });
    }""")


def select_result(page):
    """검색 결과에서 첫 번째 결과 선택 (살아있는 등기 우선, 폐쇄 등기도 OK)"""
    return page.evaluate("""() => {
        const rs = document.querySelectorAll('input[type="radio"][id*="grd_srch_rslt_list"]');
        for (const r of rs) {
            const row = r.closest('tr') || r.parentElement;
            if (!row) continue;
            const t = row.innerText;
            if (t.includes('살아있는 등기')) {
                const c = t.split('\\t');
                if (c.length >= 2 && c[c.length-2].trim() === 'N') { r.click(); return true; }
            }
        }
        if (rs.length > 0) { rs[0].click(); return true; }
        return false;
    }""")


def search_by_corpnum(page, corp_num, is_first):
    """법인등록번호로 등기부등본 검색 → 장바구니 담기"""
    clean_num = corp_num.replace('-', '')
    if not clean_num.isdigit() or len(clean_num) != 13:
        return "skipped"

    try:
        if is_first:
            page.evaluate("""() => {
                const el = document.getElementById('mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_1_gen_depth3_0_btn_top_menu3a');
                if (el) el.click();
            }""")
            page.wait_for_timeout(2000)
            dismiss(page)
            page.wait_for_timeout(1000)

        dismiss(page)

        # 등록번호검색 탭 클릭
        page.evaluate("""() => {
            document.getElementById('mf_wfm_potal_main_wfm_content_tac_crg_srch_tab_tab_drokno_tabHTML').click();
        }""")
        page.wait_for_timeout(1500)
        dismiss(page)

        # 등록번호 입력 (하이픈 없이 13자리 숫자만)
        page.evaluate("""(num) => {
            const inp = document.getElementById('mf_wfm_potal_main_wfm_content_sbx_drokno___input');
            if (inp) {
                inp.value = '';
                inp.dispatchEvent(new Event('input', {bubbles:true}));
                inp.value = num;
                inp.dispatchEvent(new Event('input', {bubbles:true}));
                inp.dispatchEvent(new Event('change', {bubbles:true}));
            }
        }""", clean_num)
        page.wait_for_timeout(300)

        # 검색 버튼 클릭
        dismiss(page)
        page.evaluate("""() => {
            document.getElementById('mf_wfm_potal_main_wfm_content_btn_dorkno_search').click();
        }""")
        page.wait_for_timeout(2500)

        # 결과 선택
        if not select_result(page):
            return "skipped"

        # 상태 기반 플로우 (말소사항 선택 → 체크박스 → 다음)
        malso_done = False
        chk_done = False
        for step in range(10):
            dismiss(page)
            page.wait_for_timeout(300)

            state = page.evaluate("""() => {
                const hasAdd = !!document.getElementById('mf_wfm_potal_main_wfm_content_btn_new_add');
                const hasPay = !!document.getElementById('mf_wfm_potal_main_wfm_content_btn_pay');
                const hasMalso = !!document.querySelector('label[for="mf_wfm_potal_main_wfm_content_rad_crg_kind_input_1"]');
                const hasChk14 = !!document.getElementById('G_mf_wfm_potal_main_wfm_content_grd_item_sel_obj_list___checkbox_dynamic_checkbox_14_0_14');
                const hasNext = !!document.getElementById('mf_wfm_potal_main_wfm_content_btn_next');
                return {hasAdd, hasPay, hasMalso, hasChk14, hasNext};
            }""")

            if state.get("hasPay"):
                count = page.evaluate("""() => {
                    const m = document.body.innerText.match(/전체\\s*(\\d+)\\s*건/);
                    return m ? parseInt(m[1]) : -1;
                }""")
                page.evaluate("""() => {
                    const el = document.getElementById('mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_1_gen_depth3_0_btn_top_menu3a');
                    if (el) el.click();
                }""")
                page.wait_for_timeout(2000)
                dismiss(page)
                page.wait_for_timeout(1000)
                return f"completed:{count}"

            if state.get("hasMalso") and not malso_done:
                page.evaluate("""() => {
                    const l = document.querySelector('label[for="mf_wfm_potal_main_wfm_content_rad_crg_kind_input_1"]');
                    if (l) l.click();
                }""")
                malso_done = True
                page.wait_for_timeout(300)

            if state.get("hasChk14") and not chk_done:
                page.evaluate("""() => {
                    const c14 = document.getElementById('G_mf_wfm_potal_main_wfm_content_grd_item_sel_obj_list___checkbox_dynamic_checkbox_14_0_14');
                    if (c14 && !c14.checked) c14.click();
                    const c15 = document.getElementById('G_mf_wfm_potal_main_wfm_content_grd_item_sel_obj_list___checkbox_dynamic_checkbox_15_0_15');
                    if (c15 && !c15.checked) c15.click();
                }""")
                chk_done = True
                page.wait_for_timeout(300)

            if state.get("hasNext"):
                dismiss(page)
                page.evaluate("document.getElementById('mf_wfm_potal_main_wfm_content_btn_next').click()")
                page.wait_for_timeout(1800)
                dismiss(page)
                page.wait_for_timeout(500)
                dismiss(page)
            else:
                page.wait_for_timeout(1000)

        return "completed_noclick"
    except Exception as e:
        return f"error:{str(e)[:100]}"


def main():
    # 인자 파싱
    cfg_path = "config.json"
    for arg in sys.argv[1:]:
        if not arg.isdigit():
            cfg_path = arg

    cfg = load_config(cfg_path)
    corpnum_path = cfg.get('corpnum_list', './data/iros_corpnums.json')
    log_path = cfg.get('cart_corpnum_log', './logs/cart_corpnum_log.json')

    with open(corpnum_path) as f:
        corp_nums = json.load(f)  # {"법인등록번호": "회사명", ...}

    log = load_log(log_path)
    done_set = set(log["completed"]) | set(log["skipped"]) | set(
        c["name"] if isinstance(c, dict) else c for c in log["failed"]
    )

    items = [(num, name) for num, name in corp_nums.items() if num not in done_set]
    print(f"총 {len(corp_nums)}개, 이미처리 {len(done_set)}개, 남은 {len(items)}개")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50, args=["--window-size=1400,900"])
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="ko-KR")
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto("https://www.iros.go.kr/index.jsp", wait_until="domcontentloaded", timeout=30000)

        print("\n" + "=" * 50)
        print("  iros.go.kr 로그인 후 Enter 누르세요")
        print("=" * 50)
        input(">>> ")

        is_first = True
        ok = fail = skip = 0

        for i, (corp_num, name) in enumerate(items):
            print(f"[{i+1}/{len(items)}] {corp_num} ({name})", end=" ")
            status = search_by_corpnum(page, corp_num, is_first)

            # 실패시 1회 재시도
            if status.startswith("error"):
                dismiss(page)
                page.wait_for_timeout(1000)
                try:
                    page.evaluate("""() => {
                        const el = document.getElementById('mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_1_gen_depth3_0_btn_top_menu3a');
                        if (el) el.click();
                    }""")
                    page.wait_for_timeout(2000)
                    dismiss(page)
                    page.wait_for_timeout(1000)
                except:
                    pass
                status = search_by_corpnum(page, corp_num, True)

            if status.startswith("completed"):
                log["completed"].append(corp_num)
                is_first = True
                ok += 1
                cart = status.split(":")[1] if ":" in status else "?"
                print(f"✓ cart:{cart} (total:{ok})")
            elif status == "skipped":
                log["skipped"].append(corp_num)
                skip += 1
                print("- skip")
            else:
                log["failed"].append({"name": corp_num, "company": name, "error": status, "time": datetime.now().isoformat()})
                is_first = True
                fail += 1
                print(f"✗ {status}")

            if (ok + fail + skip) % 10 == 0:
                save_log(log, log_path)
                print(f"  >> 완료:{ok} 실패:{fail} 건너뜀:{skip}")

        save_log(log, log_path)
        print(f"\n{'=' * 50}")
        print(f"  완료! 성공:{ok} 실패:{fail} 건너뜀:{skip}")
        print(f"  로그: {log_path}")
        print(f"{'=' * 50}")

        # 결제대상목록 이동
        print("  결제대상목록 페이지로 이동합니다...")
        try:
            page.evaluate("""() => {
                const el = document.getElementById('mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_1_gen_depth3_0_btn_top_menu3a');
                if (el) el.click();
            }""")
            page.wait_for_timeout(2000)
            dismiss(page)
            page.wait_for_timeout(1000)
            page.evaluate("document.getElementById('mf_wfm_potal_main_wfm_content_btn_pay_list').click()")
            page.wait_for_timeout(3000)
            count = page.evaluate("""() => {
                const m = document.body.innerText.match(/전체\\s*(\\d+)\\s*건/);
                return m ? m[1] : '확인불가';
            }""")
            print(f"  ★ 결제대상: {count}건 - 10건씩 결제해주세요!")
        except:
            print("  결제대상 페이지 이동 실패 - 직접 이동해주세요")
        input(">>> 결제 완료 후 Enter (브라우저 닫힘) ")
        browser.close()


if __name__ == "__main__":
    main()
