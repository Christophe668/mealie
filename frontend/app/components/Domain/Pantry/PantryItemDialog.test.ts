import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h, nextTick, ref } from "vue";
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
    const cancel = wrapper.findAll("button").find(b => b.text() === "Cancel")!;
    expect(cancel.attributes("aria-disabled")).toBe("true");
    await cancel.trigger("click");
    expect(wrapper.emitted("update:modelValue")).toBeUndefined();
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

  test("closing gives focus back to what opened it", async () => {
    const stubsWithModel = { "v-dialog": { props: ["modelValue"], template: "<div v-if=\"modelValue\"><slot /></div>" } };
    const open = ref(false);
    const Host = defineComponent(() => () => [
      h("button", { class: "opener", onClick: () => (open.value = true) }, "Milk"),
      h(PantryItemDialog, {
        "item": milk,
        "units": [],
        "saveItem": async () => true,
        "modelValue": open.value,
        "onUpdate:modelValue": (value: boolean) => (open.value = value),
      }),
    ]);
    const wrapper = mount(Host, { global: { stubs: stubsWithModel }, attachTo: document.body });

    const opener = wrapper.find(".opener");
    (opener.element as HTMLElement).focus();
    await opener.trigger("click");
    await nextTick();
    (wrapper.find("input[type=text]").element as HTMLElement).focus();

    await wrapper.findAll("button").find(b => b.text() === "Cancel")!.trigger("click");
    await flushPromises();

    expect(wrapper.find("form").exists()).toBe(false);
    expect(document.activeElement).toBe(opener.element);
    wrapper.unmount();
  });
});
