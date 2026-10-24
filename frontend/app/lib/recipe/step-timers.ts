export interface StepTimer {
  /** The words as written in the step, e.g. "10 minutes" or "2–3 minutes". */
  text: string;
  /** Whole minutes, rounded; for a range ("2–3 minutes") the upper bound, so a timer never rings early. */
  minutes: number;
  seconds: number;
}

// One amount: "1 1/2", "1/2", "1.5", "1,5" or "10".
const AMOUNT = String.raw`\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?`;
// Optional range ("2-3", "2–3", "2 to 3"), then the unit: min, mins, minute(s), h, hr(s), hour(s).
// The look-behind stops a match starting inside a number ("1.5" must not read as "5").
const TIMER_PATTERN = new RegExp(
  String.raw`(?<![\d.,/])(?:(${AMOUNT})\s*(?:[-–—]|to)\s*)?(${AMOUNT})\s*(min(?:ute)?s?|h(?:(?:ou)?rs?)?)\b`,
  "gi",
);

function parseAmount(raw: string): number {
  const [whole, fraction] = raw.includes("/") ? (raw.trim().includes(" ") ? raw.trim().split(/\s+/) : ["0", raw]) : [raw, ""];
  let value = Number(whole!.replace(",", "."));
  if (fraction) {
    const [num, den] = fraction.split("/").map(Number);
    value += den ? num! / den : 0;
  }
  return value;
}

/** Durations mentioned in a step's text, in order. Cook mode turns these into live timers. */
export function findStepTimers(text: string | null | undefined): StepTimer[] {
  if (!text) {
    return [];
  }
  return Array.from(text.matchAll(TIMER_PATTERN), (match) => {
    const amount = parseAmount(match[2]!);
    const unitSeconds = match[3]!.toLowerCase().startsWith("h") ? 3600 : 60;
    const seconds = Math.round(amount * unitSeconds);
    return { text: match[0], minutes: Math.round(seconds / 60), seconds };
  }).filter(timer => timer.seconds > 0);
}
