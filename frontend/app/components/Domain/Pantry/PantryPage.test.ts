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
// The list itself is covered by PantryList.test.ts; here it only needs to ask for a removal or a move.
vi.mock("~/components/Domain/Pantry/PantryList.vue", () => ({
  default: {
    name: "PantryList",
    props: ["byLocation"],
    emits: ["remove", "move"],
    template: "<div><button class=\"remove-milk\" @click=\"$emit('remove', byLocation[0].items[0])\">Remove</button>"
      + "<button class=\"milk-to-freezer\" @click=\"$emit('move', 'milk', 'freezer')\">Freezer</button>"
      + "<button class=\"milk-to-fridge\" @click=\"$emit('move', 'milk', 'fridge')\">Fridge</button></div>",
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

  test("a drop on another place saves the new location; a drop on its own place saves nothing", async () => {
    const wrapper = await render();
    await flushPromises();

    await wrapper.find(".milk-to-fridge").trigger("click");
    expect(pantry.current.update).not.toHaveBeenCalled();

    await wrapper.find(".milk-to-freezer").trigger("click");
    expect(pantry.current.update).toHaveBeenCalledWith("milk", { location: "freezer" });
  });
});

describe("pantry page freshness, search and filters", () => {
  const daysAgo = (days: number) => {
    const date = new Date();
    date.setDate(date.getDate() - days);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  };
  const bread: PantryItemOut = {
    id: "bread",
    name: "Baguette",
    groupId: "g",
    householdId: "h",
    location: "cupboard",
    boughtOn: daysAgo(6),
    shelfLife: { openedDays: 2, unopenedDays: 2, source: "typical" },
  };
  const garlic: PantryItemOut = {
    id: "garlic",
    name: "Ail",
    groupId: "g",
    householdId: "h",
    location: "cupboard",
    openedOn: daysAgo(8),
    shelfLife: { openedDays: 7, unopenedDays: 60, source: "typical" },
  };

  beforeEach(() => {
    pantry.current.items.value = [milk, bread, garlic];
    pantry.current.byLocation.value = [
      { location: "fridge", items: [milk] },
      { location: "cupboard", items: [bread, garlic] },
    ];
  });

  test("the summary counts what is probably past and what to check", async () => {
    const wrapper = await render();

    expect(wrapper.find(".pantry-page__summary").text().replace(/\s+/g, " "))
      .toBe("3 items · 1 probably past it · 1 to check");
  });

  test("Use first shows the items that need attention, worst first, with the keeping time", async () => {
    const wrapper = await render();
    const cards = wrapper.findAll(".pantry-use-first__card");

    expect(cards.map(c => c.find(".pantry-use-first__name").text())).toEqual(["Baguette", "Ail"]);
    expect(cards[0]!.find(".pantry-use-first__tag").text()).toBe("Probably past it");
    expect(cards[0]!.find(".pantry-use-first__meta").text()).toBe("Bought 6 days ago · keeps about 2 days");
  });

  test("Throw away on a card removes the item", async () => {
    const wrapper = await render();

    await wrapper.find(".pantry-use-first__card button").trigger("click");
    await flushPromises();

    expect(pantry.current.remove).toHaveBeenCalledWith("bread");
  });

  test("the To check chip keeps only the items that need attention", async () => {
    const wrapper = await render();
    const chip = wrapper.findAll(".pantry-page__chip").find(c => c.text().startsWith("To check"))!;

    expect(chip.text()).toBe("To check 2");
    await chip.trigger("click");

    const groups = wrapper.findComponent({ name: "PantryList" }).props("byLocation") as Array<{ items: PantryItemOut[] }>;
    expect(groups.flatMap(g => g.items.map(i => i.id))).toEqual(["bread", "garlic"]);
    // Filtering hides the Use first row; the list shows what is left.
    expect(wrapper.find(".pantry-use-first").exists()).toBe(false);
  });

  test("search ignores accents and case, and says when nothing matches", async () => {
    const wrapper = await render();
    const search = wrapper.find(".pantry-page__search-input");

    await search.setValue("BAGUÉTTE");
    expect(wrapper.find(".pantry-use-first").exists()).toBe(false);
    expect(wrapper.find(".pantry-page__none").exists()).toBe(false);

    await search.setValue("candles");
    expect(wrapper.find(".pantry-page__none").text()).toBe("Nothing in the pantry matches “candles”.");
  });
});
