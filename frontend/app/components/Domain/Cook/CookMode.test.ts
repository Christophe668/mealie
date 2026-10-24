import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import CookMode from "./CookMode.vue";
import CookFinish from "./CookFinish.vue";
import type { Recipe } from "~/lib/api/types/recipe";
import { useLocales } from "~/composables/use-locales";

vi.mock("~/composables/use-locales");

const updateLastMade = vi.fn(async () => ({ data: {} }));
vi.mock("~/composables/api", () => ({
  useUserApi: () => ({ recipes: { updateLastMade } }),
}));

const push = vi.fn();

const stubs = {
  "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" },
  "NuxtLink": { props: ["to"], template: "<a :href=\"to\"><slot /></a>" },
};

const recipe: Recipe = {
  id: "r-1",
  slug: "onion-soup",
  name: "Onion soup",
  recipeServings: 2,
  recipeIngredient: [
    { referenceId: "ing-butter", quantity: 50, unit: { id: "u-g", name: "g", fraction: false }, food: { id: "f-butter", name: "butter" } },
    { referenceId: "ing-onion", quantity: 4, food: { id: "f-onion", name: "onion", pluralName: "onions" } },
    { referenceId: "ing-salt", quantity: 0, note: "salt, to taste" },
  ],
  recipeInstructions: [
    { id: "s1", text: "Melt the butter in a large pan." },
    { id: "s2", text: "Add the onions and cook for 10 minutes." },
    { id: "s3", text: "Season and serve." },
  ],
};

function render(props: Partial<{ loggedIn: boolean; scale: number }> = {}) {
  return mount(CookMode, {
    props: { recipe, backTo: "/g/home/r/onion-soup", loggedIn: true, ...props },
    global: { stubs },
    attachTo: document.body,
  });
}

async function press(key: string, target: EventTarget = window) {
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  await flushPromises();
}

const progress = (wrapper: ReturnType<typeof render>) => wrapper.find(".cook__progress").text();
const current = (wrapper: ReturnType<typeof render>) => wrapper.find(".cook-step--current").text();

beforeEach(() => {
  vi.useFakeTimers();
  sessionStorage.clear();
  push.mockReset();
  updateLastMade.mockClear();
  vi.stubGlobal("useRouter", () => ({ push }));
  vi.mocked(useLocales).mockReturnValue({
    locales: [{ value: "en-US", pluralFoodHandling: "without-unit" }],
    locale: { value: "en-US" },
  } as any);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("CookMode", () => {
  test("starts on the first step and announces the progress", () => {
    const wrapper = render();

    expect(progress(wrapper)).toBe("Step 1 of 3");
    expect(wrapper.find(".cook__progress").attributes("aria-live")).toBe("polite");
    expect(current(wrapper)).toContain("Melt the butter");
    wrapper.unmount();
  });

  test("ArrowRight and ArrowLeft move between steps, within bounds", async () => {
    const wrapper = render();

    await press("ArrowRight");
    expect(progress(wrapper)).toBe("Step 2 of 3");
    expect(current(wrapper)).toContain("Add the onions");

    await press("ArrowLeft");
    await press("ArrowLeft");
    expect(progress(wrapper)).toBe("Step 1 of 3");

    await press("End");
    expect(progress(wrapper)).toBe("Step 3 of 3");
    await press("ArrowRight");
    expect(progress(wrapper)).toBe("Step 3 of 3");
    await press("Home");
    expect(progress(wrapper)).toBe("Step 1 of 3");
    wrapper.unmount();
  });

  test("the ingredients named in the current step are highlighted", async () => {
    const wrapper = render();
    const active = () => wrapper.findAll(".cook-ingredients__item--active").map(row => row.text());

    expect(active()).toEqual([expect.stringContaining("50 g butter")]);
    await press("ArrowRight");
    expect(active()).toEqual([expect.stringContaining("onions")]);
    wrapper.unmount();
  });

  test("Space starts the first timer of the current step", async () => {
    const wrapper = render();

    await press(" ");
    expect(wrapper.findAll(".cook-timer")).toHaveLength(0);

    await press("ArrowRight");
    await press(" ");
    expect(wrapper.findAll(".cook-timer")).toHaveLength(1);
    expect(wrapper.find(".cook-timer__time").text()).toBe("10:00");

    vi.advanceTimersByTime(2000);
    await flushPromises();
    expect(wrapper.find(".cook-timer__time").text()).toBe("09:58");

    // Timers keep running when the step changes.
    await press("ArrowRight");
    vi.advanceTimersByTime(1000);
    await flushPromises();
    expect(wrapper.find(".cook-timer__time").text()).toBe("09:57");
    wrapper.unmount();
  });

  test("Space on a focused button is left to the button", async () => {
    const wrapper = render();
    await press("ArrowRight");

    const button = wrapper.find("button").element as HTMLButtonElement;
    button.focus();
    await press(" ", button);
    expect(wrapper.findAll(".cook-timer")).toHaveLength(0);
    wrapper.unmount();
  });

  test("Escape goes back to the recipe", async () => {
    const wrapper = render();

    await press("Escape");
    expect(push).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });

  test("only the last step shows the finish", async () => {
    const wrapper = render();

    expect(wrapper.findComponent(CookFinish).exists()).toBe(false);
    await press("End");
    expect(wrapper.findComponent(CookFinish).exists()).toBe(true);
    expect(wrapper.text()).toContain("How was it?");
    wrapper.unmount();
  });

  test("a verdict records last made, keeps the verdict and goes back", async () => {
    const wrapper = render();
    await press("End");

    const loved = wrapper.findAll("button").find(b => b.text() === "Loved it")!;
    await loved.trigger("click");
    await flushPromises();

    expect(updateLastMade).toHaveBeenCalledWith("onion-soup", expect.any(String));
    expect(sessionStorage.getItem("pending-feedback:onion-soup")).toBe("loved");
    expect(push).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });

  test("Skip still records last made", async () => {
    const wrapper = render();
    await press("End");

    await wrapper.findAll("button").find(b => b.text() === "Skip")!.trigger("click");
    await flushPromises();

    expect(updateLastMade).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("pending-feedback:onion-soup")).toBeNull();
    expect(push).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });

  test("a visitor gets a plain Done that records nothing", async () => {
    const wrapper = render({ loggedIn: false });
    await press("End");

    expect(wrapper.text()).not.toContain("How was it?");
    await wrapper.findAll("button").find(b => b.text() === "Done")!.trigger("click");
    await flushPromises();

    expect(updateLastMade).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });
});
