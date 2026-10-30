import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import RecipeReadIngredients from "./RecipeReadIngredients.vue";
import type { RecipeIngredient } from "~/lib/api/types/recipe";
import type { PantryItemOut } from "~/lib/api/types/household";
import type { IngredientPantry } from "~/composables/use-recipe-pantry";
import { useIngredientTextParser } from "~/composables/recipes";
import { useLocales } from "~/composables/use-locales";

vi.mock("~/composables/use-locales");

const stubs = {
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
};

const flour: RecipeIngredient = {
  referenceId: "ing-flour",
  quantity: 1.5,
  unit: { id: "u-cup", name: "cup", pluralName: "cups" },
  food: { id: "f-flour", name: "flour" },
};
const butter: RecipeIngredient = {
  referenceId: "ing-butter",
  quantity: 100,
  unit: { id: "u-g", name: "g", fraction: false },
  food: { id: "f-butter", name: "butter" },
};
const lemon: RecipeIngredient = {
  title: "To finish",
  referenceId: "ing-lemon",
  quantity: 1,
  food: { id: "f-lemon", name: "lemon" },
};

function render(props: Partial<{ ingredients: RecipeIngredient[]; scale: number; recipeSlug: string; collapsible: boolean; pantry: IngredientPantry | null; canAct: boolean }> = {}) {
  return mount(RecipeReadIngredients, {
    props: { ingredients: [flour, butter, lemon], scale: 1, recipeSlug: "lemon-cake", groupSlug: "home", ...props },
    global: { stubs },
    attachTo: document.body,
  });
}

function rows(wrapper: ReturnType<typeof render>) {
  return wrapper.findAll(".read-ingredients__item");
}

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

const pantryItem = (extra: Partial<PantryItemOut>): PantryItemOut => ({ id: "p", name: "x", groupId: "g", householdId: "h", ...extra });

describe("RecipeReadIngredients pantry status", () => {
  const pantry = (): IngredientPantry => ({
    "ing-flour": [pantryItem({ id: "p1", location: "cupboard" })],
    "ing-butter": [pantryItem({ id: "p2", location: "fridge", useBy: "2026-10-27" })],
    "ing-lemon": [],
  });

  function renderOn(day: Date, props: Parameters<typeof render>[0]) {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(day);
    const wrapper = render(props);
    vi.useRealTimers();
    return wrapper;
  }

  test("tags have, use soon and missing in words, with where it is and when to use it by", () => {
    const wrapper = renderOn(new Date(2026, 9, 26, 12), { pantry: pantry(), canAct: true });

    expect(rows(wrapper).map(row => row.find(".read-ingredients__tag").text())).toEqual(["Have", "Use soon", "Missing"]);
    expect(rows(wrapper).map(row => row.find(".read-ingredients__detail").exists() ? row.find(".read-ingredients__detail").text() : "")).toEqual([
      "Cupboard",
      "Fridge · Use by October 27",
      "",
    ]);
    expect(wrapper.find(".read-ingredients__summary strong").text()).toBe("2 of 3");
    expect(wrapper.find(".read-ingredients__summary").text()).toContain("2 of 3 in your pantry");
  });

  test("an ingredient naming no food has no tag and is no button", () => {
    const note: RecipeIngredient = { referenceId: "ing-n", quantity: 0, note: "a pinch of salt" };
    const wrapper = render({ ingredients: [flour, note], pantry: { "ing-flour": [] }, canAct: true });

    expect(rows(wrapper)[1]!.find(".read-ingredients__tag").exists()).toBe(false);
    expect(rows(wrapper)[1]!.find("button").exists()).toBe(false);
    expect(rows(wrapper)[0]!.find("button").exists()).toBe(true);
  });

  test("a row button is named by the ingredient and its status, and opens the ingredient with its items", async () => {
    const wrapper = render({ pantry: pantry(), canAct: true });

    const buttons = wrapper.findAll("button.read-ingredients__row");
    expect(buttons).toHaveLength(3);
    expect(buttons[2]!.text()).toContain("1 lemon");
    expect(buttons[2]!.text()).toContain("Missing");

    await buttons[2]!.trigger("click");
    await buttons[0]!.trigger("click");
    expect(wrapper.emitted("open-ingredient")).toEqual([
      [{ ingredient: lemon, items: [] }],
      [{ ingredient: flour, items: pantry()["ing-flour"] }],
    ]);
  });

  test("the summary offers to add the missing ones to the list", async () => {
    const wrapper = render({ pantry: pantry(), canAct: true });

    const add = wrapper.find(".read-ingredients__summary button");
    expect(add.text()).toBe("Add 1 to list");
    await add.trigger("click");
    expect(wrapper.emitted("add-missing")).toEqual([[[lemon]]]);
  });

  test("nothing missing: no add button", () => {
    const wrapper = render({ pantry: { "ing-flour": [pantryItem({})] }, canAct: true });
    expect(wrapper.find(".read-ingredients__summary button").exists()).toBe(false);
  });

  test("without canAct the status shows but there are no buttons", () => {
    const wrapper = render({ pantry: pantry() });
    expect(wrapper.findAll(".read-ingredients__tag")).toHaveLength(3);
    expect(wrapper.find("button.read-ingredients__row").exists()).toBe(false);
    expect(wrapper.find(".read-ingredients__summary button").exists()).toBe(false);
  });

  test("an unknown pantry shows no tags, buttons or summary", () => {
    const wrapper = render({ pantry: null, canAct: true });
    expect(wrapper.find(".read-ingredients__tag").exists()).toBe(false);
    expect(wrapper.find("button.read-ingredients__row").exists()).toBe(false);
    expect(wrapper.find(".read-ingredients__summary").exists()).toBe(false);
  });
});

describe("RecipeReadIngredients", () => {
  test("renders each ingredient through the shared ingredient text parser", () => {
    const { parseIngredientText } = useIngredientTextParser();
    const wrapper = render();

    expect(rows(wrapper)).toHaveLength(3);
    expect(rows(wrapper)[1]!.text()).toBe(parseIngredientText(butter, 1));
    expect(rows(wrapper)[1]!.text()).toBe("100 g butter");
  });

  test("a note follows the ingredient in the secondary colour", () => {
    const halved: RecipeIngredient = { referenceId: "ing-l2", quantity: 2, food: { id: "f-lemon", name: "lemon" }, note: "halved" };
    const wrapper = render({ ingredients: [halved] });

    expect(rows(wrapper)[0]!.text()).toBe("2 lemon halved");
    expect(wrapper.find(".read-ingredients__note").text()).toBe("halved");
  });

  test("notes render inline markdown, as upstream does", () => {
    const zest: RecipeIngredient = { referenceId: "ing-z", quantity: 1, food: { id: "f-lemon", name: "lemon" }, note: "**unwaxed**, zested" };
    const unparsed: RecipeIngredient = { referenceId: "ing-u", quantity: 0, note: "a *pinch* of salt" };
    const wrapper = render({ ingredients: [zest, unparsed] });

    expect(wrapper.find(".read-ingredients__note strong").text()).toBe("unwaxed");
    expect(rows(wrapper)[0]!.text()).toBe("1 lemon unwaxed, zested");
    expect(rows(wrapper)[1]!.find("em").text()).toBe("pinch");
    expect(rows(wrapper)[1]!.text()).toBe("a pinch of salt");
  });

  test("a referenced recipe keeps its link", () => {
    const pastry: RecipeIngredient = {
      referenceId: "ing-p",
      quantity: 1,
      referencedRecipe: { id: "r-pastry", name: "Shortcrust pastry", slug: "shortcrust-pastry" },
    };
    const wrapper = render({ ingredients: [pastry] });

    const link = rows(wrapper)[0]!.find("a");
    expect(link.attributes("href")).toBe("/g/home/r/shortcrust-pastry");
    expect(link.text()).toBe("Shortcrust pastry");
  });

  test("scaling multiplies the quantities", async () => {
    const wrapper = render({ scale: 2 });

    expect(rows(wrapper)[0]!.text()).toBe("3 cups flour");
    expect(rows(wrapper)[1]!.text()).toBe("200 g butter");

    await wrapper.setProps({ scale: 0.5 });
    expect(rows(wrapper)[1]!.text()).toBe("50 g butter");
  });

  test("an ingredient title starts a new section with its own heading", () => {
    const wrapper = render();

    const headings = wrapper.findAll(".read-ingredients__section-title");
    expect(headings.map(h => h.text())).toEqual(["To finish"]);
    const sections = wrapper.findAll(".read-ingredients__section");
    expect(sections).toHaveLength(2);
    expect(sections[1]!.findAll(".read-ingredients__item")).toHaveLength(1);
  });

  test("when collapsible, the heading toggles the list and starts open", async () => {
    const wrapper = render({ collapsible: true });

    const toggle = wrapper.find("button.read-ingredients__toggle");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(wrapper.find(".read-ingredients__list").isVisible()).toBe(true);

    await toggle.trigger("click");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find(".read-ingredients__list").isVisible()).toBe(false);
  });
});
