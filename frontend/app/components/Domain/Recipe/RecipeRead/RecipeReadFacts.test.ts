import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import RecipeReadFacts from "./RecipeReadFacts.vue";
import type { Recipe } from "~/lib/api/types/recipe";

const stubs = {
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
};

const roast: Recipe = {
  slug: "roast",
  prepTimeSeconds: 1200,
  performTimeSeconds: 3000,
  totalTimeSeconds: 4200,
  recipeServings: 4,
  recipeIngredient: [{ quantity: 1, food: { id: "f", name: "chicken" } }],
};

function render(recipe: Recipe, scale = 1) {
  return mount(RecipeReadFacts, { props: { recipe, scale, cookTo: "/g/home/r/roast/cook" }, global: { stubs } });
}

describe("RecipeReadFacts", () => {
  test("each fact is its own line, never joined", () => {
    const lines = render(roast).findAll(".read-facts__line").map(l => l.text());

    expect(lines.slice(0, 3)).toEqual(["Prep 20 minutes", "Cook 50 minutes", "Total 1 hour 10 minutes"]);
    expect(lines.join("")).not.toMatch(/[·•]/);
  });

  test("scaled servings show as a fraction, like upstream", () => {
    const serves = render(roast, 1 / 3).find(".read-facts__serves");

    expect(serves.text()).toBe("Serves 11⁄3");
    expect(serves.find("sup").text()).toBe("1");
    expect(serves.find("sub").text()).toBe("3");
  });

  test("the stepper changes the scale by one serving", async () => {
    const wrapper = render(roast);

    await wrapper.find("button[aria-label='More servings']").trigger("click");
    expect(wrapper.emitted("update:scale")![0]).toEqual([5 / 4]);
  });

  test("a bare recipe shows no facts and no empty labels", () => {
    const wrapper = render({ slug: "bare", recipeIngredient: [] });

    expect(wrapper.find(".read-facts__list").exists()).toBe(false);
    expect(wrapper.text()).toBe("Start cooking");
  });
});
