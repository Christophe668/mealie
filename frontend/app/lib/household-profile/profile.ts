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
 * Adds what was typed (one entry, or several separated by commas) to `chips`: trimmed, empty entries dropped,
 * case-insensitive duplicates dropped keeping the first spelling, each entry cut to 60 characters, 30 at most.
 */
export function addChips(chips: string[], text: string): string[] {
  const result = [...chips];
  const seen = new Set(result.map(chip => chip.toLocaleLowerCase()));
  for (const part of text.split(",")) {
    const value = part.trim().slice(0, MAX_CHIP_LENGTH);
    const key = value.toLocaleLowerCase();
    if (!value || seen.has(key) || result.length >= MAX_CHIPS) {
      continue;
    }
    seen.add(key);
    result.push(value);
  }
  return result;
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

/** Only the fields that differ from `baseline`, so a save never overwrites what Claude changed meanwhile. */
export function changedFields<T extends object>(baseline: T, draft: T): Partial<T> {
  const changes: Partial<T> = {};
  for (const key of Object.keys(draft) as (keyof T)[]) {
    if (JSON.stringify(draft[key]) !== JSON.stringify(baseline[key])) {
      changes[key] = draft[key];
    }
  }
  return changes;
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

export function habitsPayload(draft: Partial<HabitsDraft>): MealPreferencesUpdate {
  return "notes" in draft ? { ...draft, notes: draft.notes?.trim() || null } : { ...draft };
}

/**
 * The seven days as the API numbers them (0 = Monday … 6 = Sunday), starting on the household's first day of
 * the week, which Mealie numbers 0 = Sunday … 6 = Saturday.
 */
export function weekdayOrder(firstDayOfWeek: number): number[] {
  const first = ((firstDayOfWeek % 7) + 7) % 7;
  return Array.from({ length: 7 }, (_, i) => ((first + i) % 7 + 6) % 7);
}
