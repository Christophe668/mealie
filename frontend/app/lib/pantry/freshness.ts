import { differenceInCalendarDays, parseISO } from "date-fns";
import { relativeAgo } from "~/composables/use-today";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";

/** The order the pantry page shows its groups in, coldest first. */
export const PANTRY_LOCATIONS: readonly PantryLocation[] = ["fridge", "freezer", "cupboard", "other"];

/** The server's default when an item has no location. */
export const DEFAULT_PANTRY_LOCATION: PantryLocation = "cupboard";

/** A use-by date this many days away (or nearer, or past) is urgent. */
export const USE_BY_URGENT_DAYS = 2;

export interface PantryGroupData {
  location: PantryLocation;
  items: PantryItemOut[];
}

export interface FreshnessLine {
  text: string;
  /** Use soon: the one place the pantry spends its accent. */
  urgent: boolean;
}

type Translate = (key: string, params?: Record<string, unknown>) => string;

/**
 * The single most useful freshness fact about an item, in this order: its use-by date (urgent when
 * at most two days away or already past), else when it was opened, else when it was bought. Null when
 * the item carries no dates.
 */
export function freshnessLine(item: PantryItemOut, today: Date, t: Translate, locale = "en-US"): FreshnessLine | null {
  if (item.useBy) {
    const date = parseISO(item.useBy);
    const dateText = date.toLocaleDateString(locale, { day: "numeric", month: "long" });
    return {
      text: t("pantry.use-by", { date: dateText }),
      urgent: differenceInCalendarDays(date, today) <= USE_BY_URGENT_DAYS,
    };
  }
  if (item.openedOn) {
    return { text: t("pantry.opened-ago", { when: relativeAgo(item.openedOn, today, locale) }), urgent: false };
  }
  if (item.boughtOn) {
    return { text: t("pantry.bought-ago", { when: relativeAgo(item.boughtOn, today, locale) }), urgent: false };
  }
  return null;
}

/** Items by location in the fixed order; locations without items are left out. Item order is kept. */
export function groupByLocation(items: PantryItemOut[]): PantryGroupData[] {
  return PANTRY_LOCATIONS
    .map(location => ({ location, items: items.filter(item => (item.location ?? DEFAULT_PANTRY_LOCATION) === location) }))
    .filter(group => group.items.length > 0);
}
