#!/usr/bin/env python3
"""
알리고(aligo.co.kr) SMS MCP Server
개인 계정으로 사용 가능한 한국 SMS 서비스
"""

import asyncio
import json
import os

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

ALIGO_URL = "https://apis.aligo.in/send/"

server = Server("aligo-sms")


def _send(api_key: str, user_id: str, sender: str, to: str, message: str) -> dict:
    r = requests.post(
        ALIGO_URL,
        data={
            "key":      api_key,
            "user_id":  user_id,
            "sender":   sender.replace("-", ""),
            "receiver": to.replace("-", ""),
            "msg":      message,
        },
        timeout=10,
    )
    return r.json()


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="send_sms",
            description="알리고(aligo.co.kr)를 통해 SMS를 발송합니다.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "수신 번호 (예: 01099859409)",
                    },
                    "message": {
                        "type": "string",
                        "description": "발송할 문자 내용",
                    },
                    "api_key": {
                        "type": "string",
                        "description": "알리고 API 키 (환경변수 ALIGO_API_KEY로 대체 가능)",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "알리고 로그인 아이디 (환경변수 ALIGO_USER_ID로 대체 가능)",
                    },
                    "sender": {
                        "type": "string",
                        "description": "발신번호 — 알리고에 등록된 번호 (환경변수 ALIGO_SENDER로 대체 가능)",
                    },
                },
                "required": ["to", "message"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "send_sms":
        raise ValueError(f"알 수 없는 도구: {name}")

    api_key = arguments.get("api_key") or os.environ.get("ALIGO_API_KEY", "")
    user_id = arguments.get("user_id") or os.environ.get("ALIGO_USER_ID", "")
    sender  = arguments.get("sender")  or os.environ.get("ALIGO_SENDER", "")
    to      = arguments["to"]
    message = arguments["message"]

    missing = [k for k, v in {
        "API 키": api_key, "사용자 ID": user_id, "발신번호": sender,
    }.items() if not v]

    if missing:
        return [TextContent(
            type="text",
            text=f"오류: 다음 항목이 없습니다 → {', '.join(missing)}\n"
                 f".env에 ALIGO_API_KEY / ALIGO_USER_ID / ALIGO_SENDER를 설정하세요.",
        )]

    try:
        result = _send(api_key, user_id, sender, to, message)
        if str(result.get("result_code")) == "1":
            return [TextContent(type="text", text=f"✅ SMS 발송 성공!\n{json.dumps(result, ensure_ascii=False, indent=2)}")]
        return [TextContent(type="text", text=f"❌ 발송 실패\n{json.dumps(result, ensure_ascii=False, indent=2)}")]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ 오류: {e}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
