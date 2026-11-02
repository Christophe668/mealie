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

/** One item as a recipe group shows it: that recipe's share of it, and the other recipes it is also for. */
export interface ShopRecipeEntry {
  item: ShoppingListItemOut;
  /** The recipe's share when the item is for several recipes; undefined shows the item's own quantity. */
  quantity?: number;
  /** Names of the item's other recipes, in list order. */
  others: string[];
}

/** One recipe of the shop screen's recipe view (recipeId null = items for no recipe on the list). */
export interface ShopRecipeGroup {
  recipeId: string | null;
  name: string | null;
  entries: ShopRecipeEntry[];
}

/**
 * Open items by recipe, in the list's recipe order, then the items for no recipe. An item for several
 * recipes is in each of their groups with that recipe's share, so each group reads as what that dish needs;
 * it stays one item, so ticking it in one group ticks it everywhere. A recipe with nothing open is dropped.
 */
export function shopRecipes(list: ShoppingListOut, recipeNames: Map<string, string>): ShopRecipeGroup[] {
  const order = [...new Set((list.recipeReferences ?? []).map(ref => ref.recipeId))].filter(id => recipeNames.has(id));
  const groups = new Map<string, ShopRecipeEntry[]>(order.map(id => [id, []]));
  const loose: ShopRecipeEntry[] = [];

  const open = (list.listItems ?? [])
    .filter(item => !item.checked)
    .map((item, index) => ({ item, index }))
    .sort((a, b) => (a.item.position ?? 0) - (b.item.position ?? 0) || a.index - b.index)
    .map(({ item }) => item);

  for (const item of open) {
    // An item's share of each recipe; a recipe can reference the same item more than once.
    const shares = new Map<string, number>();
    for (const ref of item.recipeReferences ?? []) {
      if (groups.has(ref.recipeId)) {
        shares.set(ref.recipeId, (shares.get(ref.recipeId) ?? 0) + (ref.recipeQuantity ?? 0));
      }
    }
    if (!shares.size) {
      loose.push({ item, others: [] });
      continue;
    }
    const ids = order.filter(id => shares.has(id));
    for (const id of ids) {
      groups.get(id)!.push({
        item,
        // A single recipe shows the item as it is on the list, so a quantity edited by hand still shows.
        quantity: ids.length > 1 && shares.get(id) ? shares.get(id) : undefined,
        others: ids.filter(other => other !== id).map(other => recipeNames.get(other)!),
      });
    }
  }

  const result: ShopRecipeGroup[] = order
    .filter(id => groups.get(id)!.length)
    .map(id => ({ recipeId: id, name: recipeNames.get(id)!, entries: groups.get(id)! }));
  if (loose.length) {
    result.push({ recipeId: null, name: null, entries: loose });
  }
  return result;
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
