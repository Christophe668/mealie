import { mount } from "@vue/test-utils";
import type { DOMWrapper } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import CookPantryCheck from "./CookPantryCheck.vue";
import type { PantryChoices } from "./CookPantryCheck.vue";
import type { PantryItemOut, PantryProposal, UnmatchedIngredient } from "~/lib/api/types/household";

const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

const item = (id: string, name: string, extra: Partial<PantryItemOut> = {}): PantryItemOut => ({
  id,
  name,
  groupId: "g",
  householdId: "h",
  ...extra,
});

const items = [
  item("p-butter", "Butter", { quantity: 250, unit: { id: "u-g", name: "gram", pluralName: "grams" } }),
  item("p-onion", "Onions", { quantity: 3 }),
];

type Props = Partial<{ items: PantryItemOut[]; proposals: PantryProposal[]; unmatched: UnmatchedIngredient[]; pantry: PantryItemOut[]; disabled: boolean }>;

function render(model: Partial<PantryChoices> = {}, props: Props = {}) {
  const wrapper = mount(CookPantryCheck, {
    props: {
      "items": items,
      "modelValue": { outcomes: {}, quantities: {}, substitutes: {}, portions: 2, location: "fridge", ...model },
      "onUpdate:modelValue": (value: PantryChoices) => wrapper.setProps({ modelValue: value }),
      ...props,
    },
    global: { stubs },
  });
  return wrapper;
}

const model = (wrapper: ReturnType<typeof render>) => wrapper.props("modelValue") as PantryChoices;
const row = (wrapper: ReturnType<typeof render>, name: string) =>
  wrapper.findAll(".cook-pantry__item").find(r => r.text().includes(name))!;
const button = (wrapper: { findAll: (selector: string) => DOMWrapper<Element>[] }, label: string) =>
  wrapper.findAll("button").find(b => b.text() === label)!;

describe("CookPantryCheck", () => {
  test("lists each item with its amount, and no outcome is chosen", () => {
    const wrapper = render();

    expect(wrapper.text()).toContain("From your pantry");
    expect(row(wrapper, "Butter").text()).toContain("250 grams");
    expect(row(wrapper, "Onions").text()).toContain("3");
    const pressed = wrapper.findAll(".cook-pantry__item button").map(b => b.attributes("aria-pressed"));
    expect(pressed).toEqual(["false", "false", "false", "false"]);
  });

  test("an outcome is one tap, a second tap on it clears it", async () => {
    const wrapper = render();

    await button(row(wrapper, "Butter"), "Used up").trigger("click");
    expect(model(wrapper).outcomes).toEqual({ "p-butter": "used_up" });
    expect(button(row(wrapper, "Butter"), "Used up").attributes("aria-pressed")).toBe("true");

    await button(row(wrapper, "Butter"), "Some left").trigger("click");
    expect(model(wrapper).outcomes).toEqual({ "p-butter": "some_left" });

    await button(row(wrapper, "Butter"), "Some left").trigger("click");
    expect(model(wrapper).outcomes).toEqual({});
  });

  test("no pantry list without items, the leftovers stay", () => {
    const wrapper = render({}, { items: [] });

    expect(wrapper.text()).not.toContain("From your pantry");
    expect(wrapper.text()).toContain("Leftovers");
  });

  test("the portions stepper stays within 0 and 50", async () => {
    const wrapper = render({ portions: 1 });
    const output = () => wrapper.find(".cook-pantry__portions").text();

    expect(output()).toBe("1 portion");
    await wrapper.find("[aria-label='Fewer portions']").trigger("click");
    expect(model(wrapper).portions).toBe(0);
    expect(output()).toBe("No leftovers");
    expect(wrapper.find("[aria-label='Fewer portions']").attributes("aria-disabled")).toBe("true");
    await wrapper.find("[aria-label='Fewer portions']").trigger("click");
    expect(model(wrapper).portions).toBe(0);

    await wrapper.setProps({ modelValue: { ...model(wrapper), portions: 49 } });
    await wrapper.find("[aria-label='More portions']").trigger("click");
    expect(model(wrapper).portions).toBe(50);
    expect(output()).toBe("50 portions");
    await wrapper.find("[aria-label='More portions']").trigger("click");
    expect(model(wrapper).portions).toBe(50);
  });

  test("fridge or freezer, one of them always chosen", async () => {
    const wrapper = render();
    const location = () => wrapper.findAll(".cook-pantry__location button").map(b => [b.text(), b.attributes("aria-pressed")]);

    expect(location()).toEqual([["Fridge", "true"], ["Freezer", "false"]]);
    await button(wrapper, "Freezer").trigger("click");
    expect(model(wrapper).location).toBe("freezer");
    await button(wrapper, "Freezer").trigger("click");
    expect(model(wrapper).location).toBe("freezer");
  });

  test("disabled: nothing changes", async () => {
    const wrapper = render({}, { disabled: true });

    await button(row(wrapper, "Butter"), "Used up").trigger("click");
    await wrapper.find("[aria-label='More portions']").trigger("click");
    await button(wrapper, "Freezer").trigger("click");
    expect(model(wrapper)).toEqual({ outcomes: {}, quantities: {}, substitutes: {}, portions: 2, location: "fridge" });
  });

  describe("proposals", () => {
    const grams = { id: "u-g", name: "g", pluralName: "g" };
    const flour = item("p-flour", "Flour", { quantity: 1000, unit: grams, foodId: "f-flour" });
    const proposal = (extra: Partial<PantryProposal> = {}): PantryProposal => ({
      pantryItemId: "p-flour",
      used: 200,
      proposedQuantity: 800,
      proposedOutcome: "some_left",
      reason: "subtracted",
      ...extra,
    });

    test("shows the proposed amount and preselects the proposed chip", () => {
      const wrapper = render(
        { outcomes: { "p-flour": "some_left" }, quantities: { "p-flour": 800 } },
        { items: [flour], proposals: [proposal()] },
      );

      expect(row(wrapper, "Flour").text()).toContain("1,000 g → 800 g");
      expect(button(row(wrapper, "Flour"), "Some left").attributes("aria-pressed")).toBe("true");
      expect(button(row(wrapper, "Flour"), "Used up").attributes("aria-pressed")).toBe("false");
    });

    test("an unchanged proposed quantity shows only the current amount", () => {
      const wrapper = render({}, { items: [flour], proposals: [proposal({ proposedQuantity: 1000 })] });

      expect(row(wrapper, "Flour").text()).toContain("1,000 g");
      expect(row(wrapper, "Flour").text()).not.toContain("→");
    });

    test("Some left on a used-up proposal starts from the current quantity", async () => {
      const wrapper = render(
        { outcomes: { "p-flour": "used_up" } },
        { items: [flour], proposals: [proposal({ proposedOutcome: "used_up", proposedQuantity: null })] },
      );

      await button(row(wrapper, "Flour"), "Some left").trigger("click");

      expect(model(wrapper).outcomes).toEqual({ "p-flour": "some_left" });
      expect(model(wrapper).quantities).toEqual({ "p-flour": 1000 });
    });

    test("editing the amount updates quantities", async () => {
      const wrapper = render(
        { outcomes: { "p-flour": "some_left" }, quantities: { "p-flour": 800 } },
        { items: [flour], proposals: [proposal()] },
      );

      await row(wrapper, "Flour").find(".cook-pantry__amount-edit").trigger("click");
      const input = row(wrapper, "Flour").find("input[type=number]");
      expect(input.attributes("min")).toBe("0");
      await input.setValue("650");

      expect(model(wrapper).quantities).toEqual({ "p-flour": 650 });
    });

    test("a units_differ row shows the hint", () => {
      const wrapper = render({}, { items: [flour], proposals: [proposal({ reason: "units_differ", proposedQuantity: 1000 })] });
      const other = render({}, { items: [flour], proposals: [proposal()] });

      expect(row(wrapper, "Flour").text()).toContain("Units don't compare, amount kept");
      expect(row(other, "Flour").text()).not.toContain("Units don't compare");
    });

    test("a none proposal has no chip pressed", () => {
      const wrapper = render(
        {},
        { items: [flour], proposals: [proposal({ proposedOutcome: "none", proposedQuantity: null, reason: "no_quantity" })] },
      );

      const pressed = row(wrapper, "Flour").findAll("button").map(b => b.attributes("aria-pressed"));
      expect(pressed).toEqual(["false", "false"]);
    });

    test("picking a substitute sets substitutes[ref], oldest suggestions first", async () => {
      const oil = item("p-oil", "Olive oil", { foodId: "f-oil" });
      const butter = item("p-butter", "Butter", { foodId: "f-butter" });
      const unmatched: UnmatchedIngredient = {
        referenceId: "ref-1",
        food: { id: "f-ghee", name: "Ghee" },
        substituteFoodIds: ["f-oil"],
      };
      const wrapper = render({}, { items: [flour], unmatched: [unmatched], pantry: [flour, butter, oil] });

      expect(wrapper.text()).toContain("Ghee: not in your pantry");
      await button(wrapper, "Used something else?").trigger("click");
      const options = wrapper.findAll(".cook-pantry__picker button").map(b => b.text());
      expect(options).toEqual(["Olive oil", "Butter"]);

      await wrapper.findAll(".cook-pantry__picker button")[0]!.trigger("click");

      expect(model(wrapper).substitutes).toEqual({ "ref-1": "p-oil" });
    });

    test("a picked row says what it replaces and × undoes it", async () => {
      const oil = item("p-oil", "Olive oil", { quantity: 500 });
      const unmatched: UnmatchedIngredient = { referenceId: "ref-1", food: { id: "f-ghee", name: "Ghee" } };
      const wrapper = render({ substitutes: { "ref-1": "p-oil" } }, { items: [], unmatched: [unmatched], pantry: [oil] });
      await wrapper.setProps({
        items: [oil],
        unmatched: [],
        proposals: [proposal({ pantryItemId: "p-oil", replacesReferenceId: "ref-1", proposedQuantity: null, proposedOutcome: "none" })],
      });

      expect(row(wrapper, "Olive oil").text()).toContain("instead of Ghee");
      await row(wrapper, "Olive oil").find(".cook-pantry__undo").trigger("click");

      expect(model(wrapper).substitutes).toEqual({});
    });
  });
});
