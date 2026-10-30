import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";

type Translate = (key: string, params: Record<string, unknown>) => string;

/** Recipe names by id, from a list's recipe references. */
export function recipeNamesOf(list: ShoppingListOut | null | undefined): Map<string, string> {
  return new Map(
    (list?.recipeReferences ?? [])
      .filter(ref => ref.recipe?.name)
      .map(ref => [ref.recipeId, ref.recipe.name as string]),
  );
}

/** "For Roast chicken" (or "For Roast chicken and 2 more") from the item's recipe references; "" when none. */
export function itemForText(item: ShoppingListItemOut, recipeNames: Map<string, string>, t: Translate): string {
  const names = [...new Set((item.recipeReferences ?? []).map(ref => ref.recipeId))]
    .map(id => recipeNames.get(id))
    .filter((name): name is string => !!name);
  if (!names.length) {
    return "";
  }
  if (names.length === 1) {
    return t("shop.for-recipe", { recipe: names[0] });
  }
  return t("shop.for-recipe-and-more", { recipe: names[0], count: names.length - 1 });
}
