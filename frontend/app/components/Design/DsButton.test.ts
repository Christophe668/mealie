import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import DsButton from "./DsButton.vue";

// NuxtLink and v-icon are registered by Nuxt/Vuetify at runtime; tests stand them in with plain elements.
const stubs = {
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
  "v-icon": { props: ["icon"], template: "<i class=\"v-icon\" />" },
};

function render(props: Record<string, unknown> = {}, attrs: Record<string, unknown> = {}) {
  return mount(DsButton, {
    props,
    attrs,
    slots: { default: "Start cooking" },
    global: { stubs },
  });
}

describe("DsButton", () => {
  test("renders a native button with its label", () => {
    const wrapper = render();

    expect(wrapper.element.tagName).toBe("BUTTON");
    expect(wrapper.attributes("type")).toBe("button");
    expect(wrapper.text()).toBe("Start cooking");
  });

  test("defaults to the primary variant at medium size", () => {
    const wrapper = render();

    expect(wrapper.classes()).toContain("ds-btn--primary");
    expect(wrapper.classes()).toContain("ds-btn--md");
  });

  test.each(["primary", "dark", "line", "ghost"] as const)("applies the %s variant", (variant) => {
    const wrapper = render({ variant });

    expect(wrapper.classes()).toContain(`ds-btn--${variant}`);
  });

  test("applies the large size and block modifiers", () => {
    const wrapper = render({ size: "lg", block: true });

    expect(wrapper.classes()).toContain("ds-btn--lg");
    expect(wrapper.classes()).toContain("ds-btn--block");
  });

  test("disabled sets aria-disabled, stays focusable and swallows clicks", async () => {
    let clicks = 0;
    const wrapper = render({ disabled: true }, { onClick: () => clicks++ });

    expect(wrapper.attributes("aria-disabled")).toBe("true");
    expect(wrapper.attributes("disabled")).toBeUndefined();

    await wrapper.trigger("click");
    expect(clicks).toBe(0);
  });

  test("an enabled button forwards clicks and has no aria-disabled", async () => {
    let clicks = 0;
    const wrapper = render({}, { onClick: () => clicks++ });

    expect(wrapper.attributes("aria-disabled")).toBeUndefined();
    await wrapper.trigger("click");
    expect(clicks).toBe(1);
  });

  test("renders a link when given a destination", () => {
    const wrapper = render({ to: "/shopping-lists" });

    expect(wrapper.element.tagName).toBe("A");
    expect(wrapper.attributes("href")).toBe("/shopping-lists");
    expect(wrapper.classes()).toContain("ds-btn");
  });

  test("renders a leading icon when given one", () => {
    const wrapper = render({ icon: "createAlt" });

    expect(wrapper.find(".v-icon").exists()).toBe(true);
  });
});
