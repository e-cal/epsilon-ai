import asyncio

from epsilon.llm import (
    Context,
    OAuthPrompt,
    StreamOptions,
    TextContent,
    Tool,
    ToolResultMessage,
    UserMessage,
    complete,
    get_model,
    get_oauth_api_key,
    login_openai_codex,
    stream,
)


async def prompt(prompt: OAuthPrompt) -> str:
    return input(f"{prompt.message} ")


async def main() -> None:
    model = get_model("openai-codex", "gpt-5.3-codex")

    credentials = await login_openai_codex(
        on_auth=lambda info: print(f"Open this URL in your browser:\n{info.url}\n"),
        on_prompt=prompt,
    )
    auth_store = {"openai-codex": credentials}
    api_key_result = await get_oauth_api_key("openai-codex", auth_store)
    if api_key_result is None:
        raise RuntimeError("OpenAI Codex OAuth login did not produce credentials")
    auth_store["openai-codex"] = api_key_result.new_credentials

    tools = [
        Tool(
            name="get_time",
            description="Get the current UTC time.",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "Optional IANA timezone."}
                },
            },
        )
    ]

    context = Context(
        system_prompt="You are a helpful assistant.",
        messages=[UserMessage(content="What time is it?", timestamp=1)],
        tools=tools,
    )

    options = StreamOptions(api_key=api_key_result.api_key)
    s = stream(model, context, options)

    async for event in s:
        match event.type:
            case "start":
                print(f"starting {event.partial.provider}/{event.partial.model}")
            case "text_delta":
                print(event.delta, end="")
            case "thinking_delta":
                print(event.delta, end="")
            case "toolcall_end":
                print(f"\nTool call: {event.tool_call.name} {event.tool_call.arguments}")
            case "done":
                print(f"\nDone: {event.reason}")
            case "error":
                print(f"\nError: {event.error.error_message}")

    final_message = await s.result()
    context.messages.append(final_message)

    tool_calls = [block for block in final_message.content if block.type == "toolCall"]
    for call in tool_calls:
        result = "2026-04-03 12:00:00 UTC"
        context.messages.append(
            ToolResultMessage(
                tool_call_id=call.id,
                tool_name=call.name,
                content=[TextContent(text=result)],
                is_error=False,
                timestamp=2,
            )
        )

    if tool_calls:
        continuation = await complete(model, context, options)
        context.messages.append(continuation)


asyncio.run(main())
