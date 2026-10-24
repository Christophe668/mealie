import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import ShopList from "./ShopList.vue";
import { shopAisles, toByLabel, updatedAgo } from "~/composables/use-shop";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";
import type { MultiPurposeLabelSummary } from "~/lib/api/types/labels";
import { useLocales } from "~/composables/use-locales";

vi.mock("~/composables/use-locales");

const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

const produce: MultiPurposeLabelSummary = { id: "l-produce", name: "Produce", color: "#4caf50", groupId: "g" };
const dairy: MultiPurposeLabelSummary = { id: "l-dairy", name: "Dairy", color: "#2196f3", groupId: "g" };
const bakery: MultiPurposeLabelSummary = { id: "l-bakery", name: "Bakery", color: "#ff9800", groupId: "g" };

let nextId = 1;
function item(name: string, extra: Partial<ShoppingListItemOut> = {}): ShoppingListItemOut {
  const id = `i${nextId++}`;
  return {
    id,
    shoppingListId: "list",
    groupId: "g",
    householdId: "h",
    checked: false,
    quantity: 0,
    note: "",
    food: { id: `f-${name}`, name },
    foodId: `f-${name}`,
    label: null,
    labelId: null,
    recipeReferences: [],
    ...extra,
  };
}

const potatoes = item("potatoes", {
  quantity: 2,
  unit: { id: "u-kg", name: "kg", fraction: false },
  label: produce,
  labelId: produce.id,
  recipeReferences: [{ id: "rr1", shoppingListItemId: "x", recipeId: "r-chicken" }],
});
const lemons = item("lemon", {
  quantity: 3,
  label: produce,
  labelId: produce.id,
  recipeReferences: [
    { id: "rr2", shoppingListItemId: "x", recipeId: "r-chicken" },
    { id: "rr3", shoppingListItemId: "x", recipeId: "r-tart" },
  ],
});
const milk = item("milk", { label: dairy, labelId: dairy.id });
const foil = item("", { food: null, foodId: null, note: "Kitchen foil" });
const butter = item("butter", { checked: true, label: dairy, labelId: dairy.id, updatedAt: "2026-10-24T09:00:00Z" });
const bread = item("bread", { checked: true, label: bakery, labelId: bakery.id, updatedAt: "2026-10-24T10:00:00Z" });

function makeList(items: ShoppingListItemOut[]): ShoppingListOut {
  return {
    id: "list",
    name: "Weekly shop",
    groupId: "g",
    userId: "u",
    householdId: "h",
    listItems: items,
    // The list's own aisle order: Dairy before Produce, which is not alphabetical and not item order.
    labelSettings: [
      { id: "s1", shoppingListId: "list", labelId: dairy.id, position: 0, label: dairy },
      { id: "s2", shoppingListId: "list", labelId: bakery.id, position: 1, label: bakery },
      { id: "s3", shoppingListId: "list", labelId: produce.id, position: 2, label: produce },
    ],
    recipeReferences: [
      { id: "lr1", shoppingListId: "list", recipeId: "r-chicken", recipeQuantity: 1, recipe: { id: "r-chicken", name: "Roast chicken" } },
      { id: "lr2", shoppingListId: "list", recipeId: "r-tart", recipeQuantity: 1, recipe: { id: "r-tart", name: "Lemon tart" } },
    ],
  };
}

const allItems = [potatoes, lemons, milk, foil, butter, bread];

/** What the upstream composable produces: unchecked items keyed by label name, the unlabelled bucket first. */
function upstreamItemsByLabel(): Record<string, ShoppingListItemOut[]> {
  return { "No label": [foil], "Dairy": [milk], "Produce": [potatoes, lemons] };
}

function render(items = allItems) {
  const list = makeList(items);
  return mount(ShopList, {
    props: { list, byLabel: toByLabel(upstreamItemsByLabel(), list) },
    global: { stubs },
    attachTo: document.body,
  });
}

const aisleNames = (wrapper: ReturnType<typeof render>) => wrapper.findAll(".shop-aisle__name").map(h => h.text());

beforeEach(() => {
  vi.mocked(useLocales).mockReturnValue({
    locales: [{ value: "en-US", pluralFoodHandling: "without-unit" }],
    locale: { value: "en-US" },
  } as any);
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ShopList", () => {
  test("groups by label in the list's label order, unlabelled last as Other", () => {
    const wrapper = render();

    expect(aisleNames(wrapper)).toEqual(["Dairy", "Produce", "Other"]);
    const produceAisle = wrapper.findAll(".shop-aisle")[1]!;
    expect(produceAisle.findAll(".shop-row__name").map(n => n.text())).toEqual(["potatoes", "lemon"]);
  });

  test("an aisle header shows its open count, and aisles with nothing open are hidden", () => {
    const wrapper = render();

    expect(wrapper.findAll(".shop-aisle__count").map(c => c.text())).toEqual(["1", "2", "1"]);
    // Bakery only holds a bought item, so it has no aisle of its own.
    expect(aisleNames(wrapper)).not.toContain("Bakery");
  });

  test("checked items move to the Bought section, newest first, collapsed until opened", async () => {
    const wrapper = render();

    const toggle = wrapper.find(".shop-bought__toggle");
    expect(toggle.text()).toBe("Bought (2)");
    expect(toggle.attributes("aria-expanded")).toBe("false");
    expect(wrapper.find(".shop-bought__list").isVisible()).toBe(false);
    expect(wrapper.findAll(".shop-aisle .shop-row__name").map(n => n.text())).not.toContain("butter");

    await toggle.trigger("click");
    expect(toggle.attributes("aria-expanded")).toBe("true");
    expect(wrapper.findAll(".shop-bought .shop-row__name").map(n => n.text())).toEqual(["bread", "butter"]);
  });

  test("tapping a row toggles the item through the handler, once", async () => {
    const wrapper = render();

    await wrapper.findAll(".shop-aisle")[1]!.find(".shop-row__label").trigger("click");
    expect(wrapper.emitted("toggle")).toEqual([[potatoes]]);
  });

  test("the row's checkbox is a real labelled checkbox that toggles through the handler", async () => {
    const wrapper = render();
    const box = wrapper.find<HTMLInputElement>("#shop-item-" + milk.id);

    expect(box.attributes("type")).toBe("checkbox");
    expect(wrapper.find(`label[for="shop-item-${milk.id}"]`).exists()).toBe(true);
    await box.trigger("click");
    expect(wrapper.emitted("toggle")).toEqual([[milk]]);
    // Controlled: the box shows the item's state until the parent updates the item.
    expect(box.element.checked).toBe(false);
  });

  test("un-ticking a bought item toggles it through the same handler", async () => {
    const wrapper = render();

    await wrapper.find(".shop-bought__toggle").trigger("click");
    await wrapper.find(".shop-bought .shop-row__label").trigger("click");
    expect(wrapper.emitted("toggle")).toEqual([[bread]]);
  });

  test("a row shows the recipes it is for and its quantity", () => {
    const wrapper = render();
    const rows = wrapper.findAll(".shop-aisle")[1]!.findAll(".shop-row");

    expect(rows[0]!.find(".shop-row__for").text()).toBe("For Roast chicken");
    expect(rows[0]!.find(".shop-row__qty").text()).toBe("2 kg");
    expect(rows[1]!.find(".shop-row__for").text()).toBe("For Roast chicken and 1 more");
    expect(rows[1]!.find(".shop-row__qty").text()).toBe("3");
    // No recipe, no quantity: neither line is rendered.
    const foilRow = wrapper.findAll(".shop-aisle")[2]!.find(".shop-row");
    expect(foilRow.find(".shop-row__name").text()).toBe("Kitchen foil");
    expect(foilRow.find(".shop-row__for").exists()).toBe(false);
    expect(foilRow.find(".shop-row__qty").exists()).toBe(false);
  });

  test("the row's more button asks to edit the item", async () => {
    const wrapper = render();

    await wrapper.find(`[data-item-id="${milk.id}"] .shop-row__more`).trigger("click");
    expect(wrapper.emitted("edit")).toEqual([[milk]]);
    expect(wrapper.emitted("toggle")).toBeUndefined();
  });

  test("a long press asks to edit instead of toggling", async () => {
    vi.useFakeTimers();
    try {
      const wrapper = render();
      const label = wrapper.find(`[data-item-id="${milk.id}"] .shop-row__label`);

      await label.trigger("pointerdown", { pointerType: "touch" });
      vi.advanceTimersByTime(600);
      await label.trigger("pointerup");
      await label.trigger("click");

      expect(wrapper.emitted("edit")).toEqual([[milk]]);
      expect(wrapper.emitted("toggle")).toBeUndefined();
    }
    finally {
      vi.useRealTimers();
    }
  });

  test("quick add submits the text on Enter and clears the field", async () => {
    const wrapper = render();
    const input = wrapper.find<HTMLInputElement>(".shop-quick-add__input");

    await input.setValue("  2 kg potatoes ");
    await wrapper.find("form.shop-quick-add").trigger("submit");
    expect(wrapper.emitted("add")).toEqual([["2 kg potatoes"]]);
    expect(input.element.value).toBe("");

    await wrapper.find("form.shop-quick-add").trigger("submit");
    expect(wrapper.emitted("add")).toHaveLength(1);
  });

  test("Clear bought items asks the parent to clear", async () => {
    const wrapper = render();

    await wrapper.find(".shop-bought__clear").trigger("click");
    expect(wrapper.emitted("clearBought")).toHaveLength(1);
  });

  test("no Bought section when nothing is bought; an empty list says what to do", () => {
    const wrapper = mount(ShopList, {
      props: { list: makeList([]), byLabel: [] },
      global: { stubs },
    });

    expect(wrapper.find(".shop-bought").exists()).toBe(false);
    expect(wrapper.find(".shop-list__empty").text()).toContain("Nothing to buy");
  });
});

describe("shop helpers", () => {
  test("toByLabel maps the composable's label buckets onto label objects, unlabelled as null", () => {
    const list = makeList(allItems);
    const groups = toByLabel(upstreamItemsByLabel(), list);

    expect(groups.map(g => g.label?.name ?? null)).toEqual([null, "Dairy", "Produce"]);
  });

  test("shopAisles keeps only open items and puts labels the list does not order after the ordered ones", () => {
    const list = makeList(allItems);
    const stray: MultiPurposeLabelSummary = { id: "l-stray", name: "Stray", groupId: "g" };
    const aisles = shopAisles(list, [
      { label: stray, items: [item("x", { label: stray, labelId: stray.id })] },
      { label: dairy, items: [milk, butter] },
    ]);

    expect(aisles.map(a => a.label?.name)).toEqual(["Dairy", "Stray"]);
    expect(aisles[0]!.items).toEqual([milk]);
  });

  test("updatedAgo reads naturally from minutes to weeks", () => {
    const now = new Date("2026-10-24T12:00:00Z");

    expect(updatedAgo("2026-10-24T11:59:40Z", now, "en-US")).toBe("now");
    expect(updatedAgo("2026-10-24T11:35:00Z", now, "en-US")).toBe("25 minutes ago");
    expect(updatedAgo("2026-10-24T10:00:00Z", now, "en-US")).toBe("2 hours ago");
    expect(updatedAgo("2026-10-10T12:00:00Z", now, "en-US")).toBe("2 weeks ago");
  });
});
