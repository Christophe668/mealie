import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import CookIngredients from "./CookIngredients.vue";
import RecipeReadIngredients, { ingredientTicksKey } from "~/components/Domain/Recipe/RecipeRead/RecipeReadIngredients.vue";
import type { RecipeIngredient } from "~/lib/api/types/recipe";
import { useLocales } from "~/composables/use-locales";

vi.mock("~/composables/use-locales");

const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

const ingredients: RecipeIngredient[] = [
  { referenceId: "ing-flour", quantity: 1.5, unit: { id: "u-cup", name: "cup", pluralName: "cups" }, food: { id: "f-flour", name: "flour" } },
  { referenceId: "ing-butter", quantity: 100, unit: { id: "u-g", name: "g", fraction: false }, food: { id: "f-butter", name: "butter" }, note: "softened" },
  { referenceId: "ing-egg", quantity: 0.5, food: { id: "f-egg", name: "egg", pluralName: "eggs" } },
];

const props = { ingredients, recipeSlug: "cake", groupSlug: "home" };

beforeEach(() => {
  sessionStorage.clear();
  vi.mocked(useLocales).mockReturnValue({
    locales: [{ value: "en-US", pluralFoodHandling: "without-unit" }],
    locale: { value: "en-US" },
  } as any);
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("CookIngredients", () => {
  test.each([1, 2, 0.5])("quantities match the read page at scale %s", (scale) => {
    const cook = mount(CookIngredients, { props: { ...props, scale }, global: { stubs } });
    const read = mount(RecipeReadIngredients, { props: { ...props, scale }, global: { stubs } });

    const lines = (wrapper: typeof cook | typeof read, selector: string) => wrapper.findAll(selector).map(row => row.text());
    expect(lines(cook, ".cook-ingredients__item")).toEqual(lines(read, ".read-ingredients__item"));
    expect(lines(cook, ".cook-ingredients__item")[0]).toBe(scale === 2 ? "3 cups flour" : lines(read, ".read-ingredients__item")[0]);
  });

  test("ticks are the read page's ticks", async () => {
    sessionStorage.setItem(ingredientTicksKey("cake"), JSON.stringify({ "ref:ing-butter": true }));
    const cook = mount(CookIngredients, { props, global: { stubs } });

    expect(cook.findAll(".cook-ingredients__item")[1]!.classes()).toContain("checked");
    await cook.findAll("input[type=checkbox]")[0]!.setValue(true);
    expect(JSON.parse(sessionStorage.getItem(ingredientTicksKey("cake"))!)).toEqual({ "ref:ing-butter": true, "ref:ing-flour": true });
  });

  test("compact shows only this step's ingredients, without ticks", () => {
    const cook = mount(CookIngredients, { props: { ...props, active: [1], compact: true }, global: { stubs } });

    expect(cook.findAll("li").map(li => li.text())).toEqual(["100 g butter softened"]);
    expect(cook.find("input").exists()).toBe(false);
  });
});
