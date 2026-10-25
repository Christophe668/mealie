import type { Diet, MealPreferencesOut, MealPreferencesUpdate, MemberProfileOut } from "~/lib/api/types/household";

export const DIETS: Diet[] = ["none", "vegetarian", "vegan", "pescatarian", "halal", "kosher", "other"];

/** The four chip lists of a member, in display order. */
export const MEMBER_LISTS = ["allergies", "exclusions", "dislikes", "likes"] as const;
export type MemberList = (typeof MEMBER_LISTS)[number];

/** Same limits as the API: each entry at most 60 characters, at most 30 entries. */
export const MAX_CHIP_LENGTH = 60;
export const MAX_CHIPS = 30;
export const MAX_NAME_LENGTH = 60;
export const MAX_NOTES_LENGTH = 500;

/** The max time choices; null is "No limit". */
export const MAX_MINUTES_CHOICES = [15, 20, 30, 45, 60, 90];

/**
 * The form two entries are compared in, close to the server's `casefold()` for the common cases: NFC, lower
 * case, and "ß" as "ss" ("Straße" and "STRASSE" are the same entry).
 */
export function chipKey(value: string): string {
  return value.normalize("NFC").toLocaleLowerCase().replace(/ß/g, "ss");
}

/**
 * The first `max` characters of `value`, counted in code points as the server's `len` counts them, so an emoji at the
 * boundary is kept or dropped whole, never split into half a surrogate pair the server cannot store.
 */
export function cutToLength(value: string, max: number): string {
  const chars = Array.from(value);
  return chars.length > max ? chars.slice(0, max).join("") : value;
}

export interface AddChipsResult {
  chips: string[];
  /** Entries left out because the list is full; the field keeps them so nothing typed is lost. */
  rest: string[];
  /** An entry was cut to 60 characters. */
  cut: boolean;
}

/**
 * Adds what was typed (one entry, or several separated by commas) to `chips`: trimmed, empty entries dropped,
 * duplicates dropped keeping the first spelling, each entry cut to 60 characters, 30 entries at most.
 */
export function addChips(chips: string[], text: string): AddChipsResult {
  const result = [...chips];
  const rest: string[] = [];
  let cut = false;
  const seen = new Set(result.map(chipKey));
  for (const part of text.split(",")) {
    const trimmed = part.trim();
    const value = cutToLength(trimmed, MAX_CHIP_LENGTH).trim();
    if (!value || seen.has(chipKey(value))) {
      continue;
    }
    if (result.length >= MAX_CHIPS) {
      rest.push(trimmed);
      continue;
    }
    cut ||= value.length < trimmed.length;
    seen.add(chipKey(value));
    result.push(value);
  }
  return { chips: result, rest, cut };
}

/** What a member card edits. */
export interface MemberDraft {
  name: string;
  userId: string | null;
  isChild: boolean;
  diet: Diet;
  allergies: string[];
  exclusions: string[];
  dislikes: string[];
  likes: string[];
  notes: string;
}

export function memberDraft(member: Partial<MemberProfileOut> = {}): MemberDraft {
  return {
    name: member.name ?? "",
    userId: member.userId ?? null,
    isChild: member.isChild ?? false,
    diet: member.diet ?? "none",
    allergies: [...(member.allergies ?? [])],
    exclusions: [...(member.exclusions ?? [])],
    dislikes: [...(member.dislikes ?? [])],
    likes: [...(member.likes ?? [])],
    notes: member.notes ?? "",
  };
}

/** The draft as the API expects it: trimmed name, empty notes as null. */
export function memberPayload(draft: MemberDraft) {
  return { ...draft, name: draft.name.trim(), notes: draft.notes.trim() || null };
}

/** What the habits card edits. */
export interface HabitsDraft {
  defaultServings: number | null;
  quickWeekdays: number[];
  weeknightMaxMinutes: number | null;
  weekendMaxMinutes: number | null;
  favouriteCuisines: string[];
  notes: string;
}

export function habitsDraft(preferences: MealPreferencesOut | null | undefined): HabitsDraft {
  return {
    defaultServings: preferences?.defaultServings ?? null,
    quickWeekdays: [...(preferences?.quickWeekdays ?? [])].sort((a, b) => a - b),
    weeknightMaxMinutes: preferences?.weeknightMaxMinutes ?? null,
    weekendMaxMinutes: preferences?.weekendMaxMinutes ?? null,
    favouriteCuisines: [...(preferences?.favouriteCuisines ?? [])],
    notes: preferences?.notes ?? "",
  };
}

/** The habits as the API expects them: empty notes as null. */
export function habitsPayload(draft: HabitsDraft) {
  return { ...draft, notes: draft.notes.trim() || null } satisfies MealPreferencesUpdate;
}

/**
 * The seven days as the API numbers them (0 = Monday … 6 = Sunday), starting on the household's first day of
 * the week, which Mealie numbers 0 = Sunday … 6 = Saturday.
 */
export function weekdayOrder(firstDayOfWeek: number): number[] {
  const first = ((firstDayOfWeek % 7) + 7) % 7;
  return Array.from({ length: 7 }, (_, i) => ((first + i) % 7 + 6) % 7);
}
