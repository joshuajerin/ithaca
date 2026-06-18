import { useEffect, useRef } from 'react';
import { AnimatePresence } from 'framer-motion';
import { useVideoPlayer } from '@/lib/video';
import { Scene1 } from './video_scenes/Scene1';
import { Scene2 } from './video_scenes/Scene2';
import { Scene3 } from './video_scenes/Scene3';
import { Scene4 } from './video_scenes/Scene4';
import { Scene5 } from './video_scenes/Scene5';
import { Scene6 } from './video_scenes/Scene6';
import { Scene7 } from './video_scenes/Scene7';
import { DotWaveBackground } from './DotWaveBackground';
import { VoiceOrb } from './VoiceOrb';
import { DashboardMockup } from './DashboardMockup';

export const SCENE_DURATIONS = {
  intro: 8000,
  voice: 10000,
  compose: 12000,
  refine: 10000,
  voicemode: 10000,
  analytics: 10000,
  outro: 8000,
};

const SCENE_COMPONENTS: Record<string, React.ComponentType> = {
  intro: Scene1,
  voice: Scene2,
  compose: Scene3,
  refine: Scene4,
  voicemode: Scene5,
  analytics: Scene6,
  outro: Scene7,
};

const SCENE_START_SEC: Record<string, number> = (() => {
  const out: Record<string, number> = {};
  let cumulativeMs = 0;
  for (const [key, ms] of Object.entries(SCENE_DURATIONS)) {
    out[key] = cumulativeMs / 1000;
    cumulativeMs += ms;
  }
  return out;
})();

const AUDIO_SEEK_EPSILON_SEC = 0.18;

export default function VideoTemplate({
  durations = SCENE_DURATIONS,
  loop = true,
  muted = false,
  onSceneChange,
}: {
  durations?: Record<string, number>;
  loop?: boolean;
  muted?: boolean;
  onSceneChange?: (sceneKey: string) => void;
} = {}) {
  const { currentSceneKey } = useVideoPlayer({ durations, loop });

  useEffect(() => {
    onSceneChange?.(currentSceneKey);
  }, [currentSceneKey, onSceneChange]);

  const baseSceneKey = currentSceneKey.replace(/_r[12]$/, '') as keyof typeof SCENE_DURATIONS;
  const SceneComponent = SCENE_COMPONENTS[baseSceneKey];

  const waveActive =
    baseSceneKey === 'intro' || baseSceneKey === 'voice' || baseSceneKey === 'voicemode';
  const showOrb = baseSceneKey === 'voice' || baseSceneKey === 'voicemode';
  const showDashboard = baseSceneKey === 'compose' || baseSceneKey === 'refine';

  const orbX = '50vw';
  const orbY = baseSceneKey === 'voicemode' ? '42vh' : baseSceneKey === 'voice' ? '24vh' : '50vh';
  const orbScale = baseSceneKey === 'voicemode' ? 1.4 : baseSceneKey === 'voice' ? 0.85 : 0.6;

  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = 0.45;
    const targetTime = SCENE_START_SEC[baseSceneKey] ?? 0;
    if (Math.abs(audio.currentTime - targetTime) > AUDIO_SEEK_EPSILON_SEC) {
      audio.currentTime = targetTime;
    }
    audio.play().catch(() => {});
  }, [currentSceneKey, baseSceneKey, muted]);

  return (
    <div className="w-full h-screen overflow-hidden relative bg-black">
      {/* Persistent background canvas */}
      <DotWaveBackground active={waveActive} />

      {/* Persistent Voice Orb (fades/positions per scene) */}
      <VoiceOrb active={showOrb} visible={showOrb} x={orbX} y={orbY} scale={orbScale} />

      {/* Dashboard mounts for compose + refine */}
      <AnimatePresence>
        {showDashboard && <DashboardMockup key="dashboard" highlightRefine={baseSceneKey === 'refine'} />}
      </AnimatePresence>

      {/* Foreground scene content */}
      <AnimatePresence mode="popLayout">
        {SceneComponent && <SceneComponent key={currentSceneKey} />}
      </AnimatePresence>

      <audio
        ref={audioRef}
        src={`${import.meta.env.BASE_URL}audio/bg_music.mp3`}
        preload="auto"
        autoPlay
        muted={muted}
      />
    </div>
  );
}
