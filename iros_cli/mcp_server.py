#!/usr/bin/env python3
"""iros MCP 서버 — stdio MCP server exposing iros CLI subcommands as tools.

Install: pip install iros-registry-automation[mcp]
Run:     iros-mcp   (or python -m iros_cli.mcp_server)
"""
from __future__ import annotations

import subprocess
import sys

# mcp 패키지 가용 여부 확인
try:
    import mcp  # noqa: F401
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


DEFAULT_CONFIG = "./config.json"


def _run_iros(*args: str) -> str:
    """iros CLI 서브커맨드를 subprocess로 실행하고 stdout+stderr를 반환.

    호출자가 `--config` 등 모든 플래그를 명시적으로 전달해야 합니다.
    """
    cmd = [sys.executable, "-m", "iros_cli.cli"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    output = result.stdout
    if result.stderr:
        output += "\n[stderr]\n" + result.stderr
    if result.returncode != 0:
        output += f"\n[exit code: {result.returncode}]"
    return output.strip()


def main() -> None:
    if not _MCP_AVAILABLE:
        print(
            "[오류] mcp 패키지가 설치되지 않았습니다.\n"
            "       pip install iros-registry-automation[mcp]  으로 설치 후 재실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    import asyncio

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    server = Server("iros-registry-automation")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="corp_cart",
                description=(
                    "법인등기부등본 장바구니 담기 (iros corp-cart). "
                    "by_corpnum=True(기본)이면 법인등록번호 기반, False이면 상호명 기반."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로 (기본: ./config.json)",
                            "default": DEFAULT_CONFIG,
                        },
                        "by_corpnum": {
                            "type": "boolean",
                            "description": "True=법인등록번호 기반(기본), False=상호명 기반",
                            "default": True,
                        },
                    },
                },
            ),
            Tool(
                name="corp_download",
                description="법인등기부등본 결제 후 열람·저장 (iros corp-download).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로",
                            "default": DEFAULT_CONFIG,
                        },
                        "total": {
                            "type": "integer",
                            "description": "받을 건수 (기본 999)",
                            "default": 999,
                        },
                    },
                },
            ),
            Tool(
                name="realty_cart",
                description="부동산등기부등본 장바구니 담기 (iros realty-cart).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로",
                            "default": DEFAULT_CONFIG,
                        },
                    },
                },
            ),
            Tool(
                name="realty_download",
                description="부동산등기부등본 결제 후 열람·저장 (iros realty-download).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로",
                            "default": DEFAULT_CONFIG,
                        },
                    },
                },
            ),
            Tool(
                name="bizno_lookup",
                description="사업자번호 → 법인정보 조회 (iros bizno).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로",
                            "default": DEFAULT_CONFIG,
                        },
                    },
                },
            ),
            Tool(
                name="generate_report",
                description="다운로드된 법인등기 PDF → 종합 리포트 엑셀 생성 (iros report).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로",
                            "default": DEFAULT_CONFIG,
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        cfg = arguments.get("config_path", DEFAULT_CONFIG)

        if name == "corp_cart":
            by_corpnum = arguments.get("by_corpnum", True)
            flag = "--by-corpnum" if by_corpnum else "--by-name"
            output = _run_iros("corp-cart", flag, "--config", cfg)
        elif name == "corp_download":
            total = arguments.get("total", 999)
            output = _run_iros("corp-download", "--config", cfg, "--total", str(total))
        elif name == "realty_cart":
            output = _run_iros("realty-cart", "--config", cfg)
        elif name == "realty_download":
            output = _run_iros("realty-download", "--config", cfg)
        elif name == "bizno_lookup":
            output = _run_iros("bizno", "--config", cfg)
        elif name == "generate_report":
            output = _run_iros("report", "--config", cfg)
        else:
            output = f"[오류] 알 수 없는 tool: {name}"

        return [TextContent(type="text", text=output)]

    async def _serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
