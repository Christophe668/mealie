import { format } from "date-fns";
import { useUserApi } from "~/composables/api";
import { toPantryUpdate } from "~/composables/use-pantry";
import { alert, alertUnreportedError } from "~/composables/use-toast";
import type { PantryItemOut, PantryItemUpdate, PantryLocation, ShoppingListSummary } from "~/lib/api/types/household";
import type { RequestResponse } from "~/lib/api/types/non-generated";
import type { RecipeIngredient } from "~/lib/api/types/recipe";

type Response<T> = Pick<RequestResponse<T>, "data" | "error">;

const UNDO_TIMEOUT = 5000;

export interface IngredientPantryActionsOptions {
  recipeId: () => string;
  /** The scale the recipe page currently shows. */
  scale: () => number;
  /** Swaps one ingredient's pantry items on screen (from `useRecipePantry`). */
  setItems: (referenceId: string, items: PantryItemOut[]) => void;
  /** One ingredient's pantry items as shown now, so an action (or its undo) changes only its own row. */
  items: (referenceId: string) => PantryItemOut[];
  /** The household's shopping lists, to name the list an add went to. */
  lists: () => ShoppingListSummary[];
}

/**
 * What the recipe page's ingredient sheet does to the pantry and the shopping lists. Pantry changes get an
 * Undo; shopping list adds get "Open list" instead, since the server may merge them into an existing item.
 * Every action resolves true on success; a failure is reported and leaves the ingredient's items as they were.
 */
export function useIngredientPantryActions(opts: IngredientPantryActionsOptions) {
  const api = useUserApi();
  const i18n = useI18n();
  const router = useRouter();
  const busy = ref(false);

  const key = (name: string) => `recipe-ingredient-sheet.${name}`;
  const t = (name: string, params?: Record<string, unknown>) => (params ? i18n.t(key(name), params) : i18n.t(key(name)));

  const foodName = (ingredient: RecipeIngredient) => ingredient.food?.name || ingredient.note || i18n.t("recipe.ingredient");
  const listName = (listId: string) => opts.lists().find(list => list.id === listId)?.name ?? "";

  /** Applies a change to one ingredient's rows, as they are now. */
  function change(ingredient: RecipeIngredient, update: (items: PantryItemOut[]) => PantryItemOut[]) {
    const referenceId = ingredient.referenceId;
    if (referenceId) {
      opts.setItems(referenceId, update(opts.items(referenceId)));
    }
  }
  const replace = (item: PantryItemOut) => (items: PantryItemOut[]) => items.map(row => (row.id === item.id ? item : row));
  /** A create can come back merged into a row already shown (same food): replace that row, else add it. */
  const upsert = (item: PantryItemOut) => (items: PantryItemOut[]) =>
    items.some(row => row.id === item.id) ? replace(item)(items) : [...items, item];

  /** One request at a time: a second tap while saving does nothing. */
  async function run<T>(request: () => Promise<Response<T>>, fallback: string): Promise<T | null> {
    if (busy.value) {
      return null;
    }
    busy.value = true;
    try {
      const { data, error } = await request();
      if (!data) {
        alertUnreportedError(error ?? null, fallback);
        return null;
      }
      return data;
    }
    finally {
      busy.value = false;
    }
  }

  /** A snackbar with a one-shot Undo; a failed undo says so and leaves the screen as it is. */
  function withUndo<T>(text: string, undo: () => Promise<Response<T>>, onUndone: (data: T) => void) {
    let undone = false;
    alert.info(text, undefined, {
      timeout: UNDO_TIMEOUT,
      action: {
        message: i18n.t("general.undo"),
        onClick: async () => {
          if (undone) {
            return;
          }
          undone = true;
          const { data, error } = await undo();
          if (!data) {
            alertUnreportedError(error ?? null, t("undo-failed"));
            return;
          }
          onUndone(data);
        },
      },
    });
  }

  function withOpenList(text: string, listId: string) {
    alert.info(text, undefined, {
      timeout: UNDO_TIMEOUT,
      action: { message: i18n.t("shop.open-list"), onClick: () => router.push(`/shopping-lists/${listId}`) },
    });
  }

  const saveFailed = () => i18n.t("pantry.save-failed");

  /** "I have it": a manual pantry item for the ingredient's food, in the chosen place. */
  async function iHaveIt(ingredient: RecipeIngredient, location: PantryLocation, useBy?: string): Promise<boolean> {
    const name = foodName(ingredient);
    const created = await run(
      () => api.householdPantry.createOne({ name, foodId: ingredient.food?.id, location, useBy: useBy || undefined, source: "manual" }),
      saveFailed(),
    );
    if (!created) {
      return false;
    }
    // Merged into a row already there: Undo puts that row back as it was instead of deleting it.
    const before = opts.items(ingredient.referenceId ?? "").find(row => row.id === created.id);
    change(ingredient, upsert(created));
    if (before) {
      withUndo(
        t("added-to-pantry", { name }),
        () => api.householdPantry.updateOne(before.id, toPantryUpdate(before)),
        restored => change(ingredient, replace(restored)),
      );
      return true;
    }
    withUndo(
      t("added-to-pantry", { name }),
      () => api.householdPantry.deleteOne(created.id),
      () => change(ingredient, items => items.filter(item => item.id !== created.id)),
    );
    return true;
  }

  /** "Used up": deletes the row; Undo recreates it from what it was (a new id). */
  async function usedUp(ingredient: RecipeIngredient, item: PantryItemOut): Promise<boolean> {
    if (!(await run(() => api.householdPantry.deleteOne(item.id), saveFailed()))) {
      return false;
    }
    change(ingredient, items => items.filter(row => row.id !== item.id));
    withUndo(
      t("removed-from-pantry", { name: item.name }),
      () => api.householdPantry.createOne(toPantryUpdate(item)),
      restored => change(ingredient, upsert(restored)),
    );
    return true;
  }

  /** Saves a row with some fields changed; Undo puts those fields back on the row as it is then. */
  async function updateRow(ingredient: RecipeIngredient, item: PantryItemOut, changes: Partial<PantryItemUpdate>, text: string): Promise<boolean> {
    const updated = await run(() => api.householdPantry.updateOne(item.id, toPantryUpdate(item, changes)), saveFailed());
    if (!updated) {
      return false;
    }
    change(ingredient, replace(updated));
    const previous = toPantryUpdate(item);
    withUndo(
      text,
      () => {
        const current = opts.items(ingredient.referenceId ?? "").find(row => row.id === item.id) ?? updated;
        const keys = Object.keys(changes) as (keyof PantryItemUpdate)[];
        return api.householdPantry.updateOne(item.id, toPantryUpdate(current, Object.fromEntries(keys.map(key => [key, previous[key]]))));
      },
      restored => change(ingredient, replace(restored)),
    );
    return true;
  }

  function openedToday(ingredient: RecipeIngredient, item: PantryItemOut): Promise<boolean> {
    const openedOn = format(new Date(), "yyyy-MM-dd");
    return updateRow(ingredient, item, { openedOn }, t("marked-opened", { name: item.name }));
  }

  /** The pantry item dialog's save (Edit place or use-by). */
  function edit(ingredient: RecipeIngredient, item: PantryItemOut, data: PantryItemUpdate): Promise<boolean> {
    return updateRow(ingredient, item, data, t("updated-in-pantry", { name: data.name || item.name }));
  }

  /** One ingredient as a plain list item at the page's scale; never `addRecipes`, so the recipe isn't counted. */
  async function addToList(ingredient: RecipeIngredient, listId: string): Promise<boolean> {
    const added = await run(
      () => api.shopping.items.createOne({
        shoppingListId: listId,
        foodId: ingredient.food?.id,
        unitId: ingredient.unit?.id,
        // Quantity-less ("salt to taste") is one of it at any scale.
        quantity: ingredient.quantity ? ingredient.quantity * opts.scale() : 1,
        note: ingredient.note || "",
      }),
      i18n.t("events.something-went-wrong"),
    );
    if (!added) {
      return false;
    }
    withOpenList(t("added-to-list", { item: foodName(ingredient), list: listName(listId) }), listId);
    return true;
  }

  /** All missing ingredients in one `addRecipes` call, so the list shows the recipe as the reason. */
  async function addMissing(ingredients: RecipeIngredient[], listId: string): Promise<boolean> {
    if (!ingredients.length) {
      return false;
    }
    const added = await run(
      () => api.shopping.lists.addRecipes(listId, [
        { recipeId: opts.recipeId(), recipeIncrementQuantity: opts.scale(), recipeIngredients: ingredients },
      ]),
      i18n.t("events.something-went-wrong"),
    );
    if (!added) {
      return false;
    }
    const count = ingredients.length;
    withOpenList(i18n.t(key("added-missing"), { count, list: listName(listId) }, count), listId);
    return true;
  }

  return { busy, iHaveIt, usedUp, openedToday, edit, addToList, addMissing };
}
