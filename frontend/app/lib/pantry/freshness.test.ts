import { describe, expect, test } from "vitest";
import { freshnessLine, groupByLocation } from "./freshness";
import type { PantryItemOut } from "~/lib/api/types/household";
import { i18n } from "~/tests/setup";

const t = (key: string, params?: Record<string, unknown>) => i18n.global.t(key, params ?? {});
const today = new Date(2026, 9, 24);

function item(extra: Partial<PantryItemOut> = {}): PantryItemOut {
  return { id: "p1", groupId: "g", householdId: "h", name: "Milk", ...extra };
}

describe("freshnessLine", () => {
  test("a use-by date wins over opened and bought, and today is urgent", () => {
    const line = freshnessLine(item({ useBy: "2026-10-24", openedOn: "2026-10-20", boughtOn: "2026-10-19" }), today, t);

    expect(line).toEqual({ text: "Use by October 24", urgent: true });
  });

  test("use by within two days is urgent, three days away is not", () => {
    expect(freshnessLine(item({ useBy: "2026-10-26" }), today, t)?.urgent).toBe(true);
    expect(freshnessLine(item({ useBy: "2026-10-27" }), today, t)).toEqual({ text: "Use by October 27", urgent: false });
  });

  test("a use-by date already past is urgent", () => {
    expect(freshnessLine(item({ useBy: "2026-10-20" }), today, t)).toEqual({ text: "Use by October 20", urgent: true });
  });

  test("without a use-by date, opened comes before bought", () => {
    const line = freshnessLine(item({ openedOn: "2026-10-21", boughtOn: "2026-10-19" }), today, t);

    expect(line).toEqual({ text: "Opened 3 days ago", urgent: false });
  });

  test("opened today reads naturally", () => {
    expect(freshnessLine(item({ openedOn: "2026-10-24" }), today, t)?.text).toBe("Opened today");
  });

  test("only a bought date gives the bought line", () => {
    expect(freshnessLine(item({ boughtOn: "2026-10-19" }), today, t)).toEqual({ text: "Bought 5 days ago", urgent: false });
  });

  test("no dates, no line", () => {
    expect(freshnessLine(item(), today, t)).toBeNull();
  });

  test("the date follows the locale", () => {
    expect(freshnessLine(item({ useBy: "2026-10-28" }), today, t, "fr-FR")?.text).toBe("Use by 28 octobre");
  });
});

describe("groupByLocation", () => {
  test("fixed order Fridge, Freezer, Cupboard, Other; empty locations left out", () => {
    const groups = groupByLocation([
      item({ id: "a", location: "other" }),
      item({ id: "b", location: "cupboard" }),
      item({ id: "c", location: "fridge" }),
      item({ id: "d" }),
    ]);

    expect(groups.map(g => g.location)).toEqual(["fridge", "cupboard", "other"]);
    // An item without a location is in the cupboard, the server's default.
    expect(groups[1]!.items.map(i => i.id)).toEqual(["b", "d"]);
  });
});
