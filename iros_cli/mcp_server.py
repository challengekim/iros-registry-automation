#!/usr/bin/env python3
"""iros MCP 서버 — stdio MCP server exposing iros CLI subcommands as tools.

Install: pip install iros-registry-automation[mcp]
Run:     iros-mcp   (or python -m iros_cli.mcp_server)

노출 tool: bizno_lookup, generate_report (비대화형 2종만)
브라우저 기반 cart/download 작업(corp_cart, corp_download, realty_cart,
realty_download)은 수동 로그인 + 수동 결제가 필요해 MCP에서 사용 불가.
해당 기능은 터미널에서 `iros` CLI를 직접 사용하세요.
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
    stdin=DEVNULL: MCP stdio 스트림 오염 방지.
    """
    cmd = [sys.executable, "-m", "iros_cli.cli"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
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

    server = Server(
        "iros-registry-automation",
        # 브라우저 기반 cart/download(corp_cart, corp_download, realty_cart,
        # realty_download)는 MCP에서 제공하지 않습니다.
        # 이 기능들은 수동 로그인 + 수동 결제가 필요하며 대화형 input()을
        # 사용해 stdio MCP 스트림과 충돌합니다.
        # 터미널에서 `iros` CLI를 직접 사용하세요.
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="bizno_lookup",
                description=(
                    "사업자번호 → 법인정보 조회 (iros bizno). "
                    "비대화형 — MCP에서 직접 호출 가능. "
                    "브라우저 기반 cart/download 작업은 MCP에서 제공하지 않으며, "
                    "터미널에서 `iros` CLI를 직접 사용해야 합니다."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "config_path": {
                            "type": "string",
                            "description": "config.json 경로 (기본: ./config.json)",
                            "default": DEFAULT_CONFIG,
                        },
                    },
                },
            ),
            Tool(
                name="generate_report",
                description=(
                    "다운로드된 법인등기 PDF → 종합 리포트 엑셀 생성 (iros report). "
                    "비대화형 — MCP에서 직접 호출 가능. "
                    "브라우저 기반 cart/download 작업은 MCP에서 제공하지 않으며, "
                    "터미널에서 `iros` CLI를 직접 사용해야 합니다."
                ),
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

        if name == "bizno_lookup":
            output = _run_iros("bizno", "--config", cfg)
        elif name == "generate_report":
            output = _run_iros("report", "--config", cfg)
        else:
            output = (
                f"[오류] 알 수 없는 tool: {name}\n"
                "corp_cart, corp_download, realty_cart, realty_download는 MCP에서 지원하지 않습니다. "
                "터미널에서 `iros` CLI를 직접 사용하세요."
            )

        return [TextContent(type="text", text=output)]

    async def _serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
