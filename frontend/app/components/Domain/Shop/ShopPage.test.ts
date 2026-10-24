import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { reactive, ref } from "vue";
import type { ShoppingListOut } from "~/lib/api/types/household";
import { useLocales } from "~/composables/use-locales";

// The page wires the upstream composable to the Shop components. The composable is replaced by a stand-in that
// keeps the same dialog contract (open* sets the state flag, the action is called on confirm).
const page = vi.hoisted(() => ({ current: null as any }));

vi.mock("~/composables/use-locales");
vi.mock("~/composables/shopping-list-page/use-shopping-list-page", () => ({
  useShoppingListPage: () => page.current,
}));
vi.mock("~/composables/shopping-list-page/use-shopping-list-item-editor", () => ({ resolveFood: () => undefined }));
vi.mock("~/composables/store", async () => {
  const { ref } = await import("vue");
  const store = () => ({ store: ref([]) });
  return { useLabelStore: store, useUnitStore: store, useFoodStore: store };
});
vi.mock("~/composables/use-toast", () => ({ alert: { info: vi.fn() } }));
vi.mock("~/composables/use-users/preferences", async () => {
  const { ref } = await import("vue");
  return { useUserExperiencePreferences: () => ref({ lockScreen: false }) };
});
vi.mock("~/composables/use-wake-lock", () => ({ useWakeLock: () => {} }));
vi.mock("vue-draggable-plus", () => ({ VueDraggable: { render: () => null } }));
vi.mock("~/components/Domain/Recipe/RecipeList.vue", () => ({ default: { render: () => null } }));
vi.mock("~/components/Domain/ShoppingList/ShoppingListItemEditor.vue", () => ({ default: { render: () => null } }));
vi.mock("~/components/Domain/ShoppingList/MultiPurposeLabelSection.vue", () => ({ default: { render: () => null } }));

const stubs = {
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
  "v-dialog": { template: "<div><slot /></div>" },
  "v-card": { template: "<div><slot /></div>" },
  "v-card-text": { template: "<div><slot /></div>" },
  "v-btn": { template: "<button><slot /></button>" },
  "v-list-item-action": { template: "<div><slot /></div>" },
  // Shows its content while open and confirms through a button, like BaseDialog's confirm action.
  "BaseDialog": {
    props: ["modelValue"],
    emits: ["confirm", "update:modelValue"],
    template: "<div v-if=\"modelValue\" class=\"base-dialog\"><slot /><button class=\"base-dialog__confirm\" @click=\"$emit('confirm')\">Confirm</button></div>",
  },
};

function makeList(): ShoppingListOut {
  return {
    id: "list",
    name: "Weekly shop",
    groupId: "g",
    userId: "u",
    householdId: "h",
    labelSettings: [],
    recipeReferences: [],
    listItems: [
      { id: "a", shoppingListId: "list", groupId: "g", householdId: "h", checked: false, note: "Kitchen foil", quantity: 0 },
      { id: "b", shoppingListId: "list", groupId: "g", householdId: "h", checked: true, note: "Bin bags", quantity: 0 },
    ],
  };
}

function fakePage() {
  const state = reactive({ checkAllDialog: false, uncheckAllDialog: false, deleteCheckedDialog: false });
  const list = makeList();
  return {
    shoppingList: ref(list),
    state,
    loadingCounter: ref(0),
    isOffline: ref(false),
    itemsByLabel: ref({ "No label": [list.listItems![0]!] }),
    recipeList: ref([]),
    createListItemData: ref({}),
    createListItem: vi.fn(),
    saveListItem: vi.fn(),
    deleteListItem: vi.fn(),
    checkAll: vi.fn(),
    uncheckAll: vi.fn(() => (state.uncheckAllDialog = false)),
    deleteChecked: vi.fn(),
    openCheckAll: () => (state.checkAllDialog = true),
    openUncheckAll: vi.fn(() => (state.uncheckAllDialog = true)),
    openDeleteChecked: () => (state.deleteCheckedDialog = true),
    copyListItems: vi.fn(),
    reorderLabelsDialog: ref(false),
    localLabels: ref(undefined),
    toggleReorderLabelsDialog: vi.fn(),
    saveLabelOrder: vi.fn(),
    cancelLabelOrder: vi.fn(),
    updateLabelOrder: vi.fn(),
    removeRecipeReferenceToList: vi.fn(),
    addRecipeReferenceToList: vi.fn(),
    refresh: vi.fn(),
  };
}

async function render() {
  const { default: ShopPage } = await import("~/pages/shopping-lists/[id].vue");
  return mount(ShopPage, {
    global: { stubs, mocks: { $globals: { icons: {} } } },
    attachTo: document.body,
  });
}

beforeEach(() => {
  page.current = fakePage();
  vi.mocked(useLocales).mockReturnValue({
    locales: [{ value: "en-US", pluralFoodHandling: "without-unit" }],
    locale: { value: "en-US" },
  } as any);
  vi.stubGlobal("definePageMeta", () => {});
  vi.stubGlobal("useSeoMeta", () => {});
  vi.stubGlobal("useRoute", () => ({ path: "/shopping-lists/list", params: { id: "list" }, query: {} }));
  vi.stubGlobal("useRouter", () => ({ push: vi.fn() }));
  vi.stubGlobal("useState", (_key: string, init: () => unknown) => ref(init()));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("shopping list page", () => {
  test("the kebab's put-everything-back item opens the uncheck-all confirm, and confirming calls the composable", async () => {
    const wrapper = await render();

    expect(wrapper.find(".base-dialog").exists()).toBe(false);
    await wrapper.find(".shop-page__more button[aria-haspopup=menu]").trigger("click");
    const item = wrapper.findAll("[role=menuitem]").find(el => el.text() === "Put everything back on the list");
    expect(item).toBeDefined();
    await item!.trigger("click");
    await flushPromises();

    expect(page.current.openUncheckAll).toHaveBeenCalledOnce();
    const dialog = wrapper.find(".base-dialog");
    expect(dialog.text()).toContain("Are you sure you want to uncheck all items?");
    await dialog.find(".base-dialog__confirm").trigger("click");
    expect(page.current.uncheckAll).toHaveBeenCalledOnce();
  });

  test("the open count is the saffron badge and is announced politely", async () => {
    const wrapper = await render();

    expect(wrapper.find(".shop-page__badge").text()).toBe("1 to buy");
    expect(wrapper.find(".shop-page__sr[role=status]").text()).toBe("1 to buy");
  });

  test("undo flips the item as it is now, keeping an edit made since the tick", async () => {
    const { alert } = await import("~/composables/use-toast");
    const wrapper = await render();

    await wrapper.find(".shop-row__label").trigger("click");
    const ticked = page.current.saveListItem.mock.calls[0][0];
    expect(ticked).toMatchObject({ id: "a", checked: true });

    // The composable now holds the ticked item, and the user renamed it before pressing Undo.
    page.current.shoppingList.value.listItems[0] = { ...ticked, note: "Foil, wide roll" };
    const undo = vi.mocked(alert.info).mock.calls.at(-1)![2]!.action!.onClick as () => void;
    undo();
    expect(page.current.saveListItem).toHaveBeenLastCalledWith(expect.objectContaining({ id: "a", checked: false, note: "Foil, wide roll" }));
  });
});
