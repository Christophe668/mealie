/*
 * Thermomix settings written in a step, Cookomix style: "Cuire 15 min / 100°C / ⟲ / vitesse 1 sans le gobelet."
 * A program is a run of settings joined by "/", "," or " - ": a time, a temperature (or Varoma), reverse,
 * and a speed ("vitesse 1", "vitesse 3-5", "vitesse mijotage", "speed 2"), Turbo or the dough mode. A run
 * only counts when it has a speed, Turbo or the dough mode, so "préchauffer le four à 180°C" or
 * "réserver 4 h" stay ordinary steps. English and French; Markdown bold around settings is ignored.
 */

export interface ThermomixProgram {
  /** The time as written, e.g. "5 min 30 sec"; null when the program has none. */
  time: string | null;
  /** "100°C", "Varoma", or null. */
  temperature: string | null;
  /** "1", "3–5", "spoon" (mijotage / soft), or null for Turbo and the dough mode. */
  speed: string | null;
  reverse: boolean;
  turbo: boolean;
  dough: boolean;
}

export interface ThermomixStep {
  programs: ThermomixProgram[];
  /** The step without its settings: "Cuire sans le gobelet." */
  text: string;
}

const NUM = String.raw`\d+(?:[.,]\d+)?`;
const TIME = String.raw`(?:${NUM}\s*(?:h|heures?|hours?|hrs?)\b\s*)?(?:${NUM}\s*min(?:utes?)?\b\s*)?(?:${NUM}\s*(?:sec(?:ondes?|onds?)?|s)\b)?`;
const TEMP = String.raw`\d{2,3}\s*°\s*C?|varoma`;
const REVERSE = String.raw`sens\s+inverse|reverse|⟲|↺|counter-?clockwise`;
const SPEED_VALUE = String.raw`mijotage|soft|spoon|🥄|${NUM}(?:\s*(?:[-–]|à|to)\s*${NUM})?`;
const SPEED = String.raw`(?:vitesse|speed|vit\.)\s*(?:${SPEED_VALUE})`;
const TURBO = String.raw`turbo`;
const DOUGH = String.raw`(?:mode\s+)?p[ée]trin|dough\s+mode|knead(?:ing)?\s+mode`;

const TOKEN = String.raw`(?:${SPEED}|${TURBO}|${DOUGH}|${REVERSE}|${TEMP}|(?=\d)${TIME})`;
const SEP = String.raw`\s*(?:\/+|,|\s[-–]\s)\s*`;
// Whole words: a token never starts or ends inside a word.
const GROUP = new RegExp(String.raw`(?<![\p{L}\d])${TOKEN}(?:${SEP}${TOKEN})*(?![\p{L}\d])`, "giu");

const IS = {
  speed: new RegExp(String.raw`^(?:${SPEED})$`, "iu"),
  turbo: new RegExp(String.raw`^(?:${TURBO})$`, "iu"),
  dough: new RegExp(String.raw`^(?:${DOUGH})$`, "iu"),
  reverse: new RegExp(String.raw`^(?:${REVERSE})$`, "iu"),
  temp: new RegExp(String.raw`^(?:${TEMP})$`, "iu"),
  time: new RegExp(String.raw`^(?:${TIME})$`, "iu"),
};

function speedValue(token: string): string {
  const value = token.replace(/^(?:vitesse|speed|vit\.)\s*/iu, "").trim();
  if (/^(?:mijotage|soft|spoon|🥄)$/iu.test(value)) {
    return "spoon";
  }
  return value.replace(/\s*(?:[-–]|à|to)\s*/u, "–");
}

function program(run: string): ThermomixProgram | null {
  const result: ThermomixProgram = { time: null, temperature: null, speed: null, reverse: false, turbo: false, dough: false };
  for (const raw of run.split(new RegExp(SEP, "u"))) {
    const token = raw.trim();
    if (!token) {
      continue;
    }
    if (IS.speed.test(token)) {
      result.speed = speedValue(token);
    }
    else if (IS.turbo.test(token)) {
      result.turbo = true;
    }
    else if (IS.dough.test(token)) {
      result.dough = true;
    }
    else if (IS.reverse.test(token)) {
      result.reverse = true;
    }
    else if (IS.temp.test(token)) {
      result.temperature = /varoma/iu.test(token) ? "Varoma" : `${token.match(/\d+/u)![0]}°C`;
    }
    else if (IS.time.test(token)) {
      result.time = token.replace(/\s+/gu, " ");
    }
    else {
      // Not something we can read with confidence: leave the step as written.
      return null;
    }
  }
  return result.speed !== null || result.turbo || result.dough ? result : null;
}

/** Tidies the text once the settings are taken out: no doubled spaces, no space before punctuation. */
function tidy(text: string): string {
  return text
    .replace(/[ \t]{2,}/gu, " ")
    .replace(/ +([.,;:!?)])/gu, "$1")
    .replace(/([(]) +/gu, "$1")
    .replace(/,\s*([.;!?])/gu, "$1")
    .replace(/^\s*[,.;]\s*/u, "")
    .trim();
}

/** The Thermomix programs in a step and the step's text without them, or null for an ordinary step. */
export function parseThermomix(text: string | null | undefined): ThermomixStep | null {
  if (!text) {
    return null;
  }
  const plain = text.replace(/\*\*|__/gu, "");
  const programs: ThermomixProgram[] = [];
  const cleaned = plain.replace(GROUP, (run) => {
    const parsed = program(run);
    if (!parsed) {
      return run;
    }
    programs.push(parsed);
    return "";
  });
  return programs.length ? { programs, text: tidy(cleaned) } : null;
}
