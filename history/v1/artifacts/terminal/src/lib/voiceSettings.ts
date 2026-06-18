/**
 * Persisted user preferences for Voice Mode synthesis: which gpt-audio voice to
 * use and how fast it should speak. Stored in localStorage so the choice
 * survives reloads, and passed through to the backend /speak call.
 */

export interface VoiceOption {
  id: string;
  label: string;
  /** Short character note shown under the picker. */
  hint: string;
}

// Keep this list in sync with AVAILABLE_VOICES in artifacts/api-server/app/ai.py.
export const VOICE_OPTIONS: VoiceOption[] = [
  { id: "alloy", label: "Alloy", hint: "Balanced, neutral" },
  { id: "ash", label: "Ash", hint: "Warm, grounded" },
  { id: "ballad", label: "Ballad", hint: "Soft, expressive" },
  { id: "coral", label: "Coral", hint: "Bright, friendly" },
  { id: "echo", label: "Echo", hint: "Calm, even" },
  { id: "sage", label: "Sage", hint: "Measured, clear" },
  { id: "shimmer", label: "Shimmer", hint: "Light, airy" },
  { id: "verse", label: "Verse", hint: "Lively, dynamic" },
];

export const MIN_SPEED = 0.5;
export const MAX_SPEED = 1.5;
export const SPEED_STEP = 0.1;

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  voice: "alloy",
  speed: 1.0,
};

export interface VoiceSettings {
  voice: string;
  speed: number;
}

const STORAGE_KEY = "agentic-terminal:voice-settings";

function clampSpeed(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_VOICE_SETTINGS.speed;
  return Math.min(MAX_SPEED, Math.max(MIN_SPEED, value));
}

export function loadVoiceSettings(): VoiceSettings {
  if (typeof window === "undefined") return { ...DEFAULT_VOICE_SETTINGS };
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_VOICE_SETTINGS };
    const parsed = JSON.parse(raw) as Partial<VoiceSettings>;
    const voice = VOICE_OPTIONS.some((v) => v.id === parsed.voice)
      ? (parsed.voice as string)
      : DEFAULT_VOICE_SETTINGS.voice;
    const speed =
      typeof parsed.speed === "number" ? clampSpeed(parsed.speed) : DEFAULT_VOICE_SETTINGS.speed;
    return { voice, speed };
  } catch {
    return { ...DEFAULT_VOICE_SETTINGS };
  }
}

export function saveVoiceSettings(settings: VoiceSettings): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* storage unavailable — preferences just won't persist */
  }
}
