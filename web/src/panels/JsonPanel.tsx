// Generic fallback renderer: pretty JSON, with a flat key/value table when the payload
// is a shallow object of scalars. No eval, no codegen — purely structural.
export function JsonPanel({ data }: { data: unknown }) {
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const entries = Object.entries(data as Record<string, unknown>);
    const allScalar = entries.length > 0 && entries.every(([, v]) => isScalar(v));
    if (allScalar) {
      return (
        <table className="tbl">
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k}>
                <td style={{ color: "var(--muted-dim)" }}>{k}</td>
                <td>{String(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }
  }
  if (Array.isArray(data) && data.length > 0 && data.every((r) => r && typeof r === "object" && !Array.isArray(r))) {
    return <ArrayTable rows={data as Record<string, unknown>[]} />;
  }
  return <pre className="pre">{safeStringify(data)}</pre>;
}

function ArrayTable({ rows }: { rows: Record<string, unknown>[] }) {
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).slice(0, 12);
  return (
    <table className="tbl">
      <thead>
        <tr>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
      </thead>
      <tbody>
        {rows.slice(0, 200).map((r, i) => (
          <tr key={i}>
            {cols.map((c) => (
              <td key={c}>{isScalar(r[c]) ? String(r[c] ?? "") : JSON.stringify(r[c])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function isScalar(v: unknown): boolean {
  return v === null || ["string", "number", "boolean"].includes(typeof v);
}

function safeStringify(data: unknown): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}
