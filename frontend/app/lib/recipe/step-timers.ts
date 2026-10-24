export interface StepTimer {
  /** The words as written in the step, e.g. "10 minutes" or "2–3 minutes". */
  text: string;
  /** Whole minutes, rounded; for a range ("2–3 minutes") the upper bound, so a timer never rings early. */
  minutes: number;
  seconds: number;
}

// One amount: "1 1/2", "1/2", "1.5", "1,5" or "10".
const AMOUNT = String.raw`\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?`;
// Optional range ("2-3", "2–3", "2 to 3", "2 à 3"), then the unit, in English or French:
// hours: h, hr(s), hour(s), heure(s); minutes: min, mins, minute(s); seconds: s, sec(s), second(s), seconde(s).
// Hours may carry minutes after them ("1 h 30", "1 hour 20 minutes", "1 heure 15"), but not a number that
// belongs to the next words ("1 h 30 g butter").
// The look-behind stops a match starting inside a number ("1.5" must not read as "5").
const MINUTE_UNIT = String.raw`min(?:ute)?s?\b`;
const HOUR_UNIT = String.raw`h(?:(?:ou)?rs?|eures?)?`;
const SECOND_UNIT = String.raw`s(?:ec(?:onde?)?s?)?\b`;
const EXTRA_MINUTES = String.raw`\s*(\d{1,2})(?:\s*${MINUTE_UNIT}|(?![\d/]|[.,]\d|\s*\p{L}))`;
const TIMER_PATTERN = new RegExp(
  String.raw`(?<![\d.,/])(?:(${AMOUNT})\s*(?:[-–—]|to|à)\s*)?(${AMOUNT})\s*(?:(${HOUR_UNIT})\b(?:${EXTRA_MINUTES})?|${MINUTE_UNIT}|(${SECOND_UNIT}))`,
  "giu",
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
    const unitSeconds = match[3] ? 3600 : match[5] ? 1 : 60;
    const seconds = Math.round(amount * unitSeconds + Number(match[4] ?? 0) * 60);
    return { text: match[0], minutes: Math.round(seconds / 60), seconds };
  }).filter(timer => timer.seconds > 0);
}
