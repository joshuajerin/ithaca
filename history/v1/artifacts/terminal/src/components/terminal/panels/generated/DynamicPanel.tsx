import React from "react";
import { AlertTriangle } from "lucide-react";
import { getGeneratedComponent, loadGeneratedComponent, type GeneratedComponent } from "./registry";
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

// Resolve a generated component for `type`. Returns a statically-registered
// component immediately (dev/HMR or build-time bundle); otherwise attempts a
// runtime fetch+compile (production), returning undefined until it resolves.
function useGeneratedComponent(type: string): GeneratedComponent | undefined {
  const [component, setComponent] = React.useState<GeneratedComponent | undefined>(
    () => getGeneratedComponent(type),
  );

  React.useEffect(() => {
    let cancelled = false;
    const immediate = getGeneratedComponent(type);
    if (immediate) {
      setComponent(() => immediate);
      return;
    }
    // Not statically available — try loading it at runtime (production path).
    setComponent(undefined);
    loadGeneratedComponent(type).then((loaded) => {
      if (!cancelled && loaded) setComponent(() => loaded);
    });
    return () => {
      cancelled = true;
    };
  }, [type]);

  return component;
}

// Renders an AI-generated panel: prefers its dedicated component (static or
// runtime-loaded), falls back to the generic renderer, and never lets a faulty
// generated component take down the dashboard (ErrorBoundary -> generic -> error).
export function DynamicPanel({ type, data }: { type: string; data: any }) {
  const Component = useGeneratedComponent(type);

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
