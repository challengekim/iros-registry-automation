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


# ---------------------------------------------------------------------------
# Subcommand handlers — each returns int (0 = success, 1 = error)
# ---------------------------------------------------------------------------

def cmd_wizard(args: argparse.Namespace) -> int:
    import iros_wizard
    try:
        iros_wizard.main()
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


def cmd_corp_cart(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    try:
        if args.by_name:
            iros_wizard.cart_by_company(cfg, cfg_path)
        else:
            # default: --by-corpnum
            iros_wizard.cart_by_corpnum(cfg, cfg_path)
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


def cmd_corp_download(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    try:
        if args.total is not None:
            # total이 지정된 경우: stdin 프롬프트 없이 직접 run_script 호출
            total_str = str(args.total)
            print(iros_wizard.MANUAL_REMINDER)
            input("Enter로 시작 (Ctrl+C 취소)")
            iros_wizard.run_script("iros_download.py", [cfg_path, total_str])
        else:
            # total 미지정: 기존 download_corp 그대로 (stdin에서 물어봄)
            iros_wizard.download_corp(cfg_path)
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


def cmd_realty_cart(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    try:
        iros_wizard.cart_realty(cfg, cfg_path)
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


def cmd_realty_download(args: argparse.Namespace) -> int:
    cfg_path, _ = _resolve_config(args.config)
    if _ is None:
        return 1
    import iros_wizard
    try:
        iros_wizard.download_realty(cfg_path)
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


def cmd_bizno(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    try:
        iros_wizard.run_bizno(cfg_path)
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cfg_path, cfg = _resolve_config(args.config)
    if cfg is None:
        return 1
    import iros_wizard
    try:
        iros_wizard.run_report(cfg_path)
    except KeyboardInterrupt:
        print("\n[중단됨]")
    return 0


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
        "--by-corpnum", dest="by_name", action="store_false", default=False,
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
