import { DEFAULT_PANTRY_LOCATION, freshnessLine } from "./freshness";
import type { PantryItemOut } from "~/lib/api/types/household";

export type IngredientStatus = "have" | "soon" | "missing";

type Translate = (key: string, params?: Record<string, unknown>) => string;

/**
 * Whether the household has an ingredient: missing without pantry items, use soon when an item is
 * urgent, else have. Null when `items` is undefined (the ingredient names no food, or the pantry is unknown).
 */
export function ingredientStatus(items: PantryItemOut[] | undefined, today: Date): IngredientStatus | null {
  if (!items) {
    return null;
  }
  if (!items.length) {
    return "missing";
  }
  const urgent = items.some(item => freshnessLine(item, today, key => key)?.urgent);
  return urgent ? "soon" : "have";
}

/** "Fridge, Freezer · Use by October 25": the places, then the freshness of the item to use first. */
export function pantryDetail(items: PantryItemOut[], today: Date, t: Translate, locale: string): string {
  const places = [...new Set(items.map(item => item.location ?? DEFAULT_PANTRY_LOCATION))]
    .map(location => t(`pantry.location.${location}`));
  // Items with a use-by date, soonest first, then the rest in their order.
  const ranked = [...items].sort((a, b) => (a.useBy ?? "9999").localeCompare(b.useBy ?? "9999"));
  const fresh = ranked.map(item => freshnessLine(item, today, t, locale)).find(Boolean);
  return [places.join(", "), fresh?.text].filter(Boolean).join(" · ");
}
