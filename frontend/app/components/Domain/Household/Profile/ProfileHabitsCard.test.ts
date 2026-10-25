import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, test, vi } from "vitest";
import ProfileHabitsCard from "./ProfileHabitsCard.vue";
import type { MealPreferencesOut } from "~/lib/api/types/household";

const stubs = { "v-icon": { template: "<i />" } };

const habits: MealPreferencesOut = {
  id: "p",
  groupId: "g",
  householdId: "h",
  defaultServings: 1,
  quickWeekdays: [0],
  weeknightMaxMinutes: 30,
  weekendMaxMinutes: null,
  favouriteCuisines: ["Thai"],
  notes: null,
};

function render(savePreferences: (changes: object) => Promise<boolean>, preferences: MealPreferencesOut | null = habits) {
  return mount(ProfileHabitsCard, {
    props: { preferences, firstDayOfWeek: 1, savePreferences },
    global: { stubs },
    attachTo: document.body,
  });
}

const stepButton = (wrapper: ReturnType<typeof render>, label: string) => wrapper.find(`button[aria-label='${label}']`);

describe("ProfileHabitsCard", () => {
  test("a reload while editing keeps Claude's changes: Save sends only what was edited here", async () => {
    const save = vi.fn().mockImplementation(async (changes) => {
      await wrapper.setProps({ preferences: { ...wrapper.props("preferences")!, ...changes } });
      return true;
    });
    const wrapper = render(save);

    await stepButton(wrapper, "More servings").trigger("click");
    // Meanwhile Claude set a weekend limit, and the page reloaded.
    await wrapper.setProps({ preferences: { ...habits, weekendMaxMinutes: 90 } });

    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(save).toHaveBeenCalledExactlyOnceWith({ defaultServings: 2 });
    const weekend = wrapper.findAll("select")[1]!.element as HTMLSelectElement;
    expect(weekend.selectedOptions[0]!.textContent!.trim()).toBe("90 minutes");
    expect(wrapper.find("button[type=submit]").attributes("aria-disabled")).toBe("true");
  });

  test("stepping down to Not set keeps focus on the button, which then does nothing", async () => {
    const wrapper = render(vi.fn());
    const minus = stepButton(wrapper, "Fewer servings");
    (minus.element as HTMLElement).focus();

    await minus.trigger("click");
    expect(wrapper.find("output").text()).toBe("Not set");
    expect(minus.attributes("aria-disabled")).toBe("true");
    expect(document.activeElement).toBe(minus.element);

    await minus.trigger("click");
    expect(wrapper.find("output").text()).toBe("Not set");
    await stepButton(wrapper, "More servings").trigger("click");
    expect(wrapper.find("output").text()).toBe("1");
    wrapper.unmount();
  });

  test("clearing the notes sends null, and the first save of a new household sends the edited fields", async () => {
    const save = vi.fn().mockResolvedValue(true);
    const wrapper = render(save, { ...habits, notes: "Batch cook" });

    await wrapper.find("textarea").setValue("   ");
    await wrapper.find("form").trigger("submit");
    expect(save).toHaveBeenLastCalledWith({ notes: null });

    const fresh = render(save, null);
    await fresh.findAll("select")[0]!.setValue("20");
    await fresh.find("form").trigger("submit");
    expect(save).toHaveBeenLastCalledWith({ weeknightMaxMinutes: 20 });
  });
});
