"""真实 OpenAI-compatible 模型的最小只读冒烟；不会输出密钥。"""

import asyncio

from app.ai.factory import get_chat_adapter


async def _collect(messages, *, tools=None) -> tuple[str, list[str], int]:
    text: list[str] = []
    calls: list[str] = []
    chunks = 0
    async for delta in get_chat_adapter().stream(messages, tools=tools, tool_choice="auto"):
        if delta.text:
            chunks += 1
            text.append(delta.text)
        calls.extend(item.name for item in delta.tool_calls)
    return "".join(text), calls, chunks


async def main() -> None:
    greeting, _, chunks = await _collect(
        [{"role": "user", "content": "你好呀，请只回答一句简短问候。"}]
    )
    _, calls, _ = await _collect(
        [{"role": "user", "content": "请调用库存查询工具查询 SKU-001，不要猜测结果。"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_inventory",
                    "description": "查询指定 SKU 库存",
                    "parameters": {
                        "type": "object",
                        "properties": {"sku_code": {"type": "string"}},
                        "required": ["sku_code"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
    )
    print(f"chat_ok={bool(greeting.strip())} stream_chunks={chunks}")
    print(f"tool_call_ok={'get_inventory' in calls} tool_names={','.join(calls)}")
    print(f"greeting={greeting.strip()[:120]}")


if __name__ == "__main__":
    asyncio.run(main())
