import { useEffect, useRef } from 'react';

export function DotWaveBackground({ active }: { active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const activeRef = useRef(active);
  activeRef.current = active;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let width = 0;
    let height = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);

    const resize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);

    let raf = 0;
    let time = 0;
    let curAmp = 14;
    let curSpeed = 0.5;
    const spacing = 30;
    const TWO_PI = Math.PI * 2;

    const render = () => {
      const targetAmp = activeRef.current ? 38 : 14;
      const targetSpeed = activeRef.current ? 1.35 : 0.5;
      curAmp += (targetAmp - curAmp) * 0.04;
      curSpeed += (targetSpeed - curSpeed) * 0.04;
      time += 0.014;

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, width, height);

      const cy = height / 2;

      for (let x = 0; x < width; x += spacing) {
        const w1 = Math.sin(x * 0.005 + time * curSpeed) * curAmp;
        const w3 = Math.cos(x * 0.002 - time * curSpeed * 0.8) * (curAmp * 1.2);
        for (let y = 0; y < height; y += spacing) {
          const w2 = Math.sin(x * 0.01 + y * 0.01 - time * curSpeed * 1.2) * (curAmp * 0.6);
          const total = w1 + w2 + w3;
          const dist = Math.abs(y - (cy + total));
          const proximity = dist < 150 ? 1 - dist / 150 : 0;

          if (proximity <= 0.02) {
            ctx.fillStyle = 'rgba(255,255,255,0.05)';
            ctx.beginPath();
            ctx.arc(x, y, 0.7, 0, TWO_PI);
            ctx.fill();
            continue;
          }

          const size = 0.7 + proximity * 2.3;
          const alpha = 0.05 + proximity * 0.55;
          ctx.fillStyle = `rgba(255,255,255,${alpha})`;
          ctx.beginPath();
          ctx.arc(x, y, size, 0, TWO_PI);
          ctx.fill();
        }
      }

      raf = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 z-0" />;
}
