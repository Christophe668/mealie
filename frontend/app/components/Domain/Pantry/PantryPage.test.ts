import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ref } from "vue";
import type { PantryItemOut } from "~/lib/api/types/household";

// The page wires the pantry composable to the Pantry components; the composable is a stand-in here.
const pantry = vi.hoisted(() => ({ current: null as any }));

vi.mock("~/composables/use-pantry", () => ({ usePantry: () => pantry.current }));
vi.mock("~/composables/use-toast", () => ({ alert: { info: vi.fn(), error: vi.fn() } }));
vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ shopping: { lists: { getAll: vi.fn().mockResolvedValue({ data: { items: [] } }) } } }),
}));
vi.mock("~/composables/store", async () => {
  const { ref } = await import("vue");
  return { useUnitStore: () => ({ store: ref([]) }) };
});
// The list itself is covered by PantryList.test.ts; here it only needs to ask for a removal.
vi.mock("~/components/Domain/Pantry/PantryList.vue", () => ({
  default: {
    props: ["byLocation"],
    emits: ["remove"],
    template: "<button class=\"remove-milk\" @click=\"$emit('remove', byLocation[0].items[0])\">Remove</button>",
  },
}));

const milk: PantryItemOut = { id: "milk", name: "Milk", groupId: "g", householdId: "h", location: "fridge" };

function fakePantry() {
  return {
    items: ref([milk]),
    byLocation: ref([{ location: "fridge", items: [milk] }]),
    loading: ref(false),
    failed: ref(false),
    refresh: vi.fn(),
    add: vi.fn(),
    restore: vi.fn().mockResolvedValue(true),
    update: vi.fn().mockResolvedValue(true),
    remove: vi.fn().mockResolvedValue(true),
    markOpened: vi.fn(),
  };
}

async function render() {
  const { default: PantryPage } = await import("~/pages/household/pantry/index.vue");
  return mount(PantryPage, {
    global: { stubs: { "v-dialog": { template: "<div><slot /></div>" }, "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" } } },
    attachTo: document.body,
  });
}

beforeEach(() => {
  pantry.current = fakePantry();
  vi.stubGlobal("definePageMeta", () => {});
  vi.stubGlobal("useSeoMeta", () => {});
  vi.stubGlobal("useRoute", () => ({ path: "/household/pantry", params: {}, query: {} }));
  vi.stubGlobal("useRouter", () => ({ push: vi.fn(), replace: vi.fn() }));
  vi.stubGlobal("useState", (_key: string, init: () => unknown) => ref(init()));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("pantry page", () => {
  test("Undo after Remove puts the item back once, however often it is pressed", async () => {
    const { alert } = await import("~/composables/use-toast");
    const wrapper = await render();

    await wrapper.find(".remove-milk").trigger("click");
    await flushPromises();
    expect(pantry.current.remove).toHaveBeenCalledWith("milk");

    const [text, , options] = vi.mocked(alert.info).mock.calls.at(-1)!;
    expect(text).toBe("Milk removed");
    options!.action!.onClick();
    options!.action!.onClick();
    expect(pantry.current.restore).toHaveBeenCalledExactlyOnceWith(milk);
  });
});
