import type { Icon } from "~/lib/icons/icon-type";

/*
 * The kind of action a step is about, read from its text so it works on every recipe, old or new.
 * Heuristic, English and French: the earliest action word in the step wins ("Preheat the oven, then chop the
 * onions" → preheat), a tie goes to the longer phrase ("cook in the oven" → bake, not cook). Words that are
 * also nouns only count in a verb position ("the rest of the butter", "brown sugar", "a stock cube" don't).
 * English matches the imperative only, so "the chopped onions" is not a cutting step.
 */
export type StepActionKey
  = | "preheat"
    | "cut"
    | "peel"
    | "grate"
    | "whisk"
    | "mix"
    | "knead"
    | "blend"
    | "boil"
    | "simmer"
    | "steam"
    | "saute"
    | "fry"
    | "roast"
    | "bake"
    | "grill"
    | "microwave"
    | "heat"
    | "cook"
    | "chill"
    | "cool"
    | "marinate"
    | "rest"
    | "season"
    | "drain"
    | "rinse"
    | "serve";

export interface StepAction {
  key: StepActionKey;
  icon: keyof Icon;
}

// French verbs come as the infinitive or the imperative ("émincer" / "émincez").
const fr = (stem: string) => `${stem}(?:er|ez)`;
// Object words that put an English noun-verb in a verb position.
const OBJ = String.raw`(?:the|it|them|all|both|everything|in|until|together|well|with|to|on|for|up|through|over)\b`;

// Each rule lists English imperatives, then French infinitives/imperatives.
const RULES: { key: StepActionKey; icon: keyof Icon; en: string[]; fr: string[] }[] = [
  { key: "preheat", icon: "thermometer", en: ["pre-?heat", String.raw`(?:heat|turn\s+on)\s+the\s+oven`], fr: ["pr[ée]chauff(?:er|ez)"] },
  {
    key: "cut",
    icon: "knife",
    en: ["chop", "dice", "slice", "mince", "cut", "halve", "julienne", "trim", "carve", "shred", String.raw`(?:quarter|cube)\s+${OBJ}`],
    fr: [fr("coup"), fr("[ée]minc"), fr("hach"), fr("tranch"), fr("cisel"), fr("taill")],
  },
  { key: "peel", icon: "knife", en: ["peel"], fr: [fr("[ée]pluch"), fr("p[eè]l")] },
  { key: "grate", icon: "knife", en: ["grate", String.raw`zest\s+${OBJ}`], fr: [fr("r[âa]p"), fr("zest")] },
  {
    key: "whisk",
    icon: "bowlMixOutline",
    en: [String.raw`(?:whisk|beat)\s+(?:${OBJ}|eggs?|egg whites|cream)`],
    fr: [fr("fouett"), "batt(?:re|ez)", "montez"],
  },
  {
    key: "mix",
    icon: "bowlMixOutline",
    en: ["mix", "stir", "combine", "toss", String.raw`fold\s+${OBJ}`],
    fr: [fr("m[ée]lang"), fr("remu"), fr("incorpor")],
  },
  { key: "knead", icon: "knead", en: ["knead"], fr: ["p[ée]tri(?:r|ssez)"] },
  { key: "blend", icon: "blender", en: ["blend", "pur[ée]e", "pulse", String.raw`process\s+${OBJ}`], fr: [fr("mix"), fr("blend")] },
  {
    key: "boil",
    icon: "potSteam",
    en: ["boil", "blanch", String.raw`bring\s+(?:\S+\s+){0,8}?to\s+(?:the\s+|a\s+)?boil`],
    fr: [String.raw`(?:(?:faire|faites)\s+)?bouillir`, String.raw`port(?:er|ez)\s+(?:\S+\s+){0,4}?[àa]\s+[ée]bullition`, "blanchi(?:r|ssez)"],
  },
  { key: "simmer", icon: "potSteam", en: ["simmer", "poach"], fr: [fr("mijot"), fr("poch")] },
  {
    key: "steam",
    icon: "potSteam",
    en: [String.raw`steam\s+${OBJ}`],
    fr: [String.raw`(?:(?:faire|faites)\s+)?cui(?:re|sez)\s+(?:\S+\s+){0,3}?[àa]\s+la\s+vapeur`],
  },
  { key: "saute", icon: "pan", en: ["saut[ée]", "sweat"], fr: [String.raw`(?:(?:faire|faites)\s+)?(?:revenir|suer)`] },
  {
    key: "fry",
    icon: "pan",
    en: ["(?:stir|pan|deep)-?fry", "fry", "sear", String.raw`brown\s+${OBJ}`],
    fr: [fr("po[êe]l"), "saisi(?:r|ssez)", String.raw`(?:(?:faire|faites)\s+)?frire`, fr("dor")],
  },
  { key: "roast", icon: "oven", en: ["roast"], fr: ["r[ôo]ti(?:r|ssez)"] },
  {
    key: "bake",
    icon: "oven",
    en: ["bake", String.raw`cook\s+(?:\S+\s+){0,3}?in\s+the\s+oven`],
    fr: [fr("enfourn"), String.raw`(?:(?:faire|faites)\s+)?cui(?:re|sez)\s+(?:\S+\s+){0,3}?au\s+four`],
  },
  { key: "grill", icon: "grill", en: ["grill", "broil", "barbecue"], fr: [fr("grill"), fr("gratin")] },
  { key: "microwave", icon: "microwave", en: ["microwave"], fr: [String.raw`(?:\S+\s+){0,4}?au\s+micro-?ondes?`] },
  { key: "heat", icon: "stove", en: [String.raw`(?:heat|warm)\s+(?:${OBJ}|a|some|oil|butter|olive)`], fr: [fr("chauff")] },
  { key: "cook", icon: "stove", en: ["cook"], fr: [String.raw`(?:(?:faire|faites)\s+)?cuire`, "cuisez"] },
  { key: "chill", icon: "snowflake", en: ["chill", "refrigerate", "freeze"], fr: [fr("r[ée]frig[ée]r"), fr("cong[ée]l")] },
  {
    key: "cool",
    icon: "snowflake",
    en: [String.raw`(?:let|leave)\s+(?:\S+\s+){0,3}?(?:to\s+)?cool`, String.raw`cool\s+(?:completely|slightly|down|for|until|the|it|them)\b`],
    fr: [String.raw`(?:laiss(?:er|ez)\s+)?refroidi(?:r|ssez)`],
  },
  { key: "marinate", icon: "clockOutline", en: ["marinate"], fr: [fr("marin")] },
  {
    key: "rest",
    icon: "clockOutline",
    en: [String.raw`(?:let|leave)\s+(?:\S+\s+){0,3}?(?:to\s+)?(?:rest|stand|sit|rise|prove)`, "rest", "prove"],
    fr: [String.raw`(?:laiss(?:er|ez)\s+)?(?:reposer|lever|gonfler|pousser)`],
  },
  {
    key: "season",
    icon: "shaker",
    en: [String.raw`season\s+(?:${OBJ}|generously|lightly|to taste)`],
    fr: [fr("assaisonn"), String.raw`sal(?:er|ez)\s+et\s+poivr(?:er|ez)`, fr("poivr")],
  },
  { key: "drain", icon: "water", en: ["drain", "strain"], fr: [fr("[ée]goutt")] },
  { key: "rinse", icon: "water", en: ["rinse", "wash"], fr: [fr("rinc"), fr("lav")] },
  {
    key: "serve",
    icon: "silverwareForkKnife",
    en: ["serve", "garnish", String.raw`plate\s+(?:up|the|it|them)\b`],
    fr: ["servi(?:r|ez)", fr("dress"), "garni(?:r|ssez)"],
  },
];

// An English verb only counts where a clause starts: the beginning, after punctuation, after a linking word
// ("then", "and", "meanwhile") or an adverb ("finely", "gently"). That keeps "orange peel", "a slice of
// cheese" and "over medium heat" out. French infinitives and imperatives are distinct forms, so they need no
// such guard.
const CLAUSE_START = String.raw`(?<=(?:^|[.,;:!?()\-–—*_#>]|(?<!\p{L})(?:then|and|or|to|now|meanwhile|first|next|finally|also|\p{L}+ly))\s*)`;

// Whole words only, accents included (\b is ASCII-only).
const COMPILED = RULES.map(rule => ({
  ...rule,
  pattern: new RegExp(
    String.raw`(?<!\p{L})(?:${CLAUSE_START}(?:${rule.en.join("|")})|(?:${rule.fr.join("|")}))(?!\p{L})`,
    "iu",
  ),
}));

/** The action a step is about, or null when its text names none. */
export function stepAction(text: string | null | undefined): StepAction | null {
  if (!text) {
    return null;
  }
  const normalised = text.normalize("NFC");
  let best: { rule: (typeof COMPILED)[number]; index: number; length: number } | null = null;
  for (const rule of COMPILED) {
    const match = rule.pattern.exec(normalised);
    if (!match) {
      continue;
    }
    if (!best || match.index < best.index || (match.index === best.index && match[0].length > best.length)) {
      best = { rule, index: match.index, length: match[0].length };
    }
  }
  return best ? { key: best.rule.key, icon: best.rule.icon } : null;
}
