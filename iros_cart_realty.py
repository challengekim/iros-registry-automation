#!/usr/bin/env python3
"""인터넷등기소 장바구니 자동화 - 부동산등기부등본
주소/동호수 목록을 읽어 IROS에서 부동산등기부등본(말소사항포함 기본)을 장바구니에 자동으로 담습니다.
Usage: python3 iros_cart_realty.py [config.json] [시작인덱스]

입력 파일 형식 예시 (JSON 배열):
  [
    {"label": "우리집", "address": "서초대로 219", "unit": "101동 1203호"},
    {"label": "상가", "address": "세종대로 110", "unit": "", "building_name": "시청별관"}
  ]

주의:
- TouchEn nxKey(보안프로그램)가 미설치된 경우 진행 중 설치 페이지가 뜨며,
  이 경우 스크립트는 자동 중단됩니다. 사전 설치 후 재실행하세요.
- 로그인/결제는 수동으로 진행해야 합니다.
"""
import json, os, sys, time
from datetime import datetime
from playwright.sync_api import sync_playwright


# ─── 셀렉터 상수 ────────────────────────────────────────────────

# 상단 메뉴 (부동산)
BTN_MENU_REALTY_VIEW = (
    'mf_wfm_potal_main_wf_header_gen_depth1_0_gen_depth2_0'
    '_gen_depth3_0_btn_top_menu3a'
)  # 부동산 열람·발급

# 간편검색 페이지
TAB_SIMPLE_SEARCH = (
    'mf_wfm_potal_main_wfm_content_tac_rlrg_appl_tab_tab_smpl_srch_tabHTML'
)
INPUT_ADDRESS = 'mf_wfm_potal_main_wfm_content_sbx_smpl_swrd___input'
BTN_SEARCH = 'mf_wfm_potal_main_wfm_content_btn_smpl_srch'

# 1차 결과 (간편검색 결과)
CHK_FIRST_RESULT = (
    'G_mf_wfm_potal_main_wfm_content_grd_smpl_srch_rslt___checkbox_chk_sel_0'
)
# 2차 결과 (소재지번 선택)
CHK_FIRST_LOC = (
    'G_mf_wfm_potal_main_wfm_content_grd_loc_srch_rslt___checkbox_chk_sel_0'
)
# 다음 버튼 (공통)
BTN_NEXT = 'mf_wfm_potal_main_wfm_content_btn_next'
# 결제대상 단계 (= 장바구니 담기 완료)
BTN_PAY = 'mf_wfm_potal_main_wfm_content_btn_bpay'

# 옵션 라디오 (기본값이지만 명시 선택으로 안전성 확보)
RAD_USG_VIEW = 'mf_wfm_potal_main_wfm_content_rad_usg_cls_input_0'        # 용도: 열람
RAD_REC_ALL  = 'mf_wfm_potal_main_wfm_content_rad_rgs_rec_view_cls_cd_input_0'  # 등기기록유형: 전부
RAD_NO_PUBLC = 'mf_wfm_potal_main_wfm_content_rad_enr_no_publc_yn_input_0'      # 공개여부: 미공개


# ─── 유틸 ─────────────────────────────────────────────────────

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


def build_query(item):
    """입력 1건에서 검색 쿼리 생성: address + unit + building_name (있는 것 모두 합침)."""
    addr = (item.get("address") or "").strip()
    unit = (item.get("unit") or "").strip()
    building = (item.get("building_name") or "").strip()
    parts = [p for p in (addr, unit, building) if p]
    return " ".join(parts)


def detect_security_install(page):
    """TouchEn/보안프로그램 설치 페이지 감지. 감지되면 True."""
    try:
        txt = page.evaluate("document.body ? document.body.innerText : ''")
    except Exception:
        return False
    if not txt:
        return False
    keywords = ["보안 프로그램 설치", "보안프로그램 설치", "TouchEn", "nxKey"]
    hit = any(kw in txt for kw in keywords)
    # URL 기반도 확인
    try:
        url = page.url
        if any(kw.lower() in url.lower() for kw in ["touchen", "nxkey", "security"]):
            hit = True
    except Exception:
        pass
    return hit


def detect_too_many_results(page):
    """"검색결과가 많아 소재지번 확인이 어려울 수 있습니다" 팝업 감지."""
    try:
        return page.evaluate("""() => {
            const modals = document.querySelectorAll('.w2modal_popup, #_modal');
            for (const m of modals) {
                if (m.offsetParent === null) continue;
                const t = m.innerText || '';
                if (t.includes('검색결과가 많') || t.includes('소재지번 확인')) {
                    return true;
                }
            }
            return false;
        }""")
    except Exception:
        return False


def cancel_popup(page):
    """팝업의 취소 버튼 클릭."""
    try:
        page.evaluate("""() => {
            document.querySelectorAll('a,button,input').forEach(b => {
                if (b.offsetParent !== null) {
                    const t = (b.textContent || b.value || '').trim();
                    const id = b.id || '';
                    if (id.includes('popup') && id.includes('btn_cancel2') && t === '취소') {
                        b.click();
                    }
                }
            });
        }""")
    except Exception:
        pass


def dismiss(page):
    """팝업 닫기 + 모달 숨기기 (기존 법인 코드와 동일 패턴).
    단, '검색결과가 많아' 팝업은 호출자 쪽에서 먼저 감지해 취소 처리한 뒤 dismiss.
    """
    try:
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
    except Exception:
        pass


def goto_realty_search(page):
    """부동산 열람·발급 메뉴 클릭 → 간편검색 탭 보장."""
    page.evaluate(
        f"document.getElementById('{BTN_MENU_REALTY_VIEW}') && "
        f"document.getElementById('{BTN_MENU_REALTY_VIEW}').click()"
    )
    page.wait_for_timeout(2000)
    dismiss(page)
    page.wait_for_timeout(500)
    # 간편검색 탭 확인 (기본값이지만 보험으로)
    try:
        page.evaluate(
            f"document.getElementById('{TAB_SIMPLE_SEARCH}') && "
            f"document.getElementById('{TAB_SIMPLE_SEARCH}').click()"
        )
    except Exception:
        pass
    page.wait_for_timeout(500)
    dismiss(page)


def process(page, item):
    """부동산 1건 처리. 반환값: 'completed:<count>' | 'skipped:<reason>' | 'error:<msg>' | 'abort_security'."""
    query = build_query(item)
    if not query:
        return "skipped:empty_address"

    # address만 있고 unit/building이 둘 다 없으면 다건 팝업 확률이 높지만, 일단 시도
    try:
        # 메뉴 클릭 → 검색 화면 초기 진입
        goto_realty_search(page)

        if detect_security_install(page):
            return "abort_security"

        # 주소 입력
        page.evaluate("""(q) => {
            const inp = document.getElementById('%s');
            if (!inp) return;
            inp.value = '';
            inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.value = q;
            inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.dispatchEvent(new Event('change', {bubbles:true}));
        }""" % INPUT_ADDRESS, query)
        page.wait_for_timeout(300)

        # 검색 버튼
        dismiss(page)
        page.evaluate(
            f"document.getElementById('{BTN_SEARCH}') && "
            f"document.getElementById('{BTN_SEARCH}').click()"
        )
        page.wait_for_timeout(2500)

        # 보안 프로그램 페이지 감지
        if detect_security_install(page):
            return "abort_security"

        # "검색결과가 많아" 팝업 감지
        if detect_too_many_results(page):
            cancel_popup(page)
            page.wait_for_timeout(500)
            dismiss(page)
            return "skipped:too_many_results"

        # 1차 결과 체크박스 선택
        chk_ok = page.evaluate(f"""() => {{
            const c = document.getElementById('{CHK_FIRST_RESULT}');
            if (c) {{
                if (!c.checked) c.click();
                return true;
            }}
            return false;
        }}""")

        if not chk_ok:
            return "skipped:no_result"

        # 이후 단계: 다음 버튼을 반복해서 결제대상(btn_bpay) 나올 때까지
        #  - 2차(소재지번 선택): CHK_FIRST_LOC가 있으면 체크
        #  - 3차/4차: 기본값 유지
        for step in range(12):
            # 다음 클릭 (현재 상태에서)
            dismiss(page)
            page.evaluate(
                f"document.getElementById('{BTN_NEXT}') && "
                f"document.getElementById('{BTN_NEXT}').click()"
            )
            page.wait_for_timeout(1800)

            # 팝업 감지는 dismiss 전에 (dismiss가 modal을 hidden으로 바꾸면 감지 불가)
            if detect_security_install(page):
                return "abort_security"

            if detect_too_many_results(page):
                cancel_popup(page)
                page.wait_for_timeout(500)
                dismiss(page)
                return "skipped:too_many_results"

            dismiss(page)

            state = page.evaluate(f"""() => {{
                return {{
                    hasPay: !!document.getElementById('{BTN_PAY}'),
                    hasLocChk: !!document.getElementById('{CHK_FIRST_LOC}'),
                    hasNext: !!document.getElementById('{BTN_NEXT}'),
                }};
            }}""")

            if state.get("hasPay"):
                count = page.evaluate("""() => {
                    const m = document.body.innerText.match(/전체\\s*(\\d+)\\s*건/);
                    return m ? parseInt(m[1]) : -1;
                }""")
                return f"completed:{count}"

            # 소재지번 선택 단계
            if state.get("hasLocChk"):
                page.evaluate(f"""() => {{
                    const c = document.getElementById('{CHK_FIRST_LOC}');
                    if (c && !c.checked) c.click();
                }}""")
                page.wait_for_timeout(300)
                continue

            # 옵션 페이지 (용도/등기기록유형/공개여부) — 기본값이지만 명시 클릭
            has_opt = page.evaluate(f"""() => {{
                return !!document.getElementById('{RAD_USG_VIEW}')
                    || !!document.getElementById('{RAD_REC_ALL}')
                    || !!document.getElementById('{RAD_NO_PUBLC}');
            }}""")
            if has_opt:
                page.evaluate(f"""() => {{
                    for (const id of ['{RAD_USG_VIEW}', '{RAD_REC_ALL}', '{RAD_NO_PUBLC}']) {{
                        const r = document.getElementById(id);
                        if (r && !r.checked) r.click();
                    }}
                }}""")
                page.wait_for_timeout(400)
                continue

            if not state.get("hasNext"):
                # 다음 버튼이 없는데 결제 버튼도 없음 — 예상 외 상태
                page.wait_for_timeout(1000)

        return "timeout_nostate"
    except Exception as e:
        return f"error:{str(e)[:100]}"


def main():
    cfg_path = "config.json"
    start_idx = 0
    for arg in sys.argv[1:]:
        if arg.isdigit():
            start_idx = int(arg)
        else:
            cfg_path = arg

    cfg = load_config(cfg_path)
    realty_path = cfg.get('realty_list', './data/iros_realties.json')
    log_path = cfg.get('realty_cart_log', './logs/cart_realty_log.json')

    if not os.path.exists(realty_path):
        print(f"오류: 부동산 입력 파일이 없습니다: {realty_path}")
        print("예시 파일: data/iros_realties.example.json")
        sys.exit(1)

    with open(realty_path) as f:
        realties = json.load(f)

    if not isinstance(realties, list):
        print(f"오류: 입력 파일은 JSON 배열이어야 합니다: {realty_path}")
        sys.exit(1)

    log = load_log(log_path)
    # label 기준 이미 처리 여부
    done_labels = set(log.get("completed", [])) | set(log.get("skipped", []))
    failed_labels = set(
        (c.get("label") if isinstance(c, dict) else c)
        for c in log.get("failed", [])
    )
    done_labels |= failed_labels

    print(f"총 {len(realties)}건, 이미처리 {len(done_labels)}건, index {start_idx}부터 시작")
    print("\n[사전 확인]")
    print("  - TouchEn nxKey 보안 프로그램이 설치되어 있어야 합니다.")
    print("  - 로그인은 브라우저에서 수동으로 진행합니다.")
    print("  - 결제는 완료 후 수동으로 진행합니다 (한 페이지당 최대 10건씩 일괄 열람 가능 (부동산)).\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50, args=["--window-size=1400,900"])
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, locale="ko-KR")
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        page.goto("https://www.iros.go.kr/index.jsp", wait_until="domcontentloaded", timeout=30000)

        print("=" * 50)
        print("  iros.go.kr 로그인 후 Enter 누르세요")
        print("=" * 50)
        input(">>> ")

        ok = fail = skip = 0
        aborted = False

        for i in range(start_idx, len(realties)):
            item = realties[i]
            if not isinstance(item, dict):
                continue
            label = item.get("label") or f"idx_{i}"
            if label in done_labels:
                continue

            print(f"[{i+1}/{len(realties)}] {label} ({build_query(item)[:40]})", end=" ")
            status = process(page, item)

            # 보안 프로그램 미설치 — 즉시 중단
            if status == "abort_security":
                print("\n" + "!" * 60)
                print("  [중단] TouchEn nxKey 보안 프로그램 설치 페이지 감지")
                print("  TouchEn nxKey 설치 후 브라우저 재시작 → 스크립트 처음부터 다시 실행 필요")
                print("!" * 60)
                aborted = True
                break

            # 실패 시 1회 재시도
            if status.startswith("error"):
                dismiss(page)
                page.wait_for_timeout(1000)
                try:
                    goto_realty_search(page)
                except Exception:
                    pass
                status = process(page, item)
                if status == "abort_security":
                    print("\n  [중단] 재시도 중 보안 프로그램 설치 페이지 감지")
                    aborted = True
                    break

            if status.startswith("completed"):
                log["completed"].append(label)
                ok += 1
                cart = status.split(":")[1] if ":" in status else "?"
                print(f"✓ cart:{cart} (total:{ok})")
            elif status.startswith("skipped"):
                reason = status.split(":", 1)[1] if ":" in status else ""
                log["skipped"].append(label)
                skip += 1
                hint = ""
                if reason == "too_many_results":
                    hint = " (입력 구체화 필요: 동/호수/건물명 추가)"
                print(f"- skip:{reason}{hint}")
            else:
                log["failed"].append({
                    "label": label,
                    "query": build_query(item),
                    "error": status,
                    "time": datetime.now().isoformat(),
                })
                fail += 1
                print(f"✗ {status}")

            if (ok + fail + skip) % 10 == 0:
                save_log(log, log_path)
                print(f"  >> 완료:{ok} 실패:{fail} 건너뜀:{skip}")

        save_log(log, log_path)
        print(f"\n{'='*50}")
        print(f"  완료! 성공:{ok} 실패:{fail} 건너뜀:{skip}")
        print(f"  로그: {log_path}")
        print(f"{'='*50}")

        if aborted:
            print("\n[안내] TouchEn nxKey 설치 후 브라우저를 재시작하고 다시 실행해주세요.")
            input(">>> Enter로 브라우저 닫기 ")
            browser.close()
            return

        print("\n  결제대상목록 페이지로 이동합니다...")
        try:
            page.evaluate(
                f"document.getElementById('{BTN_MENU_REALTY_VIEW}') && "
                f"document.getElementById('{BTN_MENU_REALTY_VIEW}').click()"
            )
            page.wait_for_timeout(2000)
            dismiss(page)
            page.wait_for_timeout(1000)
            page.evaluate(
                "document.getElementById('mf_wfm_potal_main_wfm_content_btn_pay_list') && "
                "document.getElementById('mf_wfm_potal_main_wfm_content_btn_pay_list').click()"
            )
            page.wait_for_timeout(3000)
            count = page.evaluate("""() => {
                const m = document.body.innerText.match(/전체\\s*(\\d+)\\s*건/);
                return m ? m[1] : '확인불가';
            }""")
            print(f"  ★ 결제대상: {count}건 - 한 페이지당 최대 10건씩 일괄 열람 가능 (부동산)")
        except Exception:
            print("  결제대상 페이지 이동 실패 - 상단 메뉴에서 직접 이동해주세요")
        input(">>> 결제 완료 후 Enter (브라우저 닫힘) ")
        browser.close()


if __name__ == "__main__":
    main()
