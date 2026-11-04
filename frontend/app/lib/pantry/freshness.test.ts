import { describe, expect, test } from "vitest";
import { byFreshness, freshnessLine, freshnessOf, groupByLocation } from "./freshness";
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

    expect(line).toEqual({ text: "Use by October 24", urgent: true, status: "soon" });
  });

  test("use by within two days is urgent, three days away is not", () => {
    expect(freshnessLine(item({ useBy: "2026-10-26" }), today, t)?.urgent).toBe(true);
    expect(freshnessLine(item({ useBy: "2026-10-27" }), today, t)).toEqual({ text: "Use by October 27", urgent: false, status: "ok" });
  });

  test("a use-by date already past is urgent", () => {
    expect(freshnessLine(item({ useBy: "2026-10-20" }), today, t)).toEqual({ text: "Use by October 20", urgent: true, status: "past" });
  });

  test("without a use-by date, opened comes before bought", () => {
    const line = freshnessLine(item({ openedOn: "2026-10-21", boughtOn: "2026-10-19" }), today, t);

    expect(line).toEqual({ text: "Opened 3 days ago", urgent: false, status: "unknown" });
  });

  test("opened today reads naturally", () => {
    expect(freshnessLine(item({ openedOn: "2026-10-24" }), today, t)?.text).toBe("Opened today");
  });

  test("only a bought date gives the bought line", () => {
    expect(freshnessLine(item({ boughtOn: "2026-10-19" }), today, t)).toEqual({ text: "Bought 5 days ago", urgent: false, status: "unknown" });
  });

  test("no dates, no line", () => {
    expect(freshnessLine(item(), today, t)).toBeNull();
  });

  test("the date follows the locale", () => {
    expect(freshnessLine(item({ useBy: "2026-10-28" }), today, t, "fr-FR")?.text).toBe("Use by 28 octobre");
  });
});

describe("freshnessOf", () => {
  const keeps = (openedDays: number | null, unopenedDays: number | null) => ({ openedDays, unopenedDays, source: "typical" as const });

  test("the item's own use-by date wins over any estimate", () => {
    const f = freshnessOf(item({ useBy: "2026-10-30", boughtOn: "2026-10-01", shelfLife: keeps(2, 2) }), today);

    expect(f).toEqual({ status: "ok", daysLeft: 6, estimated: false, keepsDays: null });
  });

  test("opened items count from the opening with the opened keeping time", () => {
    // Garlic: opened 8 days ago, keeps 7 days once opened: just past, worth checking.
    const f = freshnessOf(item({ boughtOn: "2026-10-10", openedOn: "2026-10-16", shelfLife: keeps(7, 60) }), today);

    expect(f).toEqual({ status: "check", daysLeft: -1, estimated: true, keepsDays: 7 });
  });

  test("sealed items count from the purchase with the sealed keeping time", () => {
    expect(freshnessOf(item({ boughtOn: "2026-10-20", shelfLife: keeps(4, 7) }), today).status).toBe("ok");
  });

  test("well past the estimate is probably past it", () => {
    // A baguette bought six days ago keeps two.
    expect(freshnessOf(item({ boughtOn: "2026-10-18", shelfLife: keeps(2, 2) }), today)).toMatchObject({ status: "past", daysLeft: -4 });
  });

  test("short-lived food nearing its estimate is to use soon", () => {
    expect(freshnessOf(item({ boughtOn: "2026-10-23", shelfLife: keeps(2, 2) }), today).status).toBe("soon");
    expect(freshnessOf(item({ boughtOn: "2026-10-24", shelfLife: keeps(2, 2) }), today).status).toBe("ok");
  });

  test("no dates, or no keeping time, means unknown", () => {
    expect(freshnessOf(item({ shelfLife: keeps(3, 21) }), today).status).toBe("unknown");
    expect(freshnessOf(item({ boughtOn: "2026-01-01" }), today).status).toBe("unknown");
  });

  test("an opened item without an opened keeping time falls back to the purchase", () => {
    expect(freshnessOf(item({ boughtOn: "2026-10-20", openedOn: "2026-10-21", shelfLife: keeps(null, 3) }), today).status).toBe("check");
  });
});

describe("byFreshness", () => {
  test("worst first, the server's order kept within a status", () => {
    const sorted = byFreshness([
      item({ id: "ok-1", boughtOn: "2026-10-23", shelfLife: { openedDays: 30, unopenedDays: 30, source: "typical" } }),
      item({ id: "unknown" }),
      item({ id: "past", useBy: "2026-10-01" }),
      item({ id: "ok-2", useBy: "2026-11-30" }),
      item({ id: "soon", useBy: "2026-10-25" }),
    ], today);

    expect(sorted.map(i => i.id)).toEqual(["past", "soon", "ok-1", "ok-2", "unknown"]);
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
