import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import DsPlaceChips from "./DsPlaceChips.vue";

function render(modelValue = "fridge") {
  return mount(DsPlaceChips, { props: { modelValue } });
}

describe("DsPlaceChips", () => {
  test("renders four radios in a radiogroup with translated labels", () => {
    const wrapper = render();

    expect(wrapper.attributes("role")).toBe("radiogroup");
    const radios = wrapper.findAll("[role=radio]");
    expect(radios.map(r => r.text())).toEqual(["Fridge", "Freezer", "Cupboard", "Other"]);
  });

  test("only the v-model place is checked and tabbable", () => {
    const radios = render("freezer").findAll("[role=radio]");

    expect(radios.map(r => r.attributes("aria-checked"))).toEqual(["false", "true", "false", "false"]);
    expect(radios.map(r => r.attributes("tabindex"))).toEqual(["-1", "0", "-1", "-1"]);
  });

  test("clicking a chip emits its place", async () => {
    const wrapper = render();

    await wrapper.findAll("[role=radio]")[2]!.trigger("click");

    expect(wrapper.emitted("update:modelValue")).toEqual([["cupboard"]]);
  });

  test("arrow keys move the selection and wrap around", async () => {
    const wrapper = render("other");

    await wrapper.findAll("[role=radio]")[3]!.trigger("keydown", { key: "ArrowRight" });
    expect(wrapper.emitted("update:modelValue")![0]).toEqual(["fridge"]);

    await wrapper.findAll("[role=radio]")[3]!.trigger("keydown", { key: "ArrowLeft" });
    expect(wrapper.emitted("update:modelValue")![1]).toEqual(["cupboard"]);
  });
});
