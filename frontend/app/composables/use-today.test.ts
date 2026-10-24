import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ref } from "vue";
import { relativeAgo, useToday } from "./use-today";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const api = vi.hoisted(() => ({
  mealplans: { getAll: vi.fn(), createOne: vi.fn(), updateOne: vi.fn() },
  lists: { getAll: vi.fn(), getOne: vi.fn() },
  recipes: { getAll: vi.fn() },
  householdRecipe: vi.fn(),
  connections: vi.fn(),
  firstDayOfWeek: { value: 0 },
}));

vi.mock("~/composables/api", () => ({
  useUserApi: () => ({
    mealplans: api.mealplans,
    shopping: { lists: api.lists },
    recipes: api.recipes,
    households: { getCurrentUserHouseholdRecipe: api.householdRecipe },
    mcpConnections: { getConnections: api.connections },
  }),
}));

vi.mock("~/composables/use-households", () => ({
  useHouseholdSelf: () => ({
    household: ref({ preferences: { firstDayOfWeek: api.firstDayOfWeek.value } }),
    actions: { refresh: vi.fn() },
  }),
}));

function ok<T>(data: T) {
  return Promise.resolve({ data, error: null, response: { status: 200 } });
}
const failed = () => Promise.resolve({ data: null, error: new Error("offline"), response: null });

function page<T>(items: T[]) {
  return { page: 1, per_page: items.length, total: items.length, total_pages: 1, items };
}

let nextId = 1;
function entry(date: string, entryType: ReadPlanEntry["entryType"], name: string): ReadPlanEntry {
  const id = nextId++;
  return {
    id,
    date,
    entryType,
    groupId: "g",
    userId: "u",
    householdId: "h",
    recipeId: `r${id}`,
    recipe: { id: `r${id}`, name, slug: name.toLowerCase().replace(/ /g, "-") },
  };
}

function mockPlan(entries: ReadPlanEntry[]) {
  api.mealplans.getAll.mockImplementation(() => ok(page(entries)));
}

async function load() {
  const today = useToday();
  await today.refresh();
  return today;
}

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

beforeEach(() => {
  // Saturday 24 October 2026, mid-afternoon local time.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 9, 24, 15, 30));
  api.firstDayOfWeek.value = 0;
  mockPlan([]);
  api.lists.getAll.mockImplementation(() => ok(page([])));
  api.lists.getOne.mockImplementation(failed);
  api.recipes.getAll.mockImplementation(() => ok(page([])));
  api.householdRecipe.mockImplementation(() => ok({ recipeId: "x", lastMade: null }));
  api.connections.mockImplementation(() => ok([]));
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("useToday tonight and lunch", () => {
  test("tonight is today's dinner even when lunch comes first", async () => {
    mockPlan([
      entry("2026-10-24", "lunch", "Leftover dal"),
      entry("2026-10-24", "dinner", "Roast chicken"),
      entry("2026-10-23", "dinner", "Pizza"),
    ]);

    const { tonight, lunch } = await load();

    expect(tonight.value?.recipe?.name).toBe("Roast chicken");
    expect(lunch.value?.recipe?.name).toBe("Leftover dal");
  });

  test("without a dinner, tonight falls back to today's first other entry", async () => {
    mockPlan([
      entry("2026-10-24", "lunch", "Leftover dal"),
      entry("2026-10-24", "side", "Green salad"),
    ]);

    const { tonight, lunch } = await load();

    expect(tonight.value?.recipe?.name).toBe("Green salad");
    expect(lunch.value?.recipe?.name).toBe("Leftover dal");
  });

  test("a lunch alone is not shown as tonight", async () => {
    mockPlan([entry("2026-10-24", "lunch", "Leftover dal")]);

    const { tonight, lunch } = await load();

    expect(tonight.value).toBeNull();
    expect(lunch.value?.recipe?.name).toBe("Leftover dal");
  });

  test("tonight's last-made date is looked up for its recipe", async () => {
    mockPlan([entry("2026-10-24", "dinner", "Roast chicken")]);
    api.householdRecipe.mockImplementation(() => ok({ recipeId: "r", lastMade: "2026-09-12T18:00:00" }));

    const { tonightLastMade } = await load();

    expect(api.householdRecipe).toHaveBeenCalledWith("roast-chicken");
    expect(tonightLastMade.value).toBe("2026-09-12T18:00:00");
  });
});

describe("useToday week", () => {
  test("starts on Sunday when the household's first day of week is 0", async () => {
    const { week } = await load();

    expect(week.value).toHaveLength(7);
    expect(ymd(week.value[0]!.date)).toBe("2026-10-18");
    expect(ymd(week.value[6]!.date)).toBe("2026-10-24");
  });

  test("starts on Monday when the household's first day of week is 1, and fetches that range once", async () => {
    api.firstDayOfWeek.value = 1;
    mockPlan([
      entry("2026-10-19", "dinner", "Pasta alla norma"),
      entry("2026-10-25", "dinner", "Sunday roast"),
      entry("2026-10-25", "dessert", "Tarte tatin"),
    ]);

    const { week } = await load();

    expect(week.value.map(day => ymd(day.date))).toEqual([
      "2026-10-19",
      "2026-10-20",
      "2026-10-21",
      "2026-10-22",
      "2026-10-23",
      "2026-10-24",
      "2026-10-25",
    ]);
    expect(api.mealplans.getAll).toHaveBeenCalledTimes(1);
    expect(api.mealplans.getAll).toHaveBeenCalledWith(1, -1, { start_date: "2026-10-19", end_date: "2026-10-25" });
    expect(week.value[0]!.entries.map(e => e.recipe?.name)).toEqual(["Pasta alla norma"]);
    expect(week.value[6]!.entries.map(e => e.recipe?.name)).toEqual(["Sunday roast", "Tarte tatin"]);
    expect(week.value[3]!.entries).toEqual([]);
  });
});

describe("useToday shopping list", () => {
  test("uses the most recently updated list and counts only unchecked items", async () => {
    api.lists.getAll.mockImplementation(() => ok(page([{ id: "list-1", name: "Weekly shop" }])));
    api.lists.getOne.mockImplementation(() => ok({
      id: "list-1",
      name: "Weekly shop",
      listItems: [
        { id: "a", checked: false },
        { id: "b", checked: true },
        { id: "c", checked: false },
        { id: "d", checked: true },
      ],
    }));

    const { openList } = await load();

    expect(api.lists.getAll).toHaveBeenCalledWith(1, 1, { orderBy: "updated_at", orderDirection: "desc" });
    expect(api.lists.getOne).toHaveBeenCalledWith("list-1");
    expect(openList.value).toEqual({ id: "list-1", name: "Weekly shop", openCount: 2 });
  });
});

describe("useToday shelves", () => {
  test("make again orders by last made (never-cooked first) and recent by creation date", async () => {
    api.recipes.getAll.mockImplementation((_page: number, _perPage: number, params: { orderBy: string }) =>
      ok(page(params.orderBy === "last_made"
        ? [{ id: "1", slug: "shakshuka", name: "Shakshuka" }]
        : [{ id: "2", slug: "risotto", name: "Risotto" }])),
    );
    api.householdRecipe.mockImplementation((slug: string) =>
      ok({ recipeId: "1", lastMade: slug === "shakshuka" ? "2026-05-02T19:00:00" : null }),
    );

    const { makeAgain, recent, lastMade } = await load();

    expect(api.recipes.getAll).toHaveBeenCalledWith(1, 8, expect.objectContaining({ orderBy: "last_made", orderDirection: "asc" }));
    expect(api.recipes.getAll).toHaveBeenCalledWith(1, 8, { orderBy: "created_at", orderDirection: "desc" });
    expect(makeAgain.value.map(r => r.name)).toEqual(["Shakshuka"]);
    expect(recent.value.map(r => r.name)).toEqual(["Risotto"]);
    expect(lastMade.value).toEqual({ shakshuka: "2026-05-02T19:00:00" });
  });
});

describe("useToday connections", () => {
  test("knows when no MCP client is connected", async () => {
    const { hasConnection } = await load();
    expect(hasConnection.value).toBe(false);
  });

  test("knows when one is", async () => {
    api.connections.mockImplementation(() => ok([{ grantId: "x" }]));
    const { hasConnection } = await load();
    expect(hasConnection.value).toBe(true);
  });

  test("stays unknown when the call fails", async () => {
    api.connections.mockImplementation(failed);
    const { hasConnection } = await load();
    expect(hasConnection.value).toBeNull();
  });
});

describe("useToday with nothing to show", () => {
  test("failed or empty responses give nulls and empty lists, not errors", async () => {
    api.mealplans.getAll.mockImplementation(failed);
    api.lists.getAll.mockImplementation(failed);
    api.recipes.getAll.mockImplementation(failed);

    const today = useToday();
    await expect(today.refresh()).resolves.toBeUndefined();

    expect(today.tonight.value).toBeNull();
    expect(today.lunch.value).toBeNull();
    expect(today.openList.value).toBeNull();
    expect(today.makeAgain.value).toEqual([]);
    expect(today.recent.value).toEqual([]);
    expect(today.week.value).toHaveLength(7);
    expect(today.week.value.every(day => day.entries.length === 0)).toBe(true);
    expect(today.loading.value).toBe(false);
  });
});

describe("useToday swap", () => {
  test("saving an existing entry updates it and reloads the plan", async () => {
    mockPlan([entry("2026-10-24", "dinner", "Roast chicken")]);
    api.mealplans.updateOne.mockImplementation(() => ok({}));
    const today = await load();

    await today.saveEntry({ id: 9, date: "2026-10-24", entryType: "dinner", recipeId: "r2", groupId: "g", userId: "u" });

    expect(api.mealplans.updateOne).toHaveBeenCalledWith(9, expect.objectContaining({ recipeId: "r2" }));
    expect(api.mealplans.getAll).toHaveBeenCalledTimes(2);
  });

  test("saving a new entry creates it", async () => {
    api.mealplans.createOne.mockImplementation(() => ok({}));
    const today = await load();

    await today.saveEntry({ date: "2026-10-24", entryType: "dinner", recipeId: "r2" });

    expect(api.mealplans.createOne).toHaveBeenCalledWith(expect.objectContaining({ recipeId: "r2" }));
  });
});

describe("relativeAgo", () => {
  const now = new Date(2026, 9, 24, 15, 30);
  test.each([
    ["2026-10-24T08:00:00", "today"],
    ["2026-10-23T20:00:00", "yesterday"],
    ["2026-10-20T20:00:00", "4 days ago"],
    ["2026-09-12T18:00:00", "6 weeks ago"],
    ["2026-05-02T19:00:00", "5 months ago"],
    ["2024-10-01T19:00:00", "2 years ago"],
  ])("%s reads as %s", (iso, expected) => {
    expect(relativeAgo(iso, now, "en-US")).toBe(expected);
  });
});
