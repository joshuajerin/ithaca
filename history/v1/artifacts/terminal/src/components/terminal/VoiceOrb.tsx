import React, { useEffect, useRef } from "react";
import type { VoiceStatus } from "@/hooks/useVoiceConductor";

interface VoiceOrbProps {
  status: VoiceStatus;
  userLevel: number;
  agentLevel: number;
  size?: number;
}

/**
 * A glowing monochrome sphere that reacts to live audio. It pulses to the user's
 * voice while listening and to the agent's voice while speaking, with a calm
 * breathing idle state in between. Pure canvas, black-and-white aesthetic.
 */
export function VoiceOrb({ status, userLevel, agentLevel, size = 240 }: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Mirror props into refs so the animation loop reads fresh values.
  const stateRef = useRef({ status, userLevel, agentLevel });
  useEffect(() => {
    stateRef.current = { status, userLevel, agentLevel };
  }, [status, userLevel, agentLevel]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.26;

    let raf = 0;
    let t = 0;
    // Smoothed amplitude for fluid motion.
    let amp = 0;

    const draw = () => {
      t += 0.016;
      const { status: st, userLevel: ul, agentLevel: al } = stateRef.current;

      const breathing = (Math.sin(t * 1.1) + 1) / 2; // 0..1 idle pulse
      let target = 0.04 + breathing * 0.06;
      if (st === "listening") target = Math.max(target, ul);
      else if (st === "speaking") target = Math.max(target, al);
      else if (st === "thinking") target = 0.18 + breathing * 0.18;
      amp += (target - amp) * 0.18;

      ctx.clearRect(0, 0, size, size);

      const r = baseR * (1 + amp * 0.45);
      const glow = 0.35 + amp * 0.65;

      // Outer atmospheric glow
      const outer = ctx.createRadialGradient(cx, cy, r * 0.2, cx, cy, r * 2.6);
      outer.addColorStop(0, `rgba(255,255,255,${0.18 * glow})`);
      outer.addColorStop(0.4, `rgba(255,255,255,${0.06 * glow})`);
      outer.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = outer;
      ctx.fillRect(0, 0, size, size);

      // Reactive concentric rings
      const ringCount = 3;
      for (let i = 0; i < ringCount; i++) {
        const phase = t * (0.6 + i * 0.25) + i * 1.7;
        const ringR = r * (1.25 + i * 0.28) + Math.sin(phase) * (4 + amp * 22);
        ctx.beginPath();
        ctx.arc(cx, cy, ringR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255,255,255,${(0.16 - i * 0.04) * (0.5 + glow)})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Core sphere with soft shading
      const core = ctx.createRadialGradient(
        cx - r * 0.3,
        cy - r * 0.3,
        r * 0.1,
        cx,
        cy,
        r,
      );
      core.addColorStop(0, "rgba(255,255,255,0.98)");
      core.addColorStop(0.55, `rgba(235,235,235,${0.85})`);
      core.addColorStop(1, `rgba(120,120,120,${0.25 + amp * 0.3})`);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fillStyle = core;
      ctx.shadowColor = "rgba(255,255,255,0.9)";
      ctx.shadowBlur = 18 + amp * 60;
      ctx.fill();
      ctx.shadowBlur = 0;

      // Inner specular highlight
      ctx.beginPath();
      ctx.arc(cx - r * 0.28, cy - r * 0.28, r * 0.28, 0, Math.PI * 2);
      const hi = ctx.createRadialGradient(
        cx - r * 0.28,
        cy - r * 0.28,
        0,
        cx - r * 0.28,
        cy - r * 0.28,
        r * 0.28,
      );
      hi.addColorStop(0, "rgba(255,255,255,0.9)");
      hi.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = hi;
      ctx.fill();

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      className="select-none"
      aria-hidden
    />
  );
}
