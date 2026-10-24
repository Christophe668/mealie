import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, test } from "vitest";
import PantryList from "./PantryList.vue";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";

const stubs = {
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
};

const today = new Date(2026, 9, 24);

function item(id: string, name: string, extra: Partial<PantryItemOut> = {}): PantryItemOut {
  return { id, name, groupId: "g", householdId: "h", ...extra };
}

const milk = item("milk", "Milk", {
  location: "fridge",
  quantity: 1,
  unit: { id: "u-l", name: "litre", fraction: false },
  useBy: "2026-10-25",
});
const butter = item("butter", "Butter", { location: "fridge", openedOn: "2026-10-21" });
const rice = item("rice", "Rice", { location: "cupboard", boughtOn: "2026-10-19" });
const peas = item("peas", "Peas", { location: "freezer" });
const candles = item("candles", "Birthday candles", { location: "other", useBy: "2027-01-01" });

function render(byLocation: Array<{ location: PantryLocation; items: PantryItemOut[] }>) {
  return mount(PantryList, {
    props: { byLocation, today },
    global: { stubs },
    attachTo: document.body,
  });
}

function headings(wrapper: ReturnType<typeof render>) {
  return wrapper.findAll("section h2").map(h => h.find(".pantry-group__name").text());
}

describe("PantryList", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  test("groups follow Fridge, Freezer, Cupboard, Other whatever order they arrive in", () => {
    const wrapper = render([
      { location: "other", items: [candles] },
      { location: "cupboard", items: [rice] },
      { location: "freezer", items: [peas] },
      { location: "fridge", items: [milk, butter] },
    ]);

    expect(headings(wrapper)).toEqual(["Fridge", "Freezer", "Cupboard", "Other"]);
  });

  test("empty groups are hidden", () => {
    const wrapper = render([
      { location: "fridge", items: [milk] },
      { location: "freezer", items: [] },
      { location: "cupboard", items: [rice] },
    ]);

    expect(headings(wrapper)).toEqual(["Fridge", "Cupboard"]);
  });

  test("each group is a labelled region listing its rows", () => {
    const wrapper = render([{ location: "fridge", items: [milk, butter] }]);
    const section = wrapper.find("section");
    const heading = section.find("h2");

    expect(section.attributes("aria-labelledby")).toBe(heading.attributes("id"));
    expect(section.findAll("li .pantry-row__name").map(n => n.text())).toEqual(["Milk", "Butter"]);
  });

  test("a row shows quantity with unit and one freshness line; only urgent use-by is the accent chip", () => {
    const wrapper = render([
      { location: "fridge", items: [milk, butter] },
      { location: "cupboard", items: [rice] },
      { location: "freezer", items: [peas] },
      { location: "other", items: [candles] },
    ]);
    const row = (id: string) => wrapper.find(`[data-item-id="${id}"]`);

    expect(row("milk").find(".pantry-row__qty").text()).toBe("1 litre");
    expect(row("milk").find(".pantry-row__fresh").text()).toContain("Use by October 25");
    expect(row("milk").find(".ds-chip--accent").exists()).toBe(true);
    expect(row("butter").find(".pantry-row__fresh").text()).toBe("Opened 3 days ago");
    expect(row("rice").find(".pantry-row__fresh").text()).toBe("Bought 5 days ago");
    expect(row("peas").find(".pantry-row__fresh").exists()).toBe(false);
    expect(row("candles").find(".ds-chip--accent").exists()).toBe(false);
    expect(wrapper.findAll(".ds-chip--accent")).toHaveLength(1);
  });

  test("tapping a row asks to edit it", async () => {
    const wrapper = render([{ location: "fridge", items: [milk] }]);

    await wrapper.find("[data-item-id=milk] .pantry-row__main").trigger("click");

    expect(wrapper.emitted("edit")).toEqual([[milk]]);
  });

  test("the row menu offers Opened today, Edit and Remove", async () => {
    const wrapper = render([{ location: "cupboard", items: [rice] }]);
    const trigger = wrapper.find("[data-item-id=rice] button[aria-haspopup=menu]");

    expect(trigger.attributes("aria-label")).toBe("Actions for Rice");
    await trigger.trigger("click");
    const items = wrapper.findAll("[role=menu] [role=menuitem]");
    expect(items.map(i => i.text().trim())).toEqual(["Opened today", "Edit", "Remove"]);

    await items[0]!.trigger("click");
    expect(wrapper.emitted("opened")).toEqual([[rice]]);

    await trigger.trigger("click");
    await wrapper.findAll("[role=menu] [role=menuitem]")[2]!.trigger("click");
    expect(wrapper.emitted("remove")).toEqual([[rice]]);

    await trigger.trigger("click");
    await wrapper.findAll("[role=menu] [role=menuitem]")[1]!.trigger("click");
    expect(wrapper.emitted("edit")).toEqual([[rice]]);
  });
});
