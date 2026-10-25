import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import ProfileWeekdayToggles from "./ProfileWeekdayToggles.vue";
import { weekdayOrder } from "~/lib/household-profile/profile";

function render(firstDayOfWeek: number, modelValue: number[] = []) {
  return mount(ProfileWeekdayToggles, { props: { modelValue, firstDayOfWeek, label: "Keep cooking quick on" } });
}

const labels = (wrapper: ReturnType<typeof render>) => wrapper.findAll("button").map(b => b.text().trim());

describe("ProfileWeekdayToggles", () => {
  test("starts on the household's first day of the week", () => {
    expect(labels(render(1))).toEqual(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
    expect(labels(render(0))).toEqual(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]);
    expect(labels(render(6))).toEqual(["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"]);
  });

  test("maps Mealie's 0 = Sunday to the API's 0 = Monday", () => {
    expect(weekdayOrder(0)).toEqual([6, 0, 1, 2, 3, 4, 5]);
    expect(weekdayOrder(1)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  test("toggling emits API weekdays (0 = Monday), sorted, and shows the pressed state", async () => {
    const wrapper = render(0, [4]);
    const button = (label: string) => wrapper.findAll("button").find(b => b.text() === label)!;

    expect(button("Fri").attributes("aria-pressed")).toBe("true");
    expect(button("Fri").attributes("aria-label")).toBe("Friday");

    await button("Sun").trigger("click");
    await button("Fri").trigger("click");

    expect(wrapper.emitted("update:modelValue")).toEqual([[[4, 6]], [[]]]);
  });
});
