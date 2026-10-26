import { mount } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import HomeDayCard from "./HomeDayCard.vue";
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

const DATE = new Date(2026, 9, 26);

let nextId = 1;
function entry(entryType: PlanEntryType, name: string): ReadPlanEntry {
  const id = nextId++;
  return {
    id,
    date: "2026-10-26",
    entryType,
    title: "",
    text: "",
    recipeId: `r${id}`,
    recipeScale: 1,
    groupId: "g",
    userId: "u",
    householdId: "h",
    recipe: { id: `r${id}`, name, slug: name.toLowerCase().replace(/ /g, "-"), image: "abc" },
  };
}

function render(entries: ReadPlanEntry[]) {
  return mount(HomeDayCard, {
    props: { date: DATE, entries, isToday: false, groupSlug: "home", plannerPath: "/planner" },
    global: { stubs },
  });
}

describe("HomeDayCard", () => {
  test("lists every entry with its photo, the dinner first, each named by its meal", () => {
    const wrapper = render([entry("dessert", "Tiramisu"), entry("dinner", "Carbonara"), entry("lunch", "Salad")]);
    const rows = wrapper.findAll(".home-day__entry");
    expect(rows.map(row => row.find(".home-day__title").text())).toEqual(["Carbonara", "Salad", "Tiramisu"]);
    expect(rows.map(row => row.find(".home-day__type").text())).toEqual(["Dinner", "Lunch", "Dessert"]);
    expect(rows.map(row => row.find("img").attributes("src"))).toEqual(["/img/r2", "/img/r3", "/img/r1"]);
  });

  test("a lone dinner carries no meal label", () => {
    const wrapper = render([entry("dinner", "Carbonara")]);
    expect(wrapper.find(".home-day__type").exists()).toBe(false);
  });

  test("an empty day links to the planner on that day", () => {
    const wrapper = render([]);
    expect(wrapper.find(".home-day__empty").attributes("href")).toBe("/planner?start=2026-10-26");
  });

  test("an entry dropped on the day is moved to it", async () => {
    const wrapper = render([]);
    const item = document.createElement("div");
    item.dataset.entryId = "42";
    wrapper.findComponent({ name: "VueDraggable" }).vm.$emit("add", { item });
    expect(wrapper.emitted("move")).toEqual([[{ entryId: 42, date: "2026-10-26" }]]);
  });
});
