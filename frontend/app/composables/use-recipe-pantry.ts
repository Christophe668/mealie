import { format } from "date-fns";
import { useUserApi } from "~/composables/api";
import type { PantryItemOut } from "~/lib/api/types/household";

/** Pantry items per ingredient `referenceId`. An ingredient that names no food is absent: it can't be told. */
export type IngredientPantry = Record<string, PantryItemOut[]>;

/**
 * What the household's pantry holds of a recipe's ingredients, matched by the server with the same rule as
 * the end-of-cooking pantry check. Null while unknown: not loaded yet, failed, or not the household's to see.
 */
export function useRecipePantry(recipeId: () => string | undefined, enabled: () => boolean) {
  const api = useUserApi();
  const pantry = ref<IngredientPantry | null>(null);
  let stamp = 0;

  async function load(id: string | undefined) {
    const current = ++stamp;
    pantry.value = null;
    if (!id || !enabled()) {
      return;
    }
    try {
      // The date only picks the meal plan entry a cooking would mark; any day gives the same pantry.
      const { data } = await api.householdCooking.pantryCheck(id, format(new Date(), "yyyy-MM-dd"));
      if (current !== stamp || !data) {
        return;
      }
      const items = new Map(data.items.map(item => [item.id, item]));
      pantry.value = Object.fromEntries(
        (data.ingredients ?? []).map(match => [
          match.referenceId,
          (match.pantryItemIds ?? []).map(itemId => items.get(itemId)).filter((item): item is PantryItemOut => !!item),
        ]),
      );
    }
    catch {
      // The recipe reads fine without it.
    }
  }

  watch([recipeId, enabled], ([id]) => load(id), { immediate: true });

  return { pantry };
}
