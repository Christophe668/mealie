export interface StepTimer {
  /** The words as written in the step, e.g. "10 minutes". */
  text: string;
  seconds: number;
}

// Accepts the brief's forms (min, minutes, h, hours) plus the common variants recipes use: "1 hour", "5 mins", "2 hrs".
const TIMER_PATTERN = /\b(\d+)\s*(min(?:ute)?s?|h(?:(?:ou)?rs?)?)\b/gi;

/** Durations mentioned in a step's text, in order. Cook mode turns these into live timers. */
export function findStepTimers(text: string | null | undefined): StepTimer[] {
  if (!text) {
    return [];
  }
  return Array.from(text.matchAll(TIMER_PATTERN), (match) => {
    const amount = Number(match[1]);
    const unit = match[2]!.toLowerCase();
    return {
      text: match[0],
      seconds: unit.startsWith("h") ? amount * 3600 : amount * 60,
    };
  }).filter(timer => timer.seconds > 0);
}
