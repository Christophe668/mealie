import { describe, expect, test } from "vitest";
import { ingredientsInStep } from "./step-ingredients";
import type { RecipeIngredient, RecipeStep } from "~/lib/api/types/recipe";

const food = (name: string, extra: Partial<RecipeIngredient> = {}): RecipeIngredient => ({
  referenceId: `ing-${name}`,
  quantity: 1,
  food: { id: `f-${name}`, name },
  ...extra,
});

const step = (text: string, extra: Partial<RecipeStep> = {}): RecipeStep => ({ text, ...extra });

/** Names of the ingredients a step uses, for readable assertions. */
function used(ingredients: RecipeIngredient[], text: string, extra: Partial<RecipeStep> = {}) {
  return ingredientsInStep(ingredients, step(text, extra)).map(i => ingredients[i]!.food?.name ?? ingredients[i]!.note);
}

describe("ingredientsInStep", () => {
  test("a singular food matches its plural in the text", () => {
    expect(used([food("potato")], "Boil the potatoes")).toEqual(["potato"]);
    expect(used([food("tomato")], "Halve the tomatoes")).toEqual(["tomato"]);
  });

  test("whole words only: salt is not in salted water", () => {
    expect(used([food("salt")], "Boil in salted water")).toEqual([]);
    expect(used([food("salt")], "Season with salt.")).toEqual(["salt"]);
  });

  test("case and diacritics are folded", () => {
    expect(used([food("Salt")], "SEASON WITH SALT")).toEqual(["Salt"]);
    expect(used([food("crème fraîche")], "Stir in the creme fraiche")).toEqual(["crème fraîche"]);
    expect(used([food("creme fraiche")], "Ajouter la crème fraîche")).toEqual(["creme fraiche"]);
  });

  test("the step's explicit ingredient links beat text matches", () => {
    const ingredients = [food("butter"), food("flour")];
    const linked = { ingredientReferences: [{ referenceId: "ing-flour" }] };
    expect(used(ingredients, "Melt the butter", linked)).toEqual(["flour"]);
  });

  test("an unparsed line is named by the first phrase of its note", () => {
    const salt: RecipeIngredient = { referenceId: "ing-salt", quantity: 0, note: "salt, to taste" };
    expect(used([salt], "Season with salt and pepper")).toEqual(["salt, to taste"]);
  });

  test("a qualified food matches its head noun: red onion in the onions", () => {
    expect(used([food("red onion")], "Fry the onions until soft")).toEqual(["red onion"]);
  });

  test("a shared head noun never matches the wrong food", () => {
    const ingredients = [food("garlic powder"), food("baking powder")];
    expect(used(ingredients, "Sift the flour with the baking powder")).toEqual(["baking powder"]);
    expect(used(ingredients, "Rub the chicken with garlic powder")).toEqual(["garlic powder"]);
    // Two oils and a bare "oil": ambiguous, so neither lights up.
    expect(used([food("olive oil"), food("sesame oil")], "Drizzle with oil")).toEqual([]);
  });

  test("one-letter names and empty steps match nothing", () => {
    expect(used([food("a")], "Add a pinch")).toEqual([]);
    expect(ingredientsInStep([food("salt")], undefined)).toEqual([]);
  });
});
