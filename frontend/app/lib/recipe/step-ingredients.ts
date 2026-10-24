import type { RecipeIngredient, RecipeStep } from "~/lib/api/types/recipe";

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Whole-word, case-insensitive, with an optional plural "s"/"es". */
function mentions(text: string, term: string): boolean {
  const words = term.trim().toLowerCase();
  if (words.length < 2) {
    return false;
  }
  return new RegExp(`(?<![\\p{L}\\d])${escapeRegExp(words)}(?:e?s)?(?![\\p{L}\\d])`, "iu").test(text);
}

function terms(ingredient: RecipeIngredient): string[] {
  const names = [ingredient.food?.name, ingredient.food?.pluralName, ingredient.referencedRecipe?.name];
  if (!ingredient.food && !ingredient.referencedRecipe) {
    // An unparsed line ("salt, to taste"): its first phrase names the ingredient.
    names.push((ingredient.note || ingredient.originalText || "").split(/[,(]/)[0]);
  }
  return names.filter((name): name is string => !!name?.trim());
}

/**
 * The ingredients a step uses: its explicit links from the editor when it has any, otherwise the ones
 * whose food is named in the text, by the full name or else its last word ("red onion" matches "the onions").
 */
export function ingredientsInStep(ingredients: RecipeIngredient[], step: RecipeStep | undefined): number[] {
  if (!step) {
    return [];
  }
  const linked = new Set((step.ingredientReferences ?? []).map(ref => ref.referenceId).filter(Boolean));
  if (linked.size) {
    return ingredients.flatMap((ingredient, index) => (ingredient.referenceId && linked.has(ingredient.referenceId) ? [index] : []));
  }
  const text = step.text || "";
  return ingredients.flatMap((ingredient, index) => {
    const names = terms(ingredient);
    const found = names.some(name => mentions(text, name))
      || names.some((name) => {
        const last = name.trim().split(/\s+/).pop() || "";
        return last !== name.trim() && last.length >= 3 && mentions(text, last);
      });
    return found ? [index] : [];
  });
}
