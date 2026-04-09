"""
Claude-powered web agent.
Uses GitHub Models (OpenAI-compatible API + GitHub PAT) to drive a Playwright browser.
No separate Anthropic API key required — authenticates via your GitHub token.
"""
import json
import os
from typing import Any

from openai import OpenAI
from playwright.sync_api import sync_playwright

from browser_tools import BrowserTools, TOOL_DEFINITIONS

# GitHub Models endpoint — OpenAI-compatible, auth via GitHub PAT
GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"

SYSTEM_PROMPT = """You are a web automation agent. You control a real browser via tools.
Your job is to complete the task the user gives you step by step.

Rules:
- Always call get_page_content or screenshot first to understand the current state of the page.
- Use CSS selectors (preferred), xpath=..., or text=... locators to identify elements.
- When filling credentials, use the exact field selectors (id, name, or CSS).
- Never substitute user-provided values (username, customer name, config number) with alternatives.
- For dropdowns, use exact case-insensitive label matching only. If the exact value is unavailable, return an error.
- After filling the form, submit it by clicking the login/submit button or pressing Enter.
- After login, confirm success by checking the page title or URL changed.
- Report any errors clearly.
- Never make up information. If you cannot find a field, say so.
"""


class WebAgent:
    """LLM-driven web agent backed by Claude via GitHub Models and Playwright."""

    def __init__(
        self,
        github_token: str,
        model: str = "gpt-4o-mini",
        headless: bool = False,
        max_iterations: int = 20,
        keep_open: bool = True,
    ):
        self.client = OpenAI(
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=github_token,
        )
        self.model = model
        self.headless = headless
        self.max_iterations = max_iterations if max_iterations != 20 else 35
        self.keep_open = keep_open

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str) -> str:
        """Start the browser and complete a task. Returns a summary."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(
                ignore_https_errors=True,  # dev/staging cert may be self-signed
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            tools = BrowserTools(page)

            result = self._agentic_loop(task, tools)

            if self.keep_open:
                input("\n[Browser] Task finished — press Enter to close the browser...")

            context.close()
            browser.close()

        return result

    # ------------------------------------------------------------------
    # Internal: agentic loop
    # ------------------------------------------------------------------

    def _agentic_loop(self, task: str, tools: BrowserTools) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        def _compact_messages(msgs: list[dict], aggressive: bool = False) -> list[dict]:
            """Keep payload small enough for low-context models by pruning old history."""
            limit = 8 if aggressive else 14
            tail_size = 8 if aggressive else 16
            if len(msgs) <= limit:
                return msgs
            # Keep system + initial task and a validated recent tail.
            # Ensure no orphan "tool" messages exist without their preceding assistant tool_calls.
            base = [msgs[0], msgs[1]]
            tail = msgs[-tail_size:]
            cleaned_tail: list[dict] = []
            pending_tool_ids: set[str] = set()

            for m in tail:
                role = m.get("role")

                if role == "assistant":
                    cleaned_tail.append(m)
                    tool_calls = m.get("tool_calls") or []
                    pending_tool_ids = {
                        tc.get("id")
                        for tc in tool_calls
                        if isinstance(tc, dict) and tc.get("id")
                    }
                    continue

                if role == "tool":
                    tcid = m.get("tool_call_id")
                    if tcid and tcid in pending_tool_ids:
                        cleaned_tail.append(m)
                        pending_tool_ids.discard(tcid)
                    continue

                # user/system or any other safe role
                cleaned_tail.append(m)
                pending_tool_ids = set()

            return [*base, *cleaned_tail]

        for iteration in range(self.max_iterations):
            print(f"\n[Agent] Iteration {iteration + 1}/{self.max_iterations}")

            payload_messages = _compact_messages(messages)
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=payload_messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    max_tokens=1200,
                )
            except Exception as exc:
                err_text = str(exc)
                if "tokens_limit_reached" not in err_text and "Request body too large" not in err_text:
                    raise

                print("[Agent] Token limit reached, retrying with more aggressive history compaction...")
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=_compact_messages(messages, aggressive=True),
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    max_tokens=800,
                )

            assistant_msg = response.choices[0].message
            # Append as a plain dict so we can always serialise it back
            messages.append(assistant_msg.model_dump(exclude_unset=False))

            # No tool calls → model is done
            if not assistant_msg.tool_calls:
                final_text = assistant_msg.content or "Task completed (no final message)."
                print(f"\n[Agent] Done: {final_text}")
                return final_text

            # Execute every tool call the model requested
            for tc in assistant_msg.tool_calls:
                tool_input = json.loads(tc.function.arguments)
                print(f"  -> Tool: {tc.function.name}  Input: {json.dumps(tool_input, default=str)[:200]}")
                result_str = tools.execute(tc.function.name, tool_input)

                # Truncate large results aggressively to avoid hitting token limits (8K model limit)
                MAX_RESULT_CHARS = 350
                if len(result_str) > MAX_RESULT_CHARS:
                    result_str = result_str[:MAX_RESULT_CHARS] + f"\n...[truncated, {len(result_str)} chars total]"

                if tc.function.name == "screenshot" and not result_str.startswith("ERROR"):
                    # Avoid image payload uploads for models/endpoints that reject inline image data.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "Screenshot captured successfully.",
                    })
                else:
                    # Safe print handling for Unicode characters on Windows console
                    safe_result = str(result_str)[:300].encode('utf-8', errors='replace').decode('utf-8', errors='replace')
                    print(f"     Result: {safe_result}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })

        return "Max iterations reached without completing the task."
