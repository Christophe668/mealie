import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import PantryItemDialog from "./PantryItemDialog.vue";
import type { PantryItemOut } from "~/lib/api/types/household";

const stubs = { "v-dialog": { template: "<div><slot /></div>" } };
const milk: PantryItemOut = { id: "milk", name: "Milk", groupId: "g", householdId: "h", location: "fridge", source: "manual" };

function render(save: (id: string, data: unknown) => Promise<boolean>) {
  return mount(PantryItemDialog, {
    props: { "item": milk, "units": [], "saveItem": save, "modelValue": true, "onUpdate:modelValue": vi.fn() },
    global: { stubs },
    attachTo: document.body,
  });
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("PantryItemDialog", () => {
  test("stays open while the save runs, keeps the typed values when it fails, closes when it succeeds", async () => {
    let finish!: (ok: boolean) => void;
    const save = vi.fn(() => new Promise<boolean>(r => (finish = r)));
    const wrapper = render(save);

    await wrapper.find("input[type=text]").setValue("Oat milk");
    await wrapper.find("form").trigger("submit");
    expect(save).toHaveBeenCalledExactlyOnceWith("milk", expect.objectContaining({ name: "Oat milk" }));
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    // A second submit while saving is ignored, and the button says it is busy.
    expect(wrapper.find("button[type=submit]").attributes("aria-disabled")).toBe("true");
    await wrapper.find("form").trigger("submit");
    expect(save).toHaveBeenCalledOnce();

    finish(false);
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
    expect(wrapper.find<HTMLInputElement>("input[type=text]").element.value).toBe("Oat milk");

    await wrapper.find("form").trigger("submit");
    finish(true);
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]]);
  });
});
