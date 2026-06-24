// Contract consistency gate (TS/zod side).
// Runs the SAME golden fixtures as the Python test (../../py/tests). Agreement on both
// sides means zod and pydantic stay in lockstep with the single JSON-Schema source of truth.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { ZodTypeAny } from "zod";
import {
  ExecutionRecord,
  PlatformError,
  PlatformRun,
  ProvenanceEnvelope,
  ProviderEntitlement,
  SkillManifest,
  StrategySpec,
  TraceEvent,
  TriggerPolicy,
} from "../generated/index";

const FIXTURES = fileURLToPath(new URL("../../../fixtures/", import.meta.url));

const DOMAINS: Record<string, ZodTypeAny> = {
  execution: ExecutionRecord,
  platform_error: PlatformError,
  platform_run: PlatformRun,
  provenance: ProvenanceEnvelope,
  provider_entitlement: ProviderEntitlement,
  skill_manifest: SkillManifest,
  strategy_spec: StrategySpec,
  events: TraceEvent,
  trigger_policy: TriggerPolicy,
};

function load(name: string): unknown {
  return JSON.parse(readFileSync(FIXTURES + name, "utf-8"));
}

describe.each(Object.keys(DOMAINS))("%s contract", (domain) => {
  const schema = DOMAINS[domain];

  it("accepts the valid fixture", () => {
    const r = schema.safeParse(load(`${domain}.valid.json`));
    expect(r.success, JSON.stringify((r as { error?: unknown }).error)).toBe(true);
  });

  it("rejects the invalid fixture", () => {
    const r = schema.safeParse(load(`${domain}.invalid.json`));
    expect(r.success).toBe(false);
  });
});

describe("StrategySpec security invariant", () => {
  it("rejects a smuggled free-form code field", () => {
    const spec = load("strategy_spec.valid.json") as Record<string, unknown>;
    spec.code = "import os; os.system('rm -rf /')";
    expect(StrategySpec.safeParse(spec).success).toBe(false);
  });
});
