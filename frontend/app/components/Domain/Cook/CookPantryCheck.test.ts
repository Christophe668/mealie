import { mount } from "@vue/test-utils";
import type { DOMWrapper } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import CookPantryCheck from "./CookPantryCheck.vue";
import type { PantryChoices } from "./CookPantryCheck.vue";
import type { PantryItemOut } from "~/lib/api/types/household";

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

function render(model: Partial<PantryChoices> = {}, props: Partial<{ items: PantryItemOut[]; disabled: boolean }> = {}) {
  const wrapper = mount(CookPantryCheck, {
    props: {
      "items": items,
      "modelValue": { outcomes: {}, portions: 2, location: "fridge", ...model },
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
    expect(model(wrapper)).toEqual({ outcomes: {}, portions: 2, location: "fridge" });
  });
});
