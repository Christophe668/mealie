export interface StepTimer {
  /** The words as written in the step, e.g. "10 minutes" or "2–3 minutes". */
  text: string;
  /** Whole minutes, rounded; for a range ("2–3 minutes") the upper bound, so a timer never rings early. */
  minutes: number;
  seconds: number;
  /** Where the words start in the step text. */
  index: number;
  /** A short name for the timer taken from the step, e.g. "Fry the guanciale"; null when nothing usable precedes the duration. */
  name: string | null;
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
    const index = match.index ?? 0;
    return { text: match[0], minutes: Math.round(seconds / 60), seconds, index, name: timerName(text, index) };
  }).filter(timer => timer.seconds > 0);
}

/*
 * Naming a timer: the action the duration belongs to, read from the same sentence.
 * "Meanwhile fry the guanciale in a dry, wide pan over medium heat for 5 minutes until…" → "Fry the guanciale".
 * Heuristic, English and French: take the sentence around the duration, keep the clause the duration sits
 * in (or the one before it when the duration opens its own clause: "…, about 9 minutes"), cut that clause
 * before the duration and before "for/until/about/pendant/jusqu'à", drop opener words such as "Meanwhile",
 * then shorten long results by trimming trailing prepositional phrases.
 */
const CLAUSE_SPLIT = /\s*(?:;|:|\(|\)|\s(?:and|then|or|while|et|puis|ou)\s)\s*/iu;
const CUT_BEFORE = /\s(?:for|until|till|about|around|roughly|approximately|another|pendant|durant|jusqu['’]à|jusqu['’]a|environ|encore)(?:\s|$)/iu;
const OPENERS = /^(?:meanwhile|then|now|next|finally|first|afterwards|after that|in the meantime|pendant ce temps|ensuite|puis|enfin|d['’]abord|maintenant)\b[\s,]*/iu;
const LEAD_IN = /^(?:for|until|till|about|around|roughly|approximately|another|pendant|durant|environ|encore)\b\s*/iu;
const TRAILING_PHRASE = /\s(?:in|into|on|onto|over|under|with|at|to|out of|from|through|dans|sur|sous|avec|à|au|aux|en|vers|par)\s[^,]*$/iu;
const MAX_NAME = 24;

export function timerName(text: string, index: number): string | null {
  const before = text.slice(0, index);
  const sentenceStart = Math.max(before.lastIndexOf(". "), before.lastIndexOf("! "), before.lastIndexOf("? "), before.lastIndexOf("\n"));
  const sentence = before.slice(sentenceStart + 1);
  const clauses = sentence.split(CLAUSE_SPLIT).map(c => c.trim()).filter(Boolean);
  let clause = clauses.pop() ?? "";
  // A clause that is only a lead-in to the duration ("about", "for about") names nothing; use the one before.
  const bare = (c: string) => c.split(CUT_BEFORE)[0]!.replace(OPENERS, "").replace(LEAD_IN, "").trim();
  while (!bare(clause) && clauses.length) {
    clause = clauses.pop()!;
  }
  clause = clause.split(CUT_BEFORE)[0]!.replace(/[\s,.;:–-]+$/u, "").replace(OPENERS, "").replace(LEAD_IN, "").trim();
  const commaCut = clause.indexOf(",");
  if (commaCut > 0 && clause.length > MAX_NAME) {
    clause = clause.slice(0, commaCut);
  }
  while (clause.length > MAX_NAME && TRAILING_PHRASE.test(clause)) {
    clause = clause.replace(TRAILING_PHRASE, "");
  }
  if (clause.length > MAX_NAME + 12) {
    clause = clause.slice(0, MAX_NAME + 12).replace(/\s+\S*$/u, "");
  }
  clause = clause.replace(/[\s,.;:–-]+$/u, "");
  if (clause.length < 3 || !/\p{L}/u.test(clause)) {
    return null;
  }
  return clause.charAt(0).toUpperCase() + clause.slice(1);
}
