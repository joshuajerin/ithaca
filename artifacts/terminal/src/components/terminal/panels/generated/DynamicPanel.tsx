import React from "react";
import { AlertTriangle } from "lucide-react";
import { getGeneratedComponent } from "./registry";
import { GeneratedPanel } from "./GeneratedPanel";

class PanelErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode; fallback: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error("Generated panel crashed:", error);
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

// Renders an AI-generated panel: prefers its dedicated component, falls back to
// the generic renderer, and never lets a faulty generated component take down
// the whole dashboard (ErrorBoundary -> generic renderer -> static error).
export function DynamicPanel({ type, data }: { type: string; data: any }) {
  const Component = getGeneratedComponent(type);

  const genericFallback = <GeneratedPanel data={data} />;

  if (!Component) {
    return genericFallback;
  }

  return (
    <PanelErrorBoundary
      fallback={
        <PanelErrorBoundary
          fallback={
            <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground gap-2 text-center">
              <AlertTriangle className="w-4 h-4" strokeWidth={1.25} />
              <span className="editorial-label text-[9px]">Panel render error</span>
            </div>
          }
        >
          {genericFallback}
        </PanelErrorBoundary>
      }
    >
      <Component data={data} />
    </PanelErrorBoundary>
  );
}
