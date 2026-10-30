import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, test } from "vitest";
import ShopItemSheet from "./ShopItemSheet.vue";
import type { PantryItemOut, PantryLocation, ShoppingListItemOut } from "~/lib/api/types/household";

const DsSheet = {
  props: ["modelValue", "title", "busy"],
  template: "<div v-if=\"modelValue\" class=\"sheet\"><slot name=\"header\" /><slot /></div>",
};

const milk = (extra: Partial<ShoppingListItemOut> = {}): ShoppingListItemOut => ({
  id: "milk",
  shoppingListId: "list",
  groupId: "g",
  householdId: "h",
  checked: false,
  quantity: 1,
  display: "1 milk",
  food: { id: "f-milk", name: "milk" },
  ...extra,
});
const pantryMilk: PantryItemOut = { id: "p1", name: "milk", location: "fridge", groupId: "g", householdId: "h" };

function render(props: Partial<{
  item: ShoppingListItemOut | null;
  match: PantryItemOut | null | undefined;
  guessedLocation: PantryLocation;
  busy: boolean;
  forText: string;
}> = {}) {
  return mount(ShopItemSheet, {
    props: { modelValue: true, item: milk(), match: null, guessedLocation: "fridge", busy: false, ...props },
    global: { stubs: { DsSheet, DsIcon: true } },
    attachTo: document.body,
  });
}

const labels = (wrapper: ReturnType<typeof render>) =>
  wrapper.findAll(".ds-sheet__action").map(action => action.find(".shop-sheet__label").text());
const action = (wrapper: ReturnType<typeof render>, label: string) =>
  wrapper.findAll(".ds-sheet__action").find(button => button.find(".shop-sheet__label").text() === label)!;

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ShopItemSheet", () => {
  test("an open item shows its text, what it is for, and the actions in order", () => {
    const wrapper = render({ forText: "For Roast chicken" });

    expect(wrapper.find(".shop-sheet__title").text()).toBe("1 milk");
    expect(wrapper.find(".shop-sheet__for").text()).toBe("For Roast chicken");
    expect(labels(wrapper)).toEqual([
      "Mark as bought",
      "Bought, put it away",
      "Already in the pantry",
      "Edit quantity or note",
      "Remove from list",
    ]);
    expect(action(wrapper, "Remove from list").classes()).toContain("ds-sheet__action--danger");
  });

  test("a bought item offers Not bought instead", () => {
    const wrapper = render({ item: milk({ checked: true }) });

    expect(labels(wrapper)[0]).toBe("Not bought");
  });

  test("no recipe, no For line", () => {
    const wrapper = render();

    expect(wrapper.find(".shop-sheet__for").exists()).toBe(false);
  });

  test("when the pantry already holds it, put away says where it goes and shows no places", () => {
    const wrapper = render({ match: pantryMilk });

    expect(action(wrapper, "Bought, put it away").text()).toContain("Adds to the one in the fridge");
    expect(wrapper.findAll("[role=radio]")).toHaveLength(0);
  });

  test("a pantry row with no particular place reads as already in the pantry", () => {
    const wrapper = render({ match: { ...pantryMilk, location: "other" } });

    expect(action(wrapper, "Bought, put it away").text()).toContain("Adds to the one already in the pantry");
  });

  test("when it is not in the pantry, the places show, preselected with the guess", () => {
    const wrapper = render({ match: null, guessedLocation: "freezer" });

    const chips = wrapper.findAll("[role=radio]");
    expect(chips.map(chip => chip.text())).toEqual(["Fridge", "Freezer", "Cupboard", "Other"]);
    expect(chips.filter(chip => chip.attributes("aria-checked") === "true").map(chip => chip.text())).toEqual(["Freezer"]);
  });

  test("the chosen place goes with put away and with already in the pantry", async () => {
    const wrapper = render({ match: null, guessedLocation: "fridge" });

    await wrapper.findAll("[role=radio]").find(chip => chip.text() === "Cupboard")!.trigger("click");
    await action(wrapper, "Bought, put it away").trigger("click");
    await action(wrapper, "Already in the pantry").trigger("click");

    expect(wrapper.emitted("put-away")).toEqual([["cupboard"]]);
    expect(wrapper.emitted("already-have")).toEqual([["cupboard"]]);
  });

  test("already in the pantry shows the places only when the pantry does not hold it", () => {
    expect(render({ match: null }).findAll("[role=radio]").length).toBeGreaterThan(0);
    document.body.innerHTML = "";
    expect(render({ match: pantryMilk }).findAll("[role=radio]")).toHaveLength(0);
  });

  test("while the pantry is being asked, the two pantry actions wait", () => {
    const wrapper = render({ match: undefined });

    expect(action(wrapper, "Bought, put it away").attributes("disabled")).toBeDefined();
    expect(action(wrapper, "Already in the pantry").attributes("disabled")).toBeDefined();
    expect(action(wrapper, "Mark as bought").attributes("disabled")).toBeUndefined();
    expect(wrapper.findAll("[role=radio]")).toHaveLength(0);
  });

  test("busy disables every action", () => {
    const wrapper = render({ busy: true });

    expect(wrapper.findAll(".ds-sheet__action").every(button => button.attributes("disabled") !== undefined)).toBe(true);
  });

  test("the other actions emit without arguments", async () => {
    const wrapper = render();

    await action(wrapper, "Mark as bought").trigger("click");
    await action(wrapper, "Edit quantity or note").trigger("click");
    await action(wrapper, "Remove from list").trigger("click");

    expect(wrapper.emitted("toggle")).toHaveLength(1);
    expect(wrapper.emitted("edit")).toHaveLength(1);
    expect(wrapper.emitted("remove")).toHaveLength(1);
  });
});
