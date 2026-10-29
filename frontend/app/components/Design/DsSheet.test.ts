import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { ref } from "vue";
import DsSheet from "./DsSheet.vue";

const mobile = ref(false);
vi.mock("vuetify", () => ({ useDisplay: () => ({ mobile }) }));

// Vuetify's overlays teleport and animate; stand them in with a slot wrapper that records which one rendered.
const overlay = (kind: string) => ({
  props: ["modelValue", "persistent", "maxWidth"],
  template: `<div data-overlay="${kind}" :data-persistent="persistent"><slot v-if="modelValue" /></div>`,
});
const stubs = { VDialog: overlay("dialog"), VBottomSheet: overlay("bottom-sheet") };

function render(props: Record<string, unknown> = {}, slots: Record<string, string> = {}) {
  return mount(DsSheet, {
    props: { modelValue: true, title: "Flour", ...props },
    slots: { default: "<button class=\"ds-sheet__action\">Put away</button>", ...slots },
    global: { stubs },
  });
}

describe("DsSheet", () => {
  beforeEach(() => {
    mobile.value = false;
  });

  test("renders the title and the body slot when open", () => {
    const wrapper = render();

    expect(wrapper.find("h2").text()).toBe("Flour");
    expect(wrapper.find(".ds-sheet__action").text()).toBe("Put away");
  });

  test("renders nothing when closed", () => {
    expect(render({ modelValue: false }).find(".ds-sheet").exists()).toBe(false);
  });

  test("the header slot replaces the title block", () => {
    const wrapper = render({}, { header: "<p class=\"custom\">Custom</p>" });

    expect(wrapper.find(".custom").exists()).toBe(true);
    expect(wrapper.find("h2").exists()).toBe(false);
  });

  test("uses a dialog on desktop and a bottom sheet on mobile", () => {
    expect(render().find("[data-overlay]").attributes("data-overlay")).toBe("dialog");

    mobile.value = true;
    expect(render().find("[data-overlay]").attributes("data-overlay")).toBe("bottom-sheet");
  });

  test("Escape closes the sheet", async () => {
    const wrapper = render();

    await wrapper.find(".ds-sheet").trigger("keydown", { key: "Escape" });

    expect(wrapper.emitted("update:modelValue")).toEqual([[false]]);
  });

  test("Escape does not close while busy, and the overlay is persistent", async () => {
    const wrapper = render({ busy: true });

    await wrapper.find(".ds-sheet").trigger("keydown", { key: "Escape" });

    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.find("[data-overlay]").attributes("data-persistent")).toBe("true");
    expect(wrapper.find(".ds-sheet").attributes("aria-busy")).toBe("true");
  });
});
