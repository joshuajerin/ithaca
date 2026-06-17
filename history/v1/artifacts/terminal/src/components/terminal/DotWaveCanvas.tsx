import React, { useEffect, useRef } from "react";

export function DotWaveCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let width = 0;
    let height = 0;
    let dpr = 1;

    const spacing = 26;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const rect = parent.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    resize();
    const ro = new ResizeObserver(resize);
    if (canvas.parentElement) ro.observe(canvas.parentElement);

    const start = performance.now();

    const render = (now: number) => {
      const t = (now - start) / 1000;
      ctx.clearRect(0, 0, width, height);

      const cols = Math.ceil(width / spacing) + 1;
      const rows = Math.ceil(height / spacing) + 1;

      // Wave parameters: 2-3 stacked sine waves with different frequencies/phases.
      const amplitude = Math.min(height * 0.16, 110);
      const baseY = height / 2;

      for (let i = 0; i < cols; i++) {
        const x = i * spacing;
        // Horizontal phase drives the travelling wave across the screen.
        const nx = x / width;
        const wave =
          Math.sin(nx * Math.PI * 3.0 - t * 0.9) * 0.6 +
          Math.sin(nx * Math.PI * 5.0 + t * 0.6) * 0.3 +
          Math.sin(nx * Math.PI * 1.5 - t * 0.4) * 0.4;
        const crestY = baseY + wave * amplitude;

        for (let j = 0; j < rows; j++) {
          const y = j * spacing;
          // Proximity to the wave crest controls size + brightness (halftone feel).
          const dist = Math.abs(y - crestY);
          const falloff = Math.max(0, 1 - dist / (amplitude * 1.6));
          const intensity = falloff * falloff;

          const radius = 0.7 + intensity * 2.6;
          const alpha = 0.06 + intensity * 0.85;

          ctx.beginPath();
          ctx.arc(x, y, radius, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
          ctx.fill();
        }
      }

      raf = requestAnimationFrame(render);
    };

    raf = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full"
      aria-hidden="true"
    />
  );
}
