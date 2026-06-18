import * as React from "react"

const MOBILE_BREAKPOINT = 768
const TABLET_BREAKPOINT = 1024

export function useIsMobile() {
  const [isMobile, setIsMobile] = React.useState<boolean | undefined>(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    }
    mql.addEventListener("change", onChange)
    setIsMobile(window.innerWidth < MOBILE_BREAKPOINT)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return !!isMobile
}

export type Breakpoint = "mobile" | "tablet" | "desktop"

/**
 * Three-tier viewport breakpoint:
 *   mobile  < 768px   — single-column stack, console in a drawer
 *   tablet  < 1024px  — 6-column flow grid, console in a drawer
 *   desktop ≥ 1024px  — 12-column placed grid, fixed console sidebar
 */
export function useBreakpoint(): Breakpoint {
  const [bp, setBp] = React.useState<Breakpoint>("desktop")

  React.useEffect(() => {
    const compute = () => {
      const w = window.innerWidth
      if (w < MOBILE_BREAKPOINT) setBp("mobile")
      else if (w < TABLET_BREAKPOINT) setBp("tablet")
      else setBp("desktop")
    }
    compute()
    window.addEventListener("resize", compute)
    return () => window.removeEventListener("resize", compute)
  }, [])

  return bp
}
