import { mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import ShopBought from "./ShopBought.vue";
import ShopList from "./ShopList.vue";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";
import { useLocales } from "~/composables/use-locales";

vi.mock("~/composables/use-locales");

const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

function item(id: string, note: string, checked: boolean): ShoppingListItemOut {
  return { id, shoppingListId: "list", groupId: "g", householdId: "h", checked, note, quantity: 0 };
}

const butter = item("butter", "Butter", true);
const bread = item("bread", "Bread", true);
const foil = item("foil", "Kitchen foil", false);

function list(items: ShoppingListItemOut[]): ShoppingListOut {
  return { id: "list", name: "Weekly shop", groupId: "g", userId: "u", householdId: "h", labelSettings: [], recipeReferences: [], listItems: items };
}

const putAwayButton = (wrapper: { findAll: (s: string) => any[] }) =>
  wrapper.findAll("button").find((b: any) => b.text() === "Put away");

beforeEach(() => {
  vi.mocked(useLocales).mockReturnValue({
    locales: [{ value: "en-US", pluralFoodHandling: "without-unit" }],
    locale: { value: "en-US" },
  } as any);
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ShopBought", () => {
  test("Put away sits next to Clear bought items and asks the parent to put the bought items away", async () => {
    const wrapper = mount(ShopBought, { props: { items: [butter, bread], recipeNames: new Map() }, global: { stubs } });

    const button = putAwayButton(wrapper);
    expect(button).toBeDefined();
    expect(button.attributes("aria-label")).toBe("Put away 2 bought items in the pantry");
    await button.trigger("click");
    expect(wrapper.emitted("put-away")).toHaveLength(1);
  });

  test("while a put away runs the button is disabled and a click does nothing", async () => {
    const wrapper = mount(ShopBought, { props: { items: [butter], recipeNames: new Map(), putting: true }, global: { stubs } });

    const button = putAwayButton(wrapper);
    expect(button.attributes("aria-disabled")).toBe("true");
    await button.trigger("click");
    expect(wrapper.emitted("put-away")).toBeUndefined();
  });

  test("the list offers Put away only when something is bought, and forwards it", async () => {
    const withBought = mount(ShopList, { props: { list: list([foil, butter]), byLabel: [] }, global: { stubs } });
    await putAwayButton(withBought).trigger("click");
    expect(withBought.emitted("putAway")).toHaveLength(1);

    const nothingBought = mount(ShopList, { props: { list: list([foil]), byLabel: [] }, global: { stubs } });
    expect(putAwayButton(nothingBought)).toBeUndefined();
  });

  test("when the Bought section empties under the focused button, focus lands on the first open row", async () => {
    const wrapper = mount(ShopList, {
      props: { list: list([foil, butter]), byLabel: [{ label: null, items: [foil] }] },
      global: { stubs },
      attachTo: document.body,
    });

    const button = putAwayButton(wrapper);
    (button.element as HTMLElement).focus();
    await button.trigger("click");
    await wrapper.setProps({ list: list([foil]) });
    await wrapper.vm.$nextTick();
    expect(document.activeElement?.id).toBe("shop-item-foil");
  });
});
