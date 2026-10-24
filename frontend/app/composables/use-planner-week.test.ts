import { flushPromises } from "@vue/test-utils";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { effectScope, ref } from "vue";
import { usePlannerWeek } from "./use-planner-week";
import type { PlannerRange } from "./use-planner-week";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const api = vi.hoisted(() => ({
  getAll: vi.fn(),
  createOne: vi.fn(),
  updateOne: vi.fn(),
  deleteOne: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("~/composables/api", () => ({
  useUserApi: () => ({
    mealplans: { getAll: api.getAll, createOne: api.createOne, updateOne: api.updateOne, deleteOne: api.deleteOne },
  }),
}));
vi.mock("vue-i18n", async importOriginal => ({
  ...(await importOriginal<object>()),
  useI18n: () => ({ t: (key: string) => key }),
}));
vi.mock("~/composables/use-toast", () => ({ alert: { error: api.toastError } }));

type Response = { data: { items: ReadPlanEntry[] } | null; error: unknown };

function deferred() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function entry(id: number, date: string): ReadPlanEntry {
  return { id, date, entryType: "dinner", title: `Entry ${id}`, groupId: "g", userId: "u", householdId: "h" };
}

const week = (start: string, end: string): PlannerRange => ({ start: new Date(`${start}T00:00`), end: new Date(`${end}T00:00`) });
const ok = (items: ReadPlanEntry[]): Response => ({ data: { items }, error: null });

function setup(range: ReturnType<typeof ref<PlannerRange>>) {
  const scope = effectScope();
  const result = scope.run(() => usePlannerWeek(() => range.value!))!;
  return { ...result, scope };
}

describe("usePlannerWeek", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("loads the week's entries", async () => {
    api.getAll.mockResolvedValue(ok([entry(1, "2026-10-20")]));
    const range = ref(week("2026-10-18", "2026-10-24"));

    const { entries, loading, failed } = setup(range);
    await flushPromises();

    expect(api.getAll).toHaveBeenCalledWith(1, -1, { start_date: "2026-10-18", end_date: "2026-10-24" });
    expect(entries.value.map(e => e.id)).toEqual([1]);
    expect(loading.value).toBe(false);
    expect(failed.value).toBe(false);
  });

  test("a response for a week already left never overwrites the current week", async () => {
    const first = deferred();
    const second = deferred();
    api.getAll.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    // e.g. the Sunday-based week requested before household preferences said Monday
    const range = ref(week("2026-10-18", "2026-10-24"));
    const { entries, loading } = setup(range);

    range.value = week("2026-10-19", "2026-10-25");
    await flushPromises();
    second.resolve(ok([entry(2, "2026-10-25")]));
    await flushPromises();
    first.resolve(ok([entry(1, "2026-10-18")]));
    await flushPromises();

    expect(entries.value.map(e => e.id)).toEqual([2]);
    expect(loading.value).toBe(false);
  });

  test("a new week starts blank instead of showing the previous week's entries", async () => {
    api.getAll.mockResolvedValueOnce(ok([entry(1, "2026-10-20")])).mockReturnValueOnce(new Promise(() => {}));
    const range = ref(week("2026-10-18", "2026-10-24"));
    const { entries, loading } = setup(range);
    await flushPromises();

    range.value = week("2026-10-25", "2026-10-31");
    await flushPromises();

    expect(entries.value).toEqual([]);
    expect(loading.value).toBe(true);
  });

  test("a failed load is reported, and a retry clears it", async () => {
    api.getAll.mockResolvedValueOnce({ data: null, error: new Error("offline") }).mockResolvedValueOnce(ok([entry(1, "2026-10-20")]));
    const range = ref(week("2026-10-18", "2026-10-24"));
    const { entries, failed, reload } = setup(range);
    await flushPromises();

    expect(failed.value).toBe(true);
    expect(entries.value).toEqual([]);

    await reload();

    expect(failed.value).toBe(false);
    expect(entries.value.map(e => e.id)).toEqual([1]);
  });

  test("a failed change says so and reloads what is saved", async () => {
    api.getAll.mockResolvedValue(ok([entry(1, "2026-10-20")]));
    api.updateOne.mockResolvedValue({ data: null, error: new Error("nope") });
    const range = ref(week("2026-10-18", "2026-10-24"));
    const { update } = setup(range);
    await flushPromises();

    const saved = await update({ ...entry(1, "2026-10-22") });

    expect(saved).toBe(false);
    expect(api.updateOne).toHaveBeenCalledWith(1, expect.objectContaining({ date: "2026-10-22" }));
    expect(api.toastError).toHaveBeenCalledWith("planner.save-failed");
    expect(api.getAll).toHaveBeenCalledTimes(2);
  });
});
