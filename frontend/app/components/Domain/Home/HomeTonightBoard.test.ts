import { mount } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import HomeTonightBoard from "./HomeTonightBoard.vue";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

vi.mock("~/composables/api", () => ({
  useStaticRoutes: () => ({ recipeImage: (id: string) => `/img/${id}` }),
}));

const NuxtLink = { props: ["to"], template: "<a :href=\"to\"><slot /></a>" };

const TODAY = new Date(2026, 9, 29);

function entry(recipe: Partial<NonNullable<ReadPlanEntry["recipe"]>> | null): ReadPlanEntry {
  return {
    id: 1,
    date: "2026-10-29",
    entryType: "dinner",
    title: recipe ? "" : "Leftovers",
    text: "",
    recipeId: recipe ? "r1" : null,
    recipeScale: 1,
    recipe: recipe ? { id: "r1", name: "Roast chicken", slug: "roast-chicken", image: "abc", ...recipe } : null,
  } as ReadPlanEntry;
}

function mountBoard(planned: ReadPlanEntry | null) {
  return mount(HomeTonightBoard, {
    props: { entry: planned, loading: false, groupSlug: "home", plannerTo: "/plan", today: TODAY },
    global: {
      components: { NuxtLink },
      stubs: { DsButton: { template: "<button><slot /></button>" }, DsIcon: true },
    },
  });
}

describe("HomeTonightBoard", () => {
  test("the title and the photo open tonight's recipe", () => {
    const wrapper = mountBoard(entry({}));

    const title = wrapper.get(".home-board__title a");
    expect(title.attributes("href")).toBe("/g/home/r/roast-chicken");
    expect(title.text()).toBe("Roast chicken");

    const photo = wrapper.get(".home-board__photo");
    expect(photo.element.tagName).toBe("A");
    expect(photo.attributes("href")).toBe("/g/home/r/roast-chicken");
    expect(photo.attributes("tabindex")).toBe("-1");
  });

  test("a note without a recipe is plain text", () => {
    const wrapper = mountBoard(entry(null));

    expect(wrapper.find(".home-board__title a").exists()).toBe(false);
    expect(wrapper.get(".home-board__title").text()).toBe("Leftovers");
    expect(wrapper.get(".home-board__photo").element.tagName).toBe("DIV");
  });
});
