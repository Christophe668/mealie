import { addDays, differenceInCalendarDays, parseISO } from "date-fns";
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

/**
 * How an item is doing, worst first: past it, worth checking, use soon, fine, or no way to tell.
 * From the item's use-by date when it has one, else estimated from when it was opened or bought and how
 * long that food typically keeps (the server's `shelfLife`).
 */
export type FreshnessStatus = "past" | "check" | "soon" | "ok" | "unknown";

export const FRESHNESS_RANK: Record<FreshnessStatus, number> = { past: 0, check: 1, soon: 2, ok: 3, unknown: 4 };

export interface Freshness {
  status: FreshnessStatus;
  /** Days until the use-by date (or the estimated one); negative once past. Null when unknown. */
  daysLeft: number | null;
  /** True when the date is estimated from the keeping time, false for the item's own use-by date. */
  estimated: boolean;
  /** The typical keeping time the estimate used, in days. */
  keepsDays: number | null;
}

/** Statuses that ask for attention: "Use first" cards, the "To check" filter, the coloured row line. */
export const NEEDS_ATTENTION: readonly FreshnessStatus[] = ["past", "check", "soon"];

function statusFrom(daysLeft: number, keepsDays: number | null): FreshnessStatus {
  if (keepsDays === null) {
    // A real use-by date: past means past.
    return daysLeft < 0 ? "past" : daysLeft <= USE_BY_URGENT_DAYS ? "soon" : "ok";
  }
  // An estimate: only "probably past" once well beyond it (half its keeping time, two days at least);
  // just beyond it is worth a look. Short-lived foods are "use soon" from halfway.
  if (daysLeft <= -Math.max(2, Math.ceil(keepsDays / 2))) {
    return "past";
  }
  if (daysLeft < 0) {
    return "check";
  }
  return daysLeft <= Math.min(USE_BY_URGENT_DAYS, Math.floor(keepsDays / 2)) ? "soon" : "ok";
}

export function freshnessOf(item: PantryItemOut, today: Date): Freshness {
  if (item.useBy) {
    const daysLeft = differenceInCalendarDays(parseISO(item.useBy), today);
    return { status: statusFrom(daysLeft, null), daysLeft, estimated: false, keepsDays: null };
  }
  const life = item.shelfLife;
  const start = item.openedOn && life?.openedDays
    ? { date: item.openedOn, days: life.openedDays }
    : item.boughtOn && life?.unopenedDays
      ? { date: item.boughtOn, days: life.unopenedDays }
      : null;
  if (!start) {
    return { status: "unknown", daysLeft: null, estimated: false, keepsDays: null };
  }
  const daysLeft = differenceInCalendarDays(addDays(parseISO(start.date), start.days), today);
  return { status: statusFrom(daysLeft, start.days), daysLeft, estimated: true, keepsDays: start.days };
}

/** Worst first; the server's order ("use first") is kept between items of the same status. */
export function byFreshness(items: PantryItemOut[], today: Date): PantryItemOut[] {
  return items
    .map((item, index) => ({ item, index, rank: FRESHNESS_RANK[freshnessOf(item, today).status] }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(entry => entry.item);
}

export interface FreshnessLine {
  text: string;
  /** Needs attention (past, worth checking or use soon). */
  urgent: boolean;
  status: FreshnessStatus;
}

type Translate = (key: string, params?: Record<string, unknown>) => string;

/**
 * The single most useful freshness fact about an item, in this order: its use-by date, else when it was
 * opened, else when it was bought, with its status (urgent when it needs attention). Null when the item
 * carries no dates.
 */
export function freshnessLine(item: PantryItemOut, today: Date, t: Translate, locale = "en-US"): FreshnessLine | null {
  const { status } = freshnessOf(item, today);
  const urgent = NEEDS_ATTENTION.includes(status);
  if (item.useBy) {
    const dateText = parseISO(item.useBy).toLocaleDateString(locale, { day: "numeric", month: "long" });
    return { text: t("pantry.use-by", { date: dateText }), urgent, status };
  }
  if (item.openedOn) {
    return { text: t("pantry.opened-ago", { when: relativeAgo(item.openedOn, today, locale) }), urgent, status };
  }
  if (item.boughtOn) {
    return { text: t("pantry.bought-ago", { when: relativeAgo(item.boughtOn, today, locale) }), urgent, status };
  }
  return null;
}

/** Items by location in the fixed order; locations without items are left out. Item order is kept. */
export function groupByLocation(items: PantryItemOut[]): PantryGroupData[] {
  return PANTRY_LOCATIONS
    .map(location => ({ location, items: items.filter(item => (item.location ?? DEFAULT_PANTRY_LOCATION) === location) }))
    .filter(group => group.items.length > 0);
}
