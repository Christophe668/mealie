import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, describe, expect, test, vi } from "vitest";
import PlannerWeek from "./PlannerWeek.vue";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";

// Sortable needs real pointer events; the stand-in lets a test play the "add" event Sortable fires on the
// list an item was dropped into.
vi.mock("vue-draggable-plus", async () => {
  const { defineComponent, h } = await import("vue");
  return {
    VueDraggable: defineComponent({
      name: "VueDraggable",
      props: { modelValue: { type: Array, default: () => [] } },
      emits: ["add", "update:modelValue"],
      setup: (_props, { slots, attrs }) => () => h("div", { ...attrs, class: ["draggable-stub", attrs.class] }, slots.default?.()),
    }),
  };
});
vi.mock("~/composables/api", () => ({
  useStaticRoutes: () => ({ recipeSmallImage: (id: string) => `/img/${id}` }),
}));

const stubs = {
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
};

const MEAL_TYPES: PlanEntryType[] = ["breakfast", "lunch", "dinner", "side", "snack", "drink", "dessert"];
// Monday 19 October 2026; "today" is Saturday 24th.
const START = new Date(2026, 9, 19);
const TODAY = new Date(2026, 9, 24);

let nextId = 1;
function entry(date: string, entryType: PlanEntryType, name: string, extra: Partial<ReadPlanEntry> = {}): ReadPlanEntry {
  const id = nextId++;
  return {
    id,
    date,
    entryType,
    title: "",
    text: "",
    recipeId: `r${id}`,
    recipeScale: 1,
    groupId: "g",
    userId: "u",
    householdId: "h",
    recipe: { id: `r${id}`, name, slug: name.toLowerCase().replace(/ /g, "-"), image: "abc", recipeServings: 4 },
    ...extra,
  };
}

function render(entries: ReadPlanEntry[]) {
  return mount(PlannerWeek, {
    props: { start: START, today: TODAY, entries, mealTypes: MEAL_TYPES, groupSlug: "home" },
    global: { stubs },
    attachTo: document.body,
  });
}

function cell(wrapper: ReturnType<typeof render>, date: string, type: PlanEntryType) {
  return wrapper.find(`.planner-grid [data-date="${date}"][data-type="${type}"]`);
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("PlannerWeek", () => {
  test("renders seven day columns from the start date", () => {
    const wrapper = render([]);

    const columns = wrapper.findAll(".planner-grid .planner-day");
    expect(columns).toHaveLength(7);
    expect(columns[0]!.attributes("data-date")).toBe("2026-10-19");
    expect(columns[6]!.attributes("data-date")).toBe("2026-10-25");
    expect(columns[0]!.find(".planner-day__head").text()).toContain("Mon");
  });

  test("an empty week still has a dinner row", () => {
    const wrapper = render([]);

    const rows = wrapper.findAll(".planner-grid .planner-grid__label").map(l => l.text());
    expect(rows).toEqual(["Dinner"]);
    expect(cell(wrapper, "2026-10-19", "dinner").exists()).toBe(true);
  });

  test("groups entries by day and meal type, rows in meal-type order", () => {
    const wrapper = render([
      entry("2026-10-21", "dessert", "Tarte tatin"),
      entry("2026-10-21", "lunch", "Leek soup"),
      entry("2026-10-23", "dinner", "Roast chicken"),
    ]);

    const rows = wrapper.findAll(".planner-grid .planner-grid__label").map(l => l.text());
    expect(rows).toEqual(["Lunch", "Dinner", "Dessert"]);
    expect(cell(wrapper, "2026-10-21", "lunch").text()).toContain("Leek soup");
    expect(cell(wrapper, "2026-10-21", "dessert").text()).toContain("Tarte tatin");
    expect(cell(wrapper, "2026-10-23", "dinner").text()).toContain("Roast chicken");
    expect(cell(wrapper, "2026-10-21", "dinner").text()).not.toContain("Roast chicken");
    // The row labels are visual; each cell names its own meal type and day for screen readers.
    expect(cell(wrapper, "2026-10-21", "lunch").attributes("role")).toBe("group");
    expect(cell(wrapper, "2026-10-21", "lunch").attributes("aria-label")).toMatch(/^Lunch on Wednesday.*21/);
  });

  test("emits move with the entry and the target day when an entry is dropped on another day", async () => {
    const roast = entry("2026-10-23", "dinner", "Roast chicken");
    const wrapper = render([roast]);

    const target = wrapper
      .findAllComponents({ name: "VueDraggable" })
      .find(c => c.attributes("data-date") === "2026-10-25" && c.attributes("data-type") === "dinner")!;
    const item = document.createElement("div");
    item.dataset.entryId = String(roast.id);
    target.vm.$emit("add", { item });

    expect(wrapper.emitted("move")).toEqual([[{ entryId: roast.id, date: "2026-10-25", entryType: "dinner" }]]);
  });

  test("dropping on another meal type of the same day moves it to that type", () => {
    const roast = entry("2026-10-23", "dinner", "Roast chicken");
    const wrapper = render([roast, entry("2026-10-22", "lunch", "Leek soup")]);

    const target = wrapper
      .findAllComponents({ name: "VueDraggable" })
      .find(c => c.attributes("data-date") === "2026-10-23" && c.attributes("data-type") === "lunch")!;
    const item = document.createElement("div");
    item.dataset.entryId = String(roast.id);
    target.vm.$emit("add", { item });

    expect(wrapper.emitted("move")).toEqual([[{ entryId: roast.id, date: "2026-10-23", entryType: "lunch" }]]);
  });

  test("the add button of a cell emits add with that day and meal type", async () => {
    const wrapper = render([]);

    await cell(wrapper, "2026-10-22", "dinner").find("button.planner-cell__add").trigger("click");

    const [date, type] = wrapper.emitted("add")![0] as [Date, PlanEntryType];
    expect(date.getDate()).toBe(22);
    expect(type).toBe("dinner");
  });

  test("an entry card shows servings only when they differ from the recipe's", () => {
    const wrapper = render([
      entry("2026-10-20", "dinner", "Dal", { recipeScale: 1 }),
      entry("2026-10-21", "dinner", "Paella", { recipeScale: 1.5 }),
    ]);

    expect(cell(wrapper, "2026-10-20", "dinner").text()).not.toMatch(/for \d/);
    expect(cell(wrapper, "2026-10-21", "dinner").text()).toContain("for 6");
  });

  test("a note entry shows its title without a photo", () => {
    const wrapper = render([
      entry("2026-10-20", "dinner", "", { recipe: null, recipeId: null, title: "Eat out" }),
    ]);

    const card = cell(wrapper, "2026-10-20", "dinner");
    expect(card.text()).toContain("Eat out");
    expect(card.find("img").exists()).toBe(false);
  });

  test("the entry menu removes the entry", async () => {
    const roast = entry("2026-10-23", "dinner", "Roast chicken");
    const wrapper = render([roast]);

    await cell(wrapper, "2026-10-23", "dinner").find("button[aria-haspopup=menu]").trigger("click");
    const remove = wrapper.findAll("[role=menuitem]").find(i => i.text() === "Remove")!;
    await remove.trigger("click");

    expect(wrapper.emitted("remove")).toEqual([[roast.id]]);
  });

  test("Move to… in the entry menu is a keyboard path to another day", async () => {
    const roast = entry("2026-10-23", "dinner", "Roast chicken");
    const wrapper = render([roast]);

    await cell(wrapper, "2026-10-23", "dinner").find("button[aria-haspopup=menu]").trigger("click");
    await wrapper.findAll("[role=menuitem]").find(i => i.text() === "Move to…")!.trigger("click");
    await flushPromises();

    const days = wrapper.findAll("[role=menuitem]").map(i => i.text());
    expect(days).toContain("Monday 19");
    expect(days).not.toContain("Friday 23");
    await wrapper.findAll("[role=menuitem]").find(i => i.text() === "Monday 19")!.trigger("click");

    expect(wrapper.emitted("move")).toEqual([[{ entryId: roast.id, date: "2026-10-19", entryType: "dinner" }]]);
  });

  test("the mobile day list pins today first with a Today chip", () => {
    const wrapper = render([entry("2026-10-24", "dinner", "Roast chicken")]);

    const sections = wrapper.findAll(".planner-list .planner-list__day");
    expect(sections).toHaveLength(7);
    expect(sections[0]!.attributes("data-date")).toBe("2026-10-24");
    expect(sections[0]!.find(".ds-chip--accent").text()).toBe("Today");
    expect(sections[0]!.text()).toContain("Roast chicken");
    expect(wrapper.findAll(".planner-list .ds-chip--accent")).toHaveLength(1);
  });
});
