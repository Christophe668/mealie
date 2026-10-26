import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import RecipeReadIngredients, { ingredientTicksKey } from "./RecipeReadIngredients.vue";
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

function render(props: Partial<{ ingredients: RecipeIngredient[]; scale: number; recipeSlug: string; collapsible: boolean; pantry: IngredientPantry | null }> = {}) {
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

describe("RecipeReadIngredients pantry", () => {
  test("marks each ingredient in the pantry or not, with where it is, and sums it up", () => {
    const wrapper = render({
      pantry: {
        "ing-flour": [pantryItem({ id: "p1", location: "cupboard" })],
        "ing-butter": [],
        "ing-lemon": [pantryItem({ id: "p2", location: "fridge" }), pantryItem({ id: "p3", location: "freezer" })],
      },
    });

    const marks = rows(wrapper).map(row => row.find(".read-ingredients__pantry"));
    expect(marks.map(m => m.text())).toEqual(["In pantry · Cupboard", "Not in pantry", "In pantry · Fridge, Freezer"]);
    expect(marks.map(m => m.classes().includes("read-ingredients__pantry--have"))).toEqual([true, false, true]);
    expect(wrapper.find(".read-ingredients__summary").text()).toBe("2 of 3 in your pantry");
  });

  test("an item near its use-by date says so", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 9, 26, 12));
    const wrapper = render({ pantry: { "ing-butter": [pantryItem({ location: "fridge", useBy: "2026-10-27" })] } });
    vi.useRealTimers();

    const mark = wrapper.find(".read-ingredients__pantry");
    expect(mark.text()).toBe("In pantry · Fridge · Use by October 27");
    expect(mark.classes()).toContain("read-ingredients__pantry--urgent");
  });

  test("ingredients the pantry can't tell, and an unknown pantry, show nothing", () => {
    const told = render({ pantry: { "ing-flour": [] } });
    expect(rows(told).map(row => row.find(".read-ingredients__pantry").exists())).toEqual([true, false, false]);
    expect(told.find(".read-ingredients__summary").text()).toBe("0 of 1 in your pantry");
    told.unmount();

    const unknown = render({ pantry: null });
    expect(unknown.find(".read-ingredients__pantry").exists()).toBe(false);
    expect(unknown.find(".read-ingredients__summary").exists()).toBe(false);
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

  test("each ingredient is a real, labelled checkbox", () => {
    const wrapper = render();

    const boxes = wrapper.findAll("input[type=checkbox]");
    expect(boxes).toHaveLength(3);
    const label = wrapper.find(`label[for="${boxes[0]!.attributes("id")}"]`);
    expect(label.exists()).toBe(true);
    expect(label.text()).toContain("flour");
  });

  test("ticking an ingredient marks it checked and unticking clears it", async () => {
    const wrapper = render();

    await wrapper.findAll("input[type=checkbox]")[1]!.setValue(true);
    expect(rows(wrapper)[1]!.classes()).toContain("checked");
    expect(rows(wrapper)[0]!.classes()).not.toContain("checked");

    await wrapper.findAll("input[type=checkbox]")[1]!.setValue(false);
    expect(rows(wrapper)[1]!.classes()).not.toContain("checked");
  });

  test("ticks persist in session storage per recipe slug", async () => {
    const first = render();
    await first.findAll("input[type=checkbox]")[0]!.setValue(true);
    expect(JSON.parse(sessionStorage.getItem(ingredientTicksKey("lemon-cake"))!)).toEqual({ "ref:ing-flour": true });
    first.unmount();

    const again = render();
    expect(rows(again)[0]!.classes()).toContain("checked");
    expect((again.findAll("input[type=checkbox]")[0]!.element as HTMLInputElement).checked).toBe(true);
    again.unmount();

    const otherRecipe = render({ recipeSlug: "apple-pie" });
    expect(rows(otherRecipe)[0]!.classes()).not.toContain("checked");
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
