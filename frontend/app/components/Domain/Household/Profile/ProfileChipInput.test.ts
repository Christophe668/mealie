import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import ProfileChipInput from "./ProfileChipInput.vue";

const stubs = { "v-icon": { template: "<i />" } };

function render(modelValue: string[] = [], tone: "neutral" | "accent" = "neutral") {
  const wrapper = mount(ProfileChipInput, {
    props: {
      modelValue,
      "label": "Allergies",
      tone,
      "onUpdate:modelValue": (value: string[]) => wrapper.setProps({ modelValue: value }),
    },
    global: { stubs },
  });
  return wrapper;
}

const chips = (wrapper: ReturnType<typeof render>) => wrapper.findAll("li").map(li => li.text().trim());

describe("ProfileChipInput", () => {
  test("Enter adds a chip and clears the field", async () => {
    const wrapper = render();
    const input = wrapper.find("input");

    await input.setValue("  peanuts ");
    await input.trigger("keydown", { key: "Enter" });

    expect(chips(wrapper)).toEqual(["peanuts"]);
    expect((input.element as HTMLInputElement).value).toBe("");
  });

  test("a comma adds what was typed before it, also several at once", async () => {
    const wrapper = render(["milk"]);
    const input = wrapper.find("input");

    await input.setValue("eggs,");
    expect(chips(wrapper)).toEqual(["milk", "eggs"]);

    await input.setValue("sesame, shellfish,");
    expect(chips(wrapper)).toEqual(["milk", "eggs", "sesame", "shellfish"]);
  });

  test("drops duplicates whatever their case, keeping the first spelling", async () => {
    const wrapper = render(["Peanuts"]);
    const input = wrapper.find("input");

    await input.setValue("peanuts");
    await input.trigger("keydown", { key: "Enter" });
    await input.setValue("Milk, MILK,");

    expect(chips(wrapper)).toEqual(["Peanuts", "Milk"]);
    expect(wrapper.emitted("update:modelValue")).toEqual([[["Peanuts", "Milk"]]]);
  });

  test("leaving the field keeps what was typed", async () => {
    const wrapper = render();
    const input = wrapper.find("input");

    await input.setValue("gluten");
    await input.trigger("blur");

    expect(chips(wrapper)).toEqual(["gluten"]);
  });

  test("× removes that chip only", async () => {
    const wrapper = render(["milk", "eggs", "soy"]);

    await wrapper.find("button[aria-label='Remove eggs']").trigger("click");

    expect(chips(wrapper)).toEqual(["milk", "soy"]);
  });

  test("the accent tone is only used when asked for", () => {
    expect(render(["peanuts"], "accent").find(".ds-chip--accent").exists()).toBe(true);
    expect(render(["olives"]).find(".ds-chip--accent").exists()).toBe(false);
  });
});
