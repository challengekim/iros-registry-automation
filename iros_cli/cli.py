#!/usr/bin/env python3
"""iros CLI — argparse 기반 서브커맨드 디스패처.

Usage:
    iros wizard
    iros corp-cart [--by-name | --by-corpnum] [--config PATH]
    iros corp-download [--config PATH] [--total N]
    iros realty-cart [--config PATH]
    iros realty-download [--config PATH]
    iros bizno [--config PATH]
    iros report [--config PATH]
    iros version
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

from iros_cli import __version__

DEFAULT_CONFIG = "./config.json"


def _resolve_config(path: str) -> tuple[str, dict | None]:
    """config path를 절대경로로 변환하고 로드. 실패 시 None 반환."""
    import json

    if not os.path.exists(path):
        print(f"[오류] 설정 파일이 없습니다: {path}")
        print("       config.json.example을 복사해서 config.json을 먼저 만들어주세요.")
        return path, None
    with open(path, encoding="utf-8") as f:
        return path, json.load(f)


def _run_script_with_exitcode(script_name: str, extra_args: list[str]) -> int:
    """프로젝트 루트의 iros_*.py 스크립트를 subprocess로 실행하고 종료코드를 반환.

    iros_wizard.run_script와 달리 returncode를 전파합니다.
    """
    import iros_wizard
    script_dir = os.path.dirname(os.path.abspath(iros_wizard.__file__))
    script_path = os.path.join(script_dir, script_name)
    if not os.path.exists(script_path):
        print(f"[오류] 스크립트가 없습니다: {script_path}", file=sys.stderr)
        return 1
    cmd = [sys.executable, script_path] + list(extra_args)
    print(f"\n실행: {' '.join(cmd)}\n")
    try:
        result = subprocess.run(cmd, cwd=script_dir)
        return result.returncode
    except KeyboardInterrupt:
        print("\n[중단됨]")
        return 130


# ---------------------------------------------------------------------------
# Subcommand handlers — each returns int (0 = success, non-zero = error)
# ---------------------------------------------------------------------------

def cmd_wizard(args: argparse.Namespace) -> int:
    import iros_wizard
    try:
        iros_wizard.main()
    except (KeyboardInterrupt, EOFError):
        print("\n[중단됨]")
        return 130
    return 0


def cmd_corp_cart(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    if args.by_name:
        companies_path = cfg.get('companies_list', './data/iros_companies.json')
        if not iros_wizard.ensure_input_file(companies_path, "companies"):
            return 1
        script = "iros_cart.py"
    else:
        corpnum_path = cfg.get('corpnum_list', './data/iros_corpnums.json')
        if not iros_wizard.ensure_input_file(corpnum_path, "corpnums"):
            return 1
        script = "iros_cart_by_corpnum.py"
    print(iros_wizard.MANUAL_REMINDER)
    try:
        input("Enter로 시작 (Ctrl+C 취소)")
    except (KeyboardInterrupt, EOFError):
        print("\n[중단됨]")
        return 130
    return _run_script_with_exitcode(script, [cfg_path])


def cmd_corp_download(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    print(iros_wizard.MANUAL_REMINDER)
    if args.total is not None:
        total_str = str(args.total)
    else:
        try:
            total_str = input("받을 건수 (기본 999): ").strip() or "999"
        except (KeyboardInterrupt, EOFError):
            print("\n[중단됨]")
            return 130
    try:
        input("Enter로 시작 (Ctrl+C 취소)")
    except (KeyboardInterrupt, EOFError):
        print("\n[중단됨]")
        return 130
    return _run_script_with_exitcode("iros_download.py", [cfg_path, total_str])


def cmd_realty_cart(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    realty_path = cfg.get('realty_list', './data/iros_realties.json')
    try:
        # ensure_input_file("realty") may prompt via prompt_realty_input
        # if the file is missing — guard against Ctrl+C / piped stdin.
        if not iros_wizard.ensure_input_file(realty_path, "realty"):
            return 1
    except (KeyboardInterrupt, EOFError):
        print("\n[중단됨]")
        return 130
    print(iros_wizard.MANUAL_REMINDER)
    print("[안내] '검색결과가 많아...' 팝업이 뜨면 자동으로 skip 처리됩니다.")
    print("      이 경우 동/호수/건물명을 추가해 입력을 구체화한 뒤 재실행하세요.\n")
    try:
        input("Enter로 시작 (Ctrl+C 취소)")
    except (KeyboardInterrupt, EOFError):
        print("\n[중단됨]")
        return 130
    return _run_script_with_exitcode("iros_cart_realty.py", [cfg_path])


def cmd_realty_download(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    print(iros_wizard.MANUAL_REMINDER)
    try:
        max_batches = input("최대 배치 수 (기본 99): ").strip() or "99"
        input("Enter로 시작 (Ctrl+C 취소)")
    except (KeyboardInterrupt, EOFError):
        print("\n[중단됨]")
        return 130
    return _run_script_with_exitcode("iros_download_realty.py", [cfg_path, max_batches])


def cmd_bizno(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    return _run_script_with_exitcode("bizno_scrape.py", [cfg_path])


def cmd_report(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    return _run_script_with_exitcode("corp_info_report.py", [cfg_path])


def cmd_version(args: argparse.Namespace) -> int:
    print(f"iros {__version__}")
    return 0


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="iros",
        description="인터넷등기소(iros.go.kr) 법인/부동산 등기부등본 자동화 CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # wizard
    p_wizard = sub.add_parser("wizard", help="대화형 마법사 메뉴 실행")
    p_wizard.set_defaults(fn=cmd_wizard)

    # corp-cart
    p_corp_cart = sub.add_parser("corp-cart", help="법인등기부등본 장바구니 담기")
    p_corp_cart.add_argument(
        "--config", default=DEFAULT_CONFIG, metavar="PATH", help="설정 파일 경로 (기본: ./config.json)"
    )
    mode_group = p_corp_cart.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--by-corpnum", dest="by_name", action="store_false",
        help="법인등록번호 기반 (기본)"
    )
    mode_group.add_argument(
        "--by-name", dest="by_name", action="store_true",
        help="상호명 기반"
    )
    p_corp_cart.set_defaults(fn=cmd_corp_cart, by_name=False)

    # corp-download
    p_corp_dl = sub.add_parser("corp-download", help="법인등기부등본 결제 후 열람·저장")
    p_corp_dl.add_argument("--config", default=DEFAULT_CONFIG, metavar="PATH")
    p_corp_dl.add_argument("--total", type=int, default=None, metavar="N", help="받을 건수 (기본: stdin 입력)")
    p_corp_dl.set_defaults(fn=cmd_corp_download)

    # realty-cart
    p_realty_cart = sub.add_parser("realty-cart", help="부동산등기부등본 장바구니 담기")
    p_realty_cart.add_argument("--config", default=DEFAULT_CONFIG, metavar="PATH")
    p_realty_cart.set_defaults(fn=cmd_realty_cart)

    # realty-download
    p_realty_dl = sub.add_parser("realty-download", help="부동산등기부등본 결제 후 열람·저장")
    p_realty_dl.add_argument("--config", default=DEFAULT_CONFIG, metavar="PATH")
    p_realty_dl.set_defaults(fn=cmd_realty_download)

    # bizno
    p_bizno = sub.add_parser("bizno", help="사업자번호 → 법인정보 조회")
    p_bizno.add_argument("--config", default=DEFAULT_CONFIG, metavar="PATH")
    p_bizno.set_defaults(fn=cmd_bizno)

    # report
    p_report = sub.add_parser("report", help="다운로드된 PDF → 종합 리포트 엑셀 생성")
    p_report.add_argument("--config", default=DEFAULT_CONFIG, metavar="PATH")
    p_report.set_defaults(fn=cmd_report)

    # version
    p_ver = sub.add_parser("version", help="버전 출력")
    p_ver.set_defaults(fn=cmd_version)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
