import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import RecipeReadNutrition from "./RecipeReadNutrition.vue";
import RecipeReadRating from "./RecipeReadRating.vue";

const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

describe("RecipeReadRating", () => {
  test("a member rates by star and clicking the current star clears it", async () => {
    const wrapper = mount(RecipeReadRating, { props: { canRate: true, rating: 3 }, global: { stubs } });
    const stars = wrapper.findAll("button[aria-pressed]").slice(0, 5);

    expect(stars[2]!.attributes("aria-pressed")).toBe("true");
    expect(stars[2]!.attributes("aria-label")).toBe("3 stars");
    await stars[4]!.trigger("click");
    await stars[2]!.trigger("click");
    expect(wrapper.emitted("rate")).toEqual([[5], [0]]);
  });

  test("the favourite toggle says whether it is on", async () => {
    const wrapper = mount(RecipeReadRating, { props: { canRate: true, favorite: true }, global: { stubs } });
    const heart = wrapper.find("button[aria-label='Favourite']");

    expect(heart.attributes("aria-pressed")).toBe("true");
    await heart.trigger("click");
    expect(wrapper.emitted("toggle-favorite")).toHaveLength(1);
  });

  test("visitors see the group average, read-only, and nothing when there is none", () => {
    const rated = mount(RecipeReadRating, { props: { average: 4.25 }, global: { stubs } });
    expect(rated.find("button").exists()).toBe(false);
    expect(rated.text()).toBe("Rated 4.3 out of 5");

    const unrated = mount(RecipeReadRating, { props: { average: 0 }, global: { stubs } });
    expect(unrated.html()).toBe("<!--v-if-->");
  });
});

describe("RecipeReadNutrition", () => {
  test("starts collapsed, opens on demand and lists only filled values with their unit", async () => {
    const wrapper = mount(RecipeReadNutrition, {
      props: { nutrition: { calories: "540", proteinContent: "42", fatContent: "", sugarContent: null } },
      global: { stubs },
      attachTo: document.body,
    });
    const toggle = wrapper.find("button");

    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find("dl").isVisible()).toBe(false);
    await toggle.trigger("click");
    expect(wrapper.find("dl").isVisible()).toBe(true);
    expect(wrapper.findAll(".read-nutrition__row").map(r => r.text())).toEqual(["Calories540 calories", "Protein42 grams"]);
    wrapper.unmount();
  });

  test("renders nothing without values", () => {
    const wrapper = mount(RecipeReadNutrition, { props: { nutrition: { calories: null } }, global: { stubs } });
    expect(wrapper.find("section").exists()).toBe(false);
  });
});
