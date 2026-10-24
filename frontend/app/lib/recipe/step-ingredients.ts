import type { RecipeIngredient, RecipeStep } from "~/lib/api/types/recipe";

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Lowercase without accents, so "Crème" and "creme" compare equal. */
const fold = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

/** Whole words (on folded text), with an optional plural "s"/"es". */
function mentions(foldedText: string, term: string): boolean {
  const words = fold(term.trim());
  if (words.length < 2) {
    return false;
  }
  return new RegExp(`(?<![\\p{L}\\d])${escapeRegExp(words)}(?:e?s)?(?![\\p{L}\\d])`, "u").test(foldedText);
}

function terms(ingredient: RecipeIngredient): string[] {
  const names = [ingredient.food?.name, ingredient.food?.pluralName, ingredient.referencedRecipe?.name];
  if (!ingredient.food && !ingredient.referencedRecipe) {
    // An unparsed line ("salt, to taste"): its first phrase names the ingredient.
    names.push((ingredient.note || ingredient.originalText || "").split(/[,(]/)[0]);
  }
  return names.map(name => name?.trim() ?? "").filter(Boolean);
}

/** The head noun of a multi-word name ("red onion" gives "onion"), or "" for a one-word name. */
function headNoun(name: string): string {
  const words = name.split(/\s+/);
  const last = words.length > 1 ? words[words.length - 1]! : "";
  return last.length >= 3 ? fold(last) : "";
}

/**
 * The ingredients a step uses: its explicit links from the editor when it has any, otherwise the ones
 * whose food is named in the text. The whole name counts first; the head noun alone ("red onion" in
 * "the onions") only when no other ingredient shares it, so baking powder never lights up garlic powder.
 */
export function ingredientsInStep(ingredients: RecipeIngredient[], step: RecipeStep | undefined): number[] {
  if (!step) {
    return [];
  }
  const linked = new Set((step.ingredientReferences ?? []).map(ref => ref.referenceId).filter(Boolean));
  if (linked.size) {
    return ingredients.flatMap((ingredient, index) => (ingredient.referenceId && linked.has(ingredient.referenceId) ? [index] : []));
  }

  const text = fold(step.text || "");
  const names = ingredients.map(terms);
  const heads = names.map(list => new Set(list.map(headNoun).filter(Boolean)));
  // How many ingredients each noun could stand for: as a head noun or as a whole one-word name.
  const claims = new Map<string, number>();
  names.forEach((list, i) => {
    const nouns = new Set([...heads[i]!, ...list.map(fold)]);
    nouns.forEach(noun => claims.set(noun, (claims.get(noun) ?? 0) + 1));
  });

  return ingredients.flatMap((_, index) => {
    const found = names[index]!.some(name => mentions(text, name))
      || [...heads[index]!].some(head => claims.get(head) === 1 && mentions(text, head));
    return found ? [index] : [];
  });
}
