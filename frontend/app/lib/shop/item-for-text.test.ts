import { describe, expect, test } from "vitest";
import { itemForText, recipeNamesOf } from "./item-for-text";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";

const t = (key: string, params?: Record<string, unknown>) => `${key}:${JSON.stringify(params)}`;
const item = (recipeIds: string[]): ShoppingListItemOut => ({
  id: "i",
  shoppingListId: "l",
  groupId: "g",
  householdId: "h",
  recipeReferences: recipeIds.map((recipeId, n) => ({ id: `r${n}`, recipeId, shoppingListItemId: "i" })),
});

describe("itemForText", () => {
  const names = new Map([["r1", "Roast chicken"], ["r2", "Soup"]]);

  test("no named recipe gives no line", () => {
    expect(itemForText(item([]), names, t)).toBe("");
    expect(itemForText(item(["unknown"]), names, t)).toBe("");
  });

  test("one recipe, counted once even when referenced twice", () => {
    expect(itemForText(item(["r1", "r1"]), names, t)).toBe("shop.for-recipe:{\"recipe\":\"Roast chicken\"}");
  });

  test("several recipes name the first and count the rest", () => {
    expect(itemForText(item(["r1", "r2"]), names, t)).toBe("shop.for-recipe-and-more:{\"recipe\":\"Roast chicken\",\"count\":1}");
  });
});

describe("recipeNamesOf", () => {
  test("maps the list's recipe ids to their names, skipping nameless ones", () => {
    const list = {
      recipeReferences: [
        { recipeId: "r1", recipe: { name: "Roast chicken" } },
        { recipeId: "r2", recipe: {} },
      ],
    } as unknown as ShoppingListOut;
    expect([...recipeNamesOf(list)]).toEqual([["r1", "Roast chicken"]]);
  });
});
