import { GeneratedPanel } from "./GeneratedPanel";

// Unknown/agent-produced panel payloads render through a static generic renderer.
// The dashboard deliberately does not fetch, transpile, or evaluate generated TSX.
export function DynamicPanel({ type, data }: { type: string; data: any }) {
  const payload =
    data && typeof data === "object" && !Array.isArray(data)
      ? { type, ...data }
      : { type, value: data };
  return <GeneratedPanel data={payload} />;
}
