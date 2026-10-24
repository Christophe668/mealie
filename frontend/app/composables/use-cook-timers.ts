import { findStepTimers } from "~/lib/recipe/step-timers";

export interface CookTimer {
  id: string;
  /** What the step said, e.g. "10 minutes". */
  label: string;
  /** Seconds. */
  total: number;
  /** Seconds left, rounded up so "00:00" only shows once the time is really up. */
  remaining: number;
  running: boolean;
  done: boolean;
}

export type CookTimerSpec = Pick<CookTimer, "id" | "label" | "total">;

/** Durations in a step's text, in seconds; the step-timer parser is the single source. */
export function parseDurations(text: string | null | undefined): number[] {
  return findStepTimers(text).map(timer => timer.seconds);
}

const TICK_MS = 250;

/*
 * The alarm: a short beep through one AudioContext, made on the first start (a user gesture, so
 * browsers let it play later), and a vibration where the device has one.
 */
let audio: AudioContext | null = null;

function unlockAudio() {
  if (audio || typeof window === "undefined") {
    return;
  }
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) {
    return;
  }
  try {
    audio = new Ctor();
  }
  catch {
    audio = null;
  }
}

function ring() {
  if (audio) {
    try {
      void audio.resume();
      const now = audio.currentTime;
      // Three short pips at 880 Hz.
      for (let i = 0; i < 3; i++) {
        const osc = audio.createOscillator();
        const gain = audio.createGain();
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.0001, now + i * 0.3);
        gain.gain.exponentialRampToValueAtTime(0.3, now + i * 0.3 + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.3 + 0.2);
        osc.connect(gain).connect(audio.destination);
        osc.start(now + i * 0.3);
        osc.stop(now + i * 0.3 + 0.22);
      }
    }
    catch {
      // No sound is better than a broken cook mode.
    }
  }
  if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
    navigator.vibrate([200, 100, 200]);
  }
}

/**
 * Cook-mode countdowns. Each running timer keeps its end time on the wall clock, so a throttled or
 * backgrounded tab is right again on the next tick. One interval serves every timer and stops when none
 * runs; leaving the scope (cook mode) clears them all.
 */
export function useCookTimers(options: { onDone?: (timer: CookTimer) => void } = {}) {
  const timers = ref<CookTimer[]>([]);
  const endsAt = new Map<string, number>();
  let interval: ReturnType<typeof setInterval> | null = null;

  const find = (id: string) => timers.value.find(timer => timer.id === id);

  function tick() {
    const now = Date.now();
    for (const timer of timers.value) {
      const end = endsAt.get(timer.id);
      if (!timer.running || end === undefined) {
        continue;
      }
      const left = Math.max(0, Math.ceil((end - now) / 1000));
      timer.remaining = left;
      if (left === 0) {
        timer.running = false;
        timer.done = true;
        endsAt.delete(timer.id);
        ring();
        options.onDone?.({ ...timer });
      }
    }
    syncInterval();
  }

  function syncInterval() {
    const anyRunning = timers.value.some(timer => timer.running);
    if (anyRunning && !interval) {
      interval = setInterval(tick, TICK_MS);
    }
    else if (!anyRunning && interval) {
      clearInterval(interval);
      interval = null;
    }
  }

  /** Starts a new timer, resumes a paused one, or runs a finished one again from the top. */
  function start(spec: CookTimerSpec) {
    unlockAudio();
    let timer = find(spec.id);
    if (!timer) {
      timers.value.push({ ...spec, remaining: spec.total, running: false, done: false });
      timer = find(spec.id)!;
    }
    if (timer.done) {
      timer.remaining = timer.total;
      timer.done = false;
    }
    if (!timer.running) {
      timer.running = true;
      endsAt.set(timer.id, Date.now() + timer.remaining * 1000);
    }
    syncInterval();
  }

  function pause(id: string) {
    const timer = find(id);
    if (!timer?.running) {
      return;
    }
    const end = endsAt.get(id) ?? Date.now();
    timer.remaining = Math.max(0, Math.ceil((end - Date.now()) / 1000));
    timer.running = false;
    endsAt.delete(id);
    syncInterval();
  }

  /** Space and the step's timer buttons: start, pause, resume or restart as fits. */
  function toggle(spec: CookTimerSpec) {
    if (find(spec.id)?.running) {
      pause(spec.id);
    }
    else {
      start(spec);
    }
  }

  function reset(id: string) {
    const timer = find(id);
    if (!timer) {
      return;
    }
    timer.remaining = timer.total;
    timer.running = false;
    timer.done = false;
    endsAt.delete(id);
    syncInterval();
  }

  function dismiss(id: string) {
    timers.value = timers.value.filter(timer => timer.id !== id);
    endsAt.delete(id);
    syncInterval();
  }

  function clear() {
    timers.value = [];
    endsAt.clear();
    syncInterval();
  }

  onScopeDispose(clear);

  return { timers: readonly(timers), start, pause, toggle, reset, dismiss, clear };
}
