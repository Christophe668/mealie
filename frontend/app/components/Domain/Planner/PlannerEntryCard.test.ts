import { flushPromises, mount } from "@vue/test-utils";
import { format } from "date-fns";
import { beforeEach, describe, expect, test, vi } from "vitest";
import PlannerEntryCard from "./PlannerEntryCard.vue";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const markCooked = vi.fn();
const unmarkCooked = vi.fn();
const alertError = vi.fn();

vi.mock("~/composables/api", () => ({
  useStaticRoutes: () => ({ recipeSmallImage: (id: string) => `/img/${id}` }),
  useUserApi: () => ({ householdCooking: { markCooked, unmarkCooked } }),
}));
vi.mock("~/composables/use-toast", () => ({ alert: { error: (...args: unknown[]) => alertError(...args) } }));

const stubs = {
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
};

function makeEntry(extra: Partial<ReadPlanEntry> = {}): ReadPlanEntry {
  return {
    id: 7,
    date: "2026-10-24",
    entryType: "dinner",
    title: "",
    text: "",
    recipeId: "r1",
    recipeScale: 1,
    groupId: "g",
    userId: "u",
    householdId: "h",
    recipe: { id: "r1", name: "Soup", slug: "soup", image: "abc", recipeServings: 4 },
    ...extra,
  };
}

function render(entry: ReadPlanEntry) {
  return mount(PlannerEntryCard, { props: { entry, groupSlug: "home" }, global: { stubs } });
}

const today = () => format(new Date(), "yyyy-MM-dd");

beforeEach(() => {
  vi.clearAllMocks();
});

describe("PlannerEntryCard cooked toggle", () => {
  test("not-done entry shows an unpressed Cooked toggle", () => {
    const toggle = render(makeEntry()).find(".planner-card__cooked");

    expect(toggle.text()).toBe("Cooked");
    expect(toggle.attributes("aria-pressed")).toBe("false");
  });

  test("done entry shows a pressed toggle and a muted card", () => {
    const wrapper = render(makeEntry({ cookedAt: "2026-10-24T12:00:00" }));

    expect(wrapper.find(".planner-card__cooked").attributes("aria-pressed")).toBe("true");
    expect(wrapper.classes()).toContain("planner-card--done");
  });

  test("clicking marks the entry cooked today and shows it done", async () => {
    markCooked.mockResolvedValue({ data: { mealPlanEntry: { cookedAt: "2026-10-25T12:00:00" } }, error: null, response: { status: 200 } });
    const wrapper = render(makeEntry());

    await wrapper.find(".planner-card__cooked").trigger("click");
    await flushPromises();

    expect(markCooked).toHaveBeenCalledWith(7, today());
    expect(wrapper.find(".planner-card__cooked").attributes("aria-pressed")).toBe("true");
  });

  test("clicking a done entry unmarks it", async () => {
    unmarkCooked.mockResolvedValue({ data: {}, error: null, response: { status: 200 } });
    const wrapper = render(makeEntry({ cookedAt: "2026-10-24T12:00:00" }));

    await wrapper.find(".planner-card__cooked").trigger("click");
    await flushPromises();

    expect(unmarkCooked).toHaveBeenCalledWith(7);
    expect(wrapper.find(".planner-card__cooked").attributes("aria-pressed")).toBe("false");
  });

  test("a 409 counts as done", async () => {
    markCooked.mockResolvedValue({ data: null, error: new Error("conflict"), response: { status: 409 } });
    const wrapper = render(makeEntry());

    await wrapper.find(".planner-card__cooked").trigger("click");
    await flushPromises();

    expect(wrapper.find(".planner-card__cooked").attributes("aria-pressed")).toBe("true");
    expect(alertError).not.toHaveBeenCalled();
  });

  test("an API error shows the error toast and reverts", async () => {
    markCooked.mockResolvedValue({ data: null, error: new Error("boom"), response: { status: 500 } });
    const wrapper = render(makeEntry());

    await wrapper.find(".planner-card__cooked").trigger("click");
    await flushPromises();

    expect(alertError).toHaveBeenCalledWith("Couldn’t update that meal. Try again.");
    expect(wrapper.find(".planner-card__cooked").attributes("aria-pressed")).toBe("false");
  });

  test("a second click while the first is pending calls the API once", async () => {
    let resolve!: (value: unknown) => void;
    markCooked.mockReturnValue(new Promise((r) => {
      resolve = r;
    }));
    const wrapper = render(makeEntry());

    await wrapper.find(".planner-card__cooked").trigger("click");
    await wrapper.find(".planner-card__cooked").trigger("click");
    resolve({ data: null, error: null, response: { status: 200 } });
    await flushPromises();

    expect(markCooked).toHaveBeenCalledTimes(1);
  });

  test("a failed unmark stays done and shows the error toast", async () => {
    unmarkCooked.mockResolvedValue({ data: null, error: new Error("boom"), response: { status: 500 } });
    const wrapper = render(makeEntry({ cookedAt: "2026-10-24T12:00:00" }));

    await wrapper.find(".planner-card__cooked").trigger("click");
    await flushPromises();

    expect(alertError).toHaveBeenCalled();
    expect(wrapper.find(".planner-card__cooked").attributes("aria-pressed")).toBe("true");
  });
});
