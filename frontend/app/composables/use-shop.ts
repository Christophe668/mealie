import { relativeAgo } from "~/composables/use-today";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";
import type { MultiPurposeLabelSummary } from "~/lib/api/types/labels";

/** One aisle of the shop screen: a label (null = unlabelled) and its items. */
export interface ShopAisleGroup {
  label: MultiPurposeLabelSummary | null;
  items: ShoppingListItemOut[];
}

/**
 * Maps the upstream composable's `itemsByLabel` (keyed by label name, unlabelled under the translated
 * "No label") onto label objects, so the screen does not depend on that name or its translation.
 */
export function toByLabel(itemsByLabel: Record<string, ShoppingListItemOut[]>, list: ShoppingListOut | null): ShopAisleGroup[] {
  const byName = new Map<string, MultiPurposeLabelSummary>();
  list?.labelSettings?.forEach(setting => byName.set(setting.label.name, setting.label));

  return Object.values(itemsByLabel).map((items) => {
    const first = items.find(item => item.labelId && item.label);
    const label = first?.label ? (byName.get(first.label.name) ?? first.label) : null;
    return { label, items };
  });
}

/**
 * Aisles in the list's own label order, unlabelled last; labels the list does not order (a label created
 * after the list) sit between the two. Only open items count, and an aisle with nothing open is dropped.
 */
export function shopAisles(list: ShoppingListOut, byLabel: ShopAisleGroup[]): ShopAisleGroup[] {
  const order = new Map<string, number>();
  [...(list.labelSettings ?? [])]
    .sort((a, b) => (a.position ?? 0) - (b.position ?? 0))
    .forEach((setting, index) => order.set(setting.labelId, index));

  const rank = (group: ShopAisleGroup) => {
    if (!group.label) {
      return Number.MAX_SAFE_INTEGER;
    }
    return order.get(group.label.id) ?? Number.MAX_SAFE_INTEGER - 1;
  };

  return byLabel
    .map(group => ({ label: group.label, items: group.items.filter(item => !item.checked) }))
    .filter(group => group.items.length > 0)
    .map((group, index) => ({ group, index }))
    .sort((a, b) => rank(a.group) - rank(b.group) || a.index - b.index)
    .map(({ group }) => group);
}

/** Bought items, most recently ticked first (the order upstream's checked section uses). */
export function shopBought(list: ShoppingListOut): ShoppingListItemOut[] {
  return (list.listItems ?? [])
    .filter(item => item.checked)
    .sort((a, b) => (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""));
}

export function openCount(list: ShoppingListOut | null): number {
  return list?.listItems?.filter(item => !item.checked).length ?? 0;
}

/** "now", "25 minutes ago", "2 hours ago", then the day-based phrasing Home uses ("yesterday", "2 weeks ago"). */
export function updatedAgo(iso: string, now: Date, locale: string): string {
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (seconds < 60) {
    return rtf.format(0, "second");
  }
  if (seconds < 3600) {
    return rtf.format(-Math.floor(seconds / 60), "minute");
  }
  if (seconds < 86400) {
    return rtf.format(-Math.floor(seconds / 3600), "hour");
  }
  return relativeAgo(iso, now, locale);
}
