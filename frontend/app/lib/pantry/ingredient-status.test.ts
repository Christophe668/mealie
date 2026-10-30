import { describe, expect, test } from "vitest";
import { ingredientStatus, pantryDetail } from "./ingredient-status";
import type { PantryItemOut } from "~/lib/api/types/household";
import { i18n } from "~/tests/setup";

const t = (key: string, params?: Record<string, unknown>) => i18n.global.t(key, params ?? {});
const today = new Date(2026, 9, 24);

function item(extra: Partial<PantryItemOut> = {}): PantryItemOut {
  return { id: "p1", groupId: "g", householdId: "h", name: "Milk", ...extra };
}

describe("ingredientStatus", () => {
  test("unknown when the ingredient names no food", () => {
    expect(ingredientStatus(undefined, today)).toBeNull();
  });

  test("missing without pantry items", () => {
    expect(ingredientStatus([], today)).toBe("missing");
  });

  test("soon when an item is used by within two days", () => {
    expect(ingredientStatus([item({ useBy: "2026-10-25" })], today)).toBe("soon");
  });

  test("have when the use-by date is far off or absent", () => {
    expect(ingredientStatus([item({ useBy: "2026-11-03" })], today)).toBe("have");
    expect(ingredientStatus([item()], today)).toBe("have");
  });

  test("soon wins when only one of several items is urgent", () => {
    expect(ingredientStatus([item({ useBy: "2026-11-03" }), item({ id: "p2", useBy: "2026-10-24" })], today)).toBe("soon");
  });
});

describe("pantryDetail", () => {
  test("places, then the freshness of the item to use first", () => {
    const items = [
      item({ location: "fridge", useBy: "2026-11-03" }),
      item({ id: "p2", location: "freezer", useBy: "2026-10-25" }),
    ];
    expect(pantryDetail(items, today, t, "en-US")).toBe("Fridge, Freezer · Use by October 25");
  });

  test("places only when no item carries a date; default place is the cupboard", () => {
    expect(pantryDetail([item()], today, t, "en-US")).toBe("Cupboard");
  });

  test("a place is listed once", () => {
    expect(pantryDetail([item({ location: "fridge" }), item({ id: "p2", location: "fridge" })], today, t, "en-US")).toBe("Fridge");
  });
});
