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

  test("a full list keeps what did not fit in the field and says why", async () => {
    const full = Array.from({ length: 29 }, (_, i) => `item ${i}`);
    const wrapper = render(full);
    const input = wrapper.find("input");

    await input.setValue("last one, one too many");
    await input.trigger("keydown", { key: "Enter" });

    expect(chips(wrapper)).toHaveLength(30);
    expect(chips(wrapper).at(-1)).toBe("last one");
    expect((input.element as HTMLInputElement).value).toBe("one too many");
    expect(wrapper.find(".profile-chips__hint").text()).toBe("This list is full (30 at most). Remove one to add another.");
    expect(input.attributes("aria-describedby")).toBe(wrapper.find(".profile-chips__hint").attributes("id"));

    // typing again clears the hint
    await input.setValue("one too many!");
    expect(wrapper.find(".profile-chips__hint").text()).toBe("");
  });

  test("an entry over 60 characters is shortened, and the field says so", async () => {
    const wrapper = render();
    const input = wrapper.find("input");

    await input.setValue(`${"a".repeat(59)} bcd`);
    await input.trigger("keydown", { key: "Enter" });

    expect(chips(wrapper)).toEqual(["a".repeat(59)]);
    expect(wrapper.find(".profile-chips__hint").text()).toBe("Shortened to 60 characters.");
  });

  test("an emoji at the 60-character boundary is kept whole or dropped whole, never split", async () => {
    const wrapper = render();
    const input = wrapper.find("input");

    // 59 letters and a peanut: 60 code points (61 UTF-16 units), so it fits as is.
    await input.setValue(`${"a".repeat(59)}\u{1F95C}`);
    await input.trigger("keydown", { key: "Enter" });
    // 60 letters and a peanut: the peanut goes, with no half surrogate left behind.
    await input.setValue(`${"b".repeat(60)}\u{1F95C}`);
    await input.trigger("keydown", { key: "Enter" });

    expect(chips(wrapper)).toEqual([`${"a".repeat(59)}\u{1F95C}`, "b".repeat(60)]);
    expect(chips(wrapper).join("")).not.toMatch(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])/);
  });

  test("Enter that confirms an input method's composition adds nothing", async () => {
    const wrapper = render();
    const input = wrapper.find("input");

    await input.setValue("にんじん");
    await input.trigger("keydown", { key: "Enter", isComposing: true });
    expect(chips(wrapper)).toEqual([]);

    await input.trigger("keydown", { key: "Enter" });
    expect(chips(wrapper)).toEqual(["にんじん"]);
  });

  test("duplicates are found the way the server finds them: NFC, case and ß", async () => {
    const wrapper = render(["Straße", "Zo\u00e9"]);
    const input = wrapper.find("input");

    await input.setValue("STRASSE, ZOE\u0301,");

    expect(chips(wrapper)).toEqual(["Straße", "Zo\u00e9"]);
  });

  test("the accent tone is only used when asked for", () => {
    expect(render(["peanuts"], "accent").find(".ds-chip--accent").exists()).toBe(true);
    expect(render(["olives"]).find(".ds-chip--accent").exists()).toBe(false);
  });
});
