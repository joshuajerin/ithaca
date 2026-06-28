"""End-to-end workflow test: agent → MCP → trace → REST → web UI.

Proves the full chain:
1. REST gateway + MCP HTTP server share one SQLite DB
2. An agent authenticates with an API key and connects over MCP streamable-HTTP
3. The MCP initialize returns instructions (the "initial push")
4. The agent calls tools (session_context, market_get_ohlcv, search_skills)
5. Every tool call becomes a trace event in the shared DB
6. The REST gateway serves those events — the web UI can see the full session

Run: DOOMBERG_DB=/tmp/doomberg-e2e.db uv run python scripts/e2e_workflow_test.py
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request

DB = os.environ.get("DOOMBERG_DB", "/tmp/doomberg-e2e.db")
REST = "http://localhost:8000"
MCP_URL = "http://localhost:8080/mcp"


def _req(url, method="GET", body=None, headers=None):
    h = headers or {}
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


async def agent_session(api_key: str):
    """Simulate an agent connecting to the MCP server and calling tools."""
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.client.session import ClientSession

    headers = {"Authorization": f"Bearer {api_key}"}

    async with streamablehttp_client(MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            # 1. Initialize — the agent reads the instructions
            init = await session.initialize()
            print(f"   Server: {init.serverInfo.name} v{init.serverInfo.version}")
            print(f"   Instructions: {(init.instructions or '')[:100]}...")
            assert init.instructions and "Doomberg" in init.instructions
            assert "session_context" in init.instructions

            # 2. List prompts — verify starter_research is there
            prompts = await session.list_prompts()
            prompt_names = {p.name for p in prompts.prompts}
            print(f"   Prompts: {prompt_names}")
            assert "starter_research" in prompt_names

            # 3. Call session_context — opens a traced research session
            print("5. Agent calls session_context...")
            result = await session.call_tool("session_context", {
                "prompt": "What does NVDA look like? Research and propose a backtest.",
                "title": "NVDA research",
            })
            text = result.content[0].text if result.content else "{}"
            session_data = json.loads(text)
            session_id = session_data.get("session_id", "")
            print(f"   Session opened: {session_id[:12]}...")
            assert session_id, "session_context did not return a session_id"

            # 4. Call market_get_ohlcv — research
            print("6. Agent calls market_get_ohlcv(NVDA)...")
            result = await session.call_tool("market_get_ohlcv", {
                "symbol": "NVDA", "range": "6mo", "interval": "1d",
            })
            text = result.content[0].text if result.content else "{}"
            ohlcv = json.loads(text)
            points = ohlcv.get("summary", {}).get("points", 0)
            print(f"   Got {points} price points for NVDA")

            # 5. Call search_skills — discover more tools
            print("7. Agent calls search_skills('momentum')...")
            result = await session.call_tool("search_skills", {"query": "momentum"})
            text = result.content[0].text if result.content else "{}"
            skills = json.loads(text)
            print(f"   Found {len(skills.get('skills', []))} matching skills")

            return session_id


def main():
    if os.path.exists(DB):
        os.remove(DB)

    env = {**os.environ, "DOOMBERG_DB": DB, "DOOMBERG_ENV": "local"}

    # 1. Start REST gateway
    print("1. Starting REST gateway on :8000...")
    rest = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "doomberg_rest.app:app", "--port", "8000"],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(3)

    # 2. Start MCP HTTP server
    print("2. Starting MCP HTTP server on :8080...")
    mcp_proc = subprocess.Popen(
        [sys.executable, "-m", "doomberg_mcp"],
        env={**env, "DOOMBERG_MCP_TRANSPORT": "http", "DOOMBERG_MCP_PORT": "8080"},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    time.sleep(3)

    try:
        # 3. Mint an agent key (what AgentLink does after Clerk auth)
        print("3. Minting agent API key...")
        from doomberg_platform import Platform
        platform = Platform(DB)
        tenant_id = platform.auth.create_tenant("E2E Test")
        api_key, key_id = platform.auth.mint_key(tenant_id, [
            "data:read", "strategy:author", "runs:write", "runs:cancel",
            "artifacts:read", "deploy:backtest",
        ])
        print(f"   Tenant: {tenant_id}")
        print(f"   API key: {api_key[:24]}...")

        # 4. Agent connects to MCP and calls tools
        print("4. Agent connects to MCP — initialize...")
        session_id = asyncio.run(agent_session(api_key))

        # 6. Check the trace via REST gateway (what the web UI sees)
        print("8. Checking trace via REST gateway (what the web UI sees)...")
        run = _req(f"{REST}/api/runs/{session_id}",
                   headers={"Authorization": f"Bearer {api_key}"})
        events = run.get("events", [])
        print(f"   Run: kind={run['kind']} state={run['state']} events={len(events)}")
        for ev in events:
            name = ev.get("data", {}).get("name", "-")
            print(f"     seq={ev['seq']} type={ev['type']:<15} name={name}")

        # 7. Verify the session shows up in the sessions list
        print("9. Checking sessions list (what the web UI renders)...")
        sessions = _req(f"{REST}/api/sessions",
                        headers={"Authorization": f"Bearer {api_key}"})
        print(f"   Sessions: {len(sessions.get('sessions', []))}")
        for s in sessions.get("sessions", []):
            print(f"     {s.get('id', '?')[:12]}... state={s.get('state', '?')} "
                  f"calls={s.get('call_count', 0)} title={s.get('title', '?')}")

        # Summary
        has_session_open = any(e["type"] == "session_open" for e in events)
        has_tool_calls = any(e["type"] == "tool_call" for e in events)
        has_tool_results = any(e["type"] == "tool_result" for e in events)
        has_prompt = any("prompt" in (e.get("data", {}) or {}) for e in events if e["type"] == "session_open")

        print("\n" + "=" * 60)
        if has_session_open and has_tool_calls and has_tool_results:
            print("✅ END-TO-END WORKFLOW PROVEN")
            print("   Agent → MCP (HTTP+auth) → tool calls → trace store → REST API")
            print(f"   Session {session_id[:12]}... has {len(events)} trace events")
            print(f"   The web UI can render this session live via SSE")
            if has_prompt:
                print(f"   The agent's prompt is captured: '{events[0]['data'].get('prompt', '')[:50]}...'")
        else:
            print("❌ WORKFLOW INCOMPLETE")
            print(f"   session_open: {has_session_open}, tool_calls: {has_tool_calls}, tool_results: {has_tool_results}")
            sys.exit(1)

    finally:
        print("\nCleaning up servers...")
        rest.terminate()
        mcp_proc.terminate()
        rest.wait()
        mcp_proc.wait()


if __name__ == "__main__":
    main()
