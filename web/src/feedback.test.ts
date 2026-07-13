import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.dirname(fileURLToPath(import.meta.url));

function read(rel: string): string {
  return fs.readFileSync(path.join(srcDir, rel), "utf8");
}

describe("feedback rail flow", () => {
  it("renders the requested form above the account row and persists through the API", () => {
    const app = read("App.tsx");
    const api = read("api.ts");

    expect(app.indexOf('className="rail-feedback"')).toBeLessThan(app.indexOf('className="rail-user"'));
    expect(app).toContain("What bugs or features would you like to see?");
    expect(app).toContain("Submit");
    expect(app).toContain("api.submitFeedback(message)");
    expect(api).toContain("postJson(`/feedback`, { message }, signal)");
  });
});
