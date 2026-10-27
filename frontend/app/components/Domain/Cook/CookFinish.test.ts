import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import CookFinish from "./CookFinish.vue";
import { alert } from "~/composables/use-toast";
import type { PantryCheckOut, PantryItemOut, PantryProposal } from "~/lib/api/types/household";

type ApiResult<T> = { data: T | null; error: unknown; response?: { status: number } };

const pantryCheck = vi.fn<(recipeId: string, cookedOn: string, scale?: number, substitutes?: Record<string, string>) => Promise<ApiResult<PantryCheckOut>>>();
const getAll = vi.fn<() => Promise<ApiResult<{ items: PantryItemOut[] }>>>();
const record = vi.fn<(payload: object, options?: { amend?: boolean }) => Promise<ApiResult<object>>>();
vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ householdCooking: { pantryCheck, record }, householdPantry: { getAll } }),
}));

const conflict = (message = "already recorded as cooked on 2026-10-24"): ApiResult<object> => ({
  data: null,
  error: { response: { status: 409, data: { detail: { message } } } },
  response: null,
});

const replace = vi.fn();
const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

const item = (id: string, name: string): PantryItemOut => ({ id, name, groupId: "g", householdId: "h" });

function check(extra: Partial<PantryCheckOut> = {}): ApiResult<PantryCheckOut> {
  return { data: { items: [], suggestedLeftoverPortions: 0, mealPlanEntryId: null, ...extra }, error: null, response: { status: 200 } };
}

async function render(props: Partial<{ loggedIn: boolean; scale: number; cookedOn: string; mealPlanEntryId: number; amend: boolean }> = {}) {
  const wrapper = mount(CookFinish, {
    props: { recipeId: "r-1", backTo: "/g/home/r/onion-soup", loggedIn: true, scale: 1, ...props },
    global: { stubs },
  });
  await flushPromises();
  return wrapper;
}

const button = (wrapper: Awaited<ReturnType<typeof render>>, label: string) =>
  wrapper.findAll("button").find(b => b.text() === label)!;
const itemRow = (wrapper: Awaited<ReturnType<typeof render>>, name: string) =>
  wrapper.findAll(".cook-pantry__item").find(r => r.text().includes(name))!;

beforeEach(() => {
  vi.useFakeTimers();
  // Late evening local time, so a UTC date would already be the next day east of Greenwich.
  vi.setSystemTime(new Date(2026, 9, 24, 23, 30));
  replace.mockReset();
  pantryCheck.mockReset();
  pantryCheck.mockResolvedValue(check());
  getAll.mockReset();
  getAll.mockResolvedValue({ data: { items: [] }, error: null });
  record.mockReset();
  record.mockResolvedValue({ data: {}, error: null, response: { status: 201 } });
  vi.stubGlobal("useRouter", () => ({ replace }));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CookFinish", () => {
  test("told later: checks and records the given day and entry, amending a cooking already recorded", async () => {
    pantryCheck.mockResolvedValue(check({ mealPlanEntryId: 9 }));
    const wrapper = await render({ cookedOn: "2026-10-23", mealPlanEntryId: 7, amend: true });

    expect(pantryCheck).toHaveBeenCalledWith("r-1", "2026-10-23", 1);
    await button(wrapper, "Loved it").trigger("click");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith(
      { recipeId: "r-1", cookedOn: "2026-10-23", scale: 1, mealPlanEntryId: 7, feedback: { verdict: "loved" } },
      { amend: true },
    );
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
  });

  test("nothing in the pantry and no leftovers: the screen as before, Done records the cooking", async () => {
    const wrapper = await render({ scale: 2 });

    // The cook's own day, and the scale cooked.
    expect(pantryCheck).toHaveBeenCalledWith("r-1", "2026-10-24", 2);
    expect(wrapper.text()).toContain("How was it?");
    expect(wrapper.text()).not.toContain("From your pantry");
    expect(wrapper.text()).not.toContain("Leftovers");

    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith({ recipeId: "r-1", cookedOn: "2026-10-24", scale: 2 });
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
  });

  test("pantry items start with no outcome; only the chosen one is sent, with the meal plan entry", async () => {
    pantryCheck.mockResolvedValue(check({ items: [item("p-butter", "Butter"), item("p-onion", "Onions")], mealPlanEntryId: 7 }));
    const wrapper = await render();

    expect(wrapper.text()).toContain("From your pantry");
    expect(wrapper.findAll(".cook-pantry__item button").every(b => b.attributes("aria-pressed") === "false")).toBe(true);

    await itemRow(wrapper, "Butter").findAll("button").find(b => b.text() === "Used up")!.trigger("click");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith({
      recipeId: "r-1",
      cookedOn: "2026-10-24",
      scale: 1,
      mealPlanEntryId: 7,
      pantry: [{ pantryItemId: "p-butter", outcome: "used_up" }],
    });
  });

  test("leftovers are pre-filled with the suggestion and sent with where they go", async () => {
    pantryCheck.mockResolvedValue(check({ suggestedLeftoverPortions: 2 }));
    const wrapper = await render();

    expect(wrapper.find(".cook-pantry__portions").text()).toBe("2 portions");
    await button(wrapper, "Freezer").trigger("click");
    await wrapper.find("[aria-label='More portions']").trigger("click");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith(expect.objectContaining({ leftovers: { portions: 3, location: "freezer" } }));
  });

  test("leftovers brought down to none are not sent", async () => {
    pantryCheck.mockResolvedValue(check({ suggestedLeftoverPortions: 1 }));
    const wrapper = await render();

    await wrapper.find("[aria-label='Fewer portions']").trigger("click");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record.mock.calls[0]![0]).not.toHaveProperty("leftovers");
  });

  test("a verdict is a selection; Done sends it with the effort", async () => {
    const wrapper = await render();

    await button(wrapper, "Loved it").trigger("click");
    expect(record).not.toHaveBeenCalled();
    expect(button(wrapper, "Loved it").attributes("aria-pressed")).toBe("true");
    await button(wrapper, "It was fine").trigger("click");
    expect(button(wrapper, "Loved it").attributes("aria-pressed")).toBe("false");
    expect(button(wrapper, "It was fine").attributes("aria-pressed")).toBe("true");
    await button(wrapper, "A lot of work").trigger("click");

    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith({ recipeId: "r-1", cookedOn: "2026-10-24", scale: 1, feedback: { verdict: "ok", effort: 3 } });
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
  });

  test("the chosen verdict can be cleared again", async () => {
    const wrapper = await render();

    await button(wrapper, "Not again").trigger("click");
    await button(wrapper, "Not again").trigger("click");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record.mock.calls[0]![0]).not.toHaveProperty("feedback");
  });

  test("Skip saves the pantry choices but no feedback", async () => {
    pantryCheck.mockResolvedValue(check({ items: [item("p-butter", "Butter")] }));
    const wrapper = await render();

    await button(wrapper, "Loved it").trigger("click");
    await itemRow(wrapper, "Butter").findAll("button").find(b => b.text() === "Some left")!.trigger("click");
    await button(wrapper, "Skip").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith({
      recipeId: "r-1",
      cookedOn: "2026-10-24",
      scale: 1,
      pantry: [{ pantryItemId: "p-butter", outcome: "some_left" }],
    });
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
  });

  test("a first-attempt 409 says nothing was changed, then leaves", async () => {
    const error = vi.spyOn(alert, "error").mockImplementation(() => {});
    const info = vi.spyOn(alert, "info").mockImplementation(() => {});
    record.mockResolvedValue(conflict());
    const wrapper = await render();

    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(info).toHaveBeenCalledWith("already recorded as cooked on 2026-10-24 Pantry and leftovers weren’t changed.");
    expect(error).not.toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
    error.mockRestore();
    info.mockRestore();
  });

  test("a 409 on the retry of our own failed request leaves silently", async () => {
    const error = vi.spyOn(alert, "error").mockImplementation(() => {});
    const info = vi.spyOn(alert, "info").mockImplementation(() => {});
    record.mockResolvedValueOnce({ data: null, error: new Error("boom"), response: { status: 500 } });
    record.mockResolvedValueOnce(conflict());
    const wrapper = await render();

    await button(wrapper, "Done").trigger("click");
    await flushPromises();
    expect(replace).not.toHaveBeenCalled();
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(info).not.toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
    error.mockRestore();
    info.mockRestore();
  });

  test("effort chips wait for a verdict, and effort alone is never sent", async () => {
    const wrapper = await render();
    const quick = () => wrapper.findAll(".cook-finish__chip")[0]!;

    expect(quick().attributes("aria-disabled")).toBe("true");
    await quick().trigger("click");
    expect(quick().attributes("aria-pressed")).toBe("false");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();
    expect(record).toHaveBeenCalledWith({ recipeId: "r-1", cookedOn: "2026-10-24", scale: 1 });

    record.mockClear();
    await button(wrapper, "Loved it").trigger("click");
    expect(quick().attributes("aria-disabled")).toBeUndefined();
    await quick().trigger("click");
    expect(quick().attributes("aria-pressed")).toBe("true");
  });

  test("a failed save says so, stays and can be retried", async () => {
    const error = vi.spyOn(alert, "error").mockImplementation(() => {});
    let resolve!: (value: ApiResult<object>) => void;
    record.mockImplementationOnce(() => new Promise((r) => {
      resolve = r;
    }));
    const wrapper = await render();

    await button(wrapper, "Loved it").trigger("click");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();
    // Everything waits while the save is in flight.
    expect(button(wrapper, "Done").attributes("aria-disabled")).toBe("true");
    expect(button(wrapper, "Skip").attributes("aria-disabled")).toBe("true");
    expect(button(wrapper, "Not again").attributes("aria-disabled")).toBe("true");
    await button(wrapper, "Not again").trigger("click");
    await button(wrapper, "Done").trigger("click");
    expect(record).toHaveBeenCalledTimes(1);

    resolve({ data: null, error: new Error("boom"), response: { status: 500 } });
    await flushPromises();

    expect(error).toHaveBeenCalledWith("Couldn’t record that you made it.");
    expect(replace).not.toHaveBeenCalled();
    expect(button(wrapper, "Done").attributes("aria-disabled")).toBeUndefined();
    expect(button(wrapper, "Loved it").attributes("aria-pressed")).toBe("true");

    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledTimes(2);
    expect(record.mock.calls[1]![0]).toEqual(record.mock.calls[0]![0]);
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
    error.mockRestore();
  });

  test("a failed pantry check still lets you finish", async () => {
    pantryCheck.mockResolvedValue({ data: null, error: new Error("offline"), response: { status: 500 } });
    const wrapper = await render();

    expect(wrapper.text()).not.toContain("From your pantry");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(record).toHaveBeenCalledWith({ recipeId: "r-1", cookedOn: "2026-10-24", scale: 1 });
  });

  test("a visitor gets a plain Done that checks and records nothing", async () => {
    const wrapper = await render({ loggedIn: false });

    expect(wrapper.text()).not.toContain("How was it?");
    await button(wrapper, "Done").trigger("click");
    await flushPromises();

    expect(pantryCheck).not.toHaveBeenCalled();
    expect(record).not.toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
  });

  describe("pantry quantities", () => {
    const flour: PantryItemOut = { ...item("p-flour", "Flour"), quantity: 1000, unit: { id: "u-g", name: "g", pluralName: "g" } };
    const oil: PantryItemOut = { ...item("p-oil", "Olive oil"), quantity: 500 };
    const proposal = (extra: Partial<PantryProposal> = {}): PantryProposal => ({
      pantryItemId: "p-flour",
      used: 200,
      proposedQuantity: 800,
      proposedOutcome: "some_left",
      reason: "subtracted",
      ...extra,
    });
    const ghee = { referenceId: "ref-1", food: { id: "f-ghee", name: "Ghee" } };

    test("refetches the pantry check with substitutes", async () => {
      pantryCheck.mockResolvedValueOnce(check({ items: [flour], proposals: [proposal()], unmatchedIngredients: [ghee] }));
      getAll.mockResolvedValue({ data: { items: [flour, oil] }, error: null });
      const wrapper = await render();

      expect(pantryCheck).toHaveBeenCalledTimes(1);
      expect(wrapper.text()).toContain("Ghee: not in your pantry");
      pantryCheck.mockResolvedValueOnce(check({
        items: [flour, oil],
        proposals: [proposal(), proposal({ pantryItemId: "p-oil", proposedQuantity: null, proposedOutcome: "none", replacesReferenceId: "ref-1" })],
        unmatchedIngredients: [],
      }));
      await button(wrapper, "Used something else?").trigger("click");
      await wrapper.findAll(".cook-pantry__picker button").find(b => b.text() === "Olive oil")!.trigger("click");
      await flushPromises();

      expect(pantryCheck).toHaveBeenCalledTimes(2);
      expect(pantryCheck).toHaveBeenLastCalledWith("r-1", "2026-10-24", 1, { "ref-1": "p-oil" });
      expect(itemRow(wrapper, "Olive oil").text()).toContain("instead of Ghee");
      // the proposal for the first item is kept, not redone
      expect(button(itemRow(wrapper, "Flour"), "Some left").attributes("aria-pressed")).toBe("true");
    });

    test("a failed refetch keeps the previous check and drops the substitute", async () => {
      pantryCheck.mockResolvedValueOnce(check({ items: [flour], proposals: [proposal()], unmatchedIngredients: [ghee] }));
      getAll.mockResolvedValue({ data: { items: [flour, oil] }, error: null });
      const wrapper = await render();

      pantryCheck.mockResolvedValueOnce({ data: null, error: new Error("offline"), response: { status: 500 } });
      await button(wrapper, "Used something else?").trigger("click");
      await wrapper.findAll(".cook-pantry__picker button").find(b => b.text() === "Olive oil")!.trigger("click");
      await flushPromises();

      expect(pantryCheck).toHaveBeenCalledTimes(2);
      expect(wrapper.text()).toContain("Ghee: not in your pantry");
      expect(itemRow(wrapper, "Flour")).toBeTruthy();
      await button(wrapper, "Done").trigger("click");
      await flushPromises();
      expect(record.mock.calls[0]![0]).toHaveProperty("pantry", [{ pantryItemId: "p-flour", outcome: "some_left", quantity: 800 }]);
    });

    test("sends quantity and replacesReferenceId", async () => {
      pantryCheck.mockResolvedValue(check({
        items: [flour, oil],
        proposals: [proposal(), proposal({ pantryItemId: "p-oil", proposedQuantity: null, proposedOutcome: "used_up", replacesReferenceId: "ref-1" })],
      }));
      const wrapper = await render();

      expect(button(itemRow(wrapper, "Olive oil"), "Used up").attributes("aria-pressed")).toBe("true");
      await button(wrapper, "Done").trigger("click");
      await flushPromises();

      expect(record).toHaveBeenCalledWith({
        recipeId: "r-1",
        cookedOn: "2026-10-24",
        scale: 1,
        pantry: [
          { pantryItemId: "p-flour", outcome: "some_left", quantity: 800 },
          { pantryItemId: "p-oil", outcome: "used_up", replacesReferenceId: "ref-1" },
        ],
      });
    });

    test("an unchanged some_left sends no quantity", async () => {
      pantryCheck.mockResolvedValue(check({ items: [flour], proposals: [proposal({ proposedQuantity: 1000, reason: "units_differ" })] }));
      const wrapper = await render();

      await button(wrapper, "Done").trigger("click");
      await flushPromises();

      expect(record).toHaveBeenCalledWith({
        recipeId: "r-1",
        cookedOn: "2026-10-24",
        scale: 1,
        pantry: [{ pantryItemId: "p-flour", outcome: "some_left" }],
      });
    });
  });
});
