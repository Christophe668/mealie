import { format } from "date-fns";
import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test } from "vitest";
import RecipeIngredientSheet from "./RecipeIngredientSheet.vue";
import type { PantryItemOut, ShoppingListSummary } from "~/lib/api/types/household";
import type { RecipeIngredient } from "~/lib/api/types/recipe";
import { DEFAULT_PANTRY_LOCATION } from "~/lib/pantry/freshness";

const DsSheet = {
  props: ["modelValue", "title", "busy"],
  template: "<div v-if=\"modelValue\" class=\"sheet\"><slot name=\"header\" /><slot /></div>",
};

const lemon: RecipeIngredient = { referenceId: "ing-lemon", quantity: 2, food: { id: "f-lemon", name: "lemon" } };
const pantryItem = (extra: Partial<PantryItemOut> = {}): PantryItemOut => ({
  id: "p1",
  name: "lemon",
  location: "fridge",
  groupId: "g",
  householdId: "h",
  ...extra,
});
const list = (id: string, name: string): ShoppingListSummary => ({
  id,
  name,
  groupId: "g",
  userId: "u",
  householdId: "h",
  recipeReferences: [],
  labelSettings: [],
});

function render(props: Partial<{ items: PantryItemOut[]; lists: ShoppingListSummary[]; busy: boolean }> = {}) {
  return mount(RecipeIngredientSheet, {
    props: { modelValue: true, ingredient: lemon, items: [], lists: [list("l1", "Weekly shop")], busy: false, ...props },
    global: { stubs: { DsSheet, DsIcon: true } },
    attachTo: document.body,
  });
}

const actionLabels = (wrapper: ReturnType<typeof render>) =>
  wrapper.findAll(".ds-sheet__action").map(action => action.find(".recipe-sheet__label").text());

const action = (wrapper: ReturnType<typeof render>, label: string) =>
  wrapper.findAll(".ds-sheet__action").find(button => button.find(".recipe-sheet__label").text() === label)!;

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  document.body.innerHTML = "";
});

describe("RecipeIngredientSheet", () => {
  test("a missing ingredient offers I have it with the four places, and the shopping list", async () => {
    const wrapper = render();

    expect(wrapper.text()).toContain("Not in your pantry");
    expect(actionLabels(wrapper)).toEqual(["I have it", "Add to shopping list"]);
    const chips = wrapper.findAll("[role=radio]");
    expect(chips.map(chip => chip.text())).toEqual(["Fridge", "Freezer", "Cupboard", "Other"]);
    const checked = chips.filter(chip => chip.attributes("aria-checked") === "true");
    // DEFAULT_PANTRY_LOCATION
    expect(checked.map(chip => chip.text())).toEqual(["Cupboard"]);

    await chips[0]!.trigger("click");
    await action(wrapper, "I have it").trigger("click");
    expect(wrapper.emitted("i-have-it")).toEqual([["fridge", undefined]]);
  });

  test("+ use-by reveals a date that goes with I have it", async () => {
    const wrapper = render();
    expect(wrapper.find("input[type=date]").exists()).toBe(false);

    await wrapper.get(".recipe-sheet__use-by").trigger("click");
    await wrapper.get("input[type=date]").setValue("2026-11-03");
    await action(wrapper, "I have it").trigger("click");

    expect(wrapper.emitted("i-have-it")).toEqual([[DEFAULT_PANTRY_LOCATION, "2026-11-03"]]);
  });

  test("a held ingredient offers Running low, Opened today, Edit and Used up", async () => {
    const item = pantryItem();
    const wrapper = render({ items: [item] });

    expect(actionLabels(wrapper)).toEqual(["Running low", "Opened today", "Edit place or use-by", "Used up"]);
    expect(action(wrapper, "Used up").classes()).toContain("ds-sheet__action--danger");
    expect(wrapper.text()).toContain("Fridge");

    await action(wrapper, "Opened today").trigger("click");
    await action(wrapper, "Edit place or use-by").trigger("click");
    await action(wrapper, "Used up").trigger("click");
    await action(wrapper, "Running low").trigger("click");
    expect(wrapper.emitted("opened-today")).toEqual([[item]]);
    expect(wrapper.emitted("edit")).toEqual([[item]]);
    expect(wrapper.emitted("used-up")).toEqual([[item]]);
    expect(wrapper.emitted("running-low")).toEqual([["l1"]]);
  });

  test("an item opened today hides Opened today", () => {
    const wrapper = render({ items: [pantryItem({ openedOn: format(new Date(), "yyyy-MM-dd") })] });

    expect(actionLabels(wrapper)).toEqual(["Running low", "Edit place or use-by", "Used up"]);
  });

  test("two rows render two blocks, with Running low once", async () => {
    const fridge = pantryItem({ id: "p1", location: "fridge" });
    const freezer = pantryItem({ id: "p2", location: "freezer" });
    const wrapper = render({ items: [fridge, freezer] });

    const blocks = wrapper.findAll(".recipe-sheet__row");
    expect(blocks).toHaveLength(2);
    expect(blocks[0]!.text()).toContain("Fridge");
    expect(blocks[1]!.text()).toContain("Freezer");
    expect(actionLabels(wrapper).filter(label => label === "Running low")).toHaveLength(1);

    const usedUp = blocks[1]!.findAll(".ds-sheet__action").at(-1)!;
    await usedUp.trigger("click");
    expect(wrapper.emitted("used-up")).toEqual([[freezer]]);
  });

  test("with two lists, Add to shopping list shows the picker before emitting", async () => {
    const wrapper = render({ lists: [list("l1", "Weekly shop"), list("l2", "Market")] });

    await action(wrapper, "Add to shopping list").trigger("click");
    expect(wrapper.emitted("add-to-list")).toBeUndefined();
    expect(wrapper.text()).toContain("Which list?");
    expect(actionLabels(wrapper)).toEqual(["Weekly shop", "Market"]);

    await action(wrapper, "Market").trigger("click");
    expect(wrapper.emitted("add-to-list")).toEqual([["l2"]]);
    expect(sessionStorage.getItem("recipe-read:last-list")).toBe("l2");
  });

  test("the picker puts the last list used first and marks it", async () => {
    sessionStorage.setItem("recipe-read:last-list", "l2");
    const wrapper = render({ lists: [list("l1", "Weekly shop"), list("l2", "Market")] });

    await action(wrapper, "Add to shopping list").trigger("click");

    expect(actionLabels(wrapper)).toEqual(["Market", "Weekly shop"]);
    expect(action(wrapper, "Market").attributes("aria-current")).toBe("true");
  });

  test("with one list, the add names it and emits straight away", async () => {
    const wrapper = render();

    expect(action(wrapper, "Add to shopping list").text()).toContain("lemon → Weekly shop");
    await action(wrapper, "Add to shopping list").trigger("click");
    expect(wrapper.emitted("add-to-list")).toEqual([["l1"]]);
  });

  test("without an ingredient it is the list picker for the missing ones", async () => {
    const wrapper = mount(RecipeIngredientSheet, {
      props: { modelValue: true, ingredient: null, items: [], lists: [list("l1", "Weekly shop"), list("l2", "Market")], busy: false },
      global: { stubs: { DsSheet, DsIcon: true } },
    });

    expect(actionLabels(wrapper)).toEqual(["Weekly shop", "Market"]);
    await action(wrapper, "Weekly shop").trigger("click");
    expect(wrapper.emitted("add-missing")).toEqual([["l1"]]);
  });

  test("actions are disabled while busy", () => {
    const wrapper = render({ busy: true });

    expect(wrapper.findAll(".ds-sheet__action").every(button => button.attributes("disabled") !== undefined)).toBe(true);
  });
});
