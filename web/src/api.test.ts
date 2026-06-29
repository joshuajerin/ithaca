import { afterEach, describe, expect, it, vi } from "vitest";
import { api, AgentToolkitsError, setAuthTokenProvider } from "./api";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    statusText: init.statusText,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
}

describe("agent toolkit catalog API", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setAuthTokenProvider(null);
  });

  it("normalizes live toolkit and tool payloads from the server catalog", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      kind: "toolkits.catalog",
      toolkits: [{
        toolkit_id: "market-research",
        name: "Market Research",
        description: "Quotes and catalysts",
        required_first_tool: "start_research_session",
        direct_tools: ["start_research_session", "market_tide"],
        tools: [{ name: "run_skill", description: "Run a catalog skill" }],
        skill_count: 12,
      }],
    }));
    vi.stubGlobal("fetch", fetchMock);

    const catalog = await api.listAgentToolkits();

    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/agent\/toolkits$/), expect.any(Object));
    expect(catalog.toolkits).toEqual([{
      toolkit_id: "market-research",
      name: "Market Research",
      description: "Quotes and catalysts",
      required_first_tool: "start_research_session",
      direct_tool_count: 2,
      skill_count: 12,
      direct_tools: ["start_research_session", "market_tide"],
      tools: [{ name: "run_skill", description: "Run a catalog skill" }],
    }]);
    expect(catalog.source).toBe("live");
  });

  it("classifies auth-required catalog responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(
      { detail: "sign in to view catalog" },
      { status: 401, statusText: "Unauthorized" },
    )));

    await expect(api.listAgentToolkits()).rejects.toMatchObject({
      kind: "auth-required",
    } satisfies Partial<AgentToolkitsError>);
  });

  it("reports a missing catalog contract after probing known live endpoints", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(
      { detail: "not found" },
      { status: 404, statusText: "Not Found" },
    ));
    vi.stubGlobal("fetch", fetchMock);

    await expect(api.listAgentToolkits()).rejects.toMatchObject({
      kind: "unavailable",
    } satisfies Partial<AgentToolkitsError>);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
