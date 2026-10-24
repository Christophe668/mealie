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

const replace = vi.fn();

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

function render(props: Partial<{ loggedIn: boolean; scale: number; recipe: Recipe }> = {}) {
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
  replace.mockReset();
  updateLastMade.mockClear();
  vi.stubGlobal("useRouter", () => ({ replace }));
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
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
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
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });

  test("Skip still records last made", async () => {
    const wrapper = render();
    await press("End");

    await wrapper.findAll("button").find(b => b.text() === "Skip")!.trigger("click");
    await flushPromises();

    expect(updateLastMade).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("pending-feedback:onion-soup")).toBeNull();
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });

  test("a duration over a day offers no timer", async () => {
    const marinade: Recipe = { ...recipe, recipeInstructions: [{ id: "m1", text: "Marinate for 48 hours, or 2 hours at least." }] };
    const wrapper = render({ recipe: marinade });

    const buttons = wrapper.findAll(".cook-step__timers button").map(b => b.text());
    expect(buttons).toEqual(["Start 2 hours"]);
    await press(" ");
    expect(wrapper.find(".cook-timer__time").text()).toBe("2:00:00");
    wrapper.unmount();
  });

  test("a visitor gets a plain Done that records nothing", async () => {
    const wrapper = render({ loggedIn: false });
    await press("End");

    expect(wrapper.text()).not.toContain("How was it?");
    await wrapper.findAll("button").find(b => b.text() === "Done")!.trigger("click");
    await flushPromises();

    expect(updateLastMade).not.toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
    wrapper.unmount();
  });

  describe("on a phone", () => {
    beforeEach(() => {
      vi.stubGlobal("matchMedia", (media: string) => ({
        matches: true,
        media,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
      }));
    });

    async function renderMobile() {
      const wrapper = render();
      await flushPromises();
      return wrapper;
    }

    const openSheet = async (wrapper: Awaited<ReturnType<typeof renderMobile>>) => {
      await wrapper.findAll("button").find(b => b.text() === "Ingredients")!.trigger("click");
      await flushPromises();
    };

    test("the step's ingredients sit above the step, the full list waits in the sheet", async () => {
      const wrapper = await renderMobile();

      expect(wrapper.find(".cook__aside").exists()).toBe(false);
      const strip = wrapper.find(".cook-ingredients--compact");
      expect(strip.text()).toContain("For this step");
      expect(strip.findAll("li").map(li => li.text())).toEqual(["50 g butter"]);
      // Above the current step in the document.
      const order = strip.element.compareDocumentPosition(wrapper.find(".cook-step--current").element);
      expect(order & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

      await press("ArrowRight");
      expect(wrapper.find(".cook-ingredients--compact").findAll("li").map(li => li.text())).toEqual(["4 onions"]);
      wrapper.unmount();
    });

    test("the open sheet is modal: the rest is inert and the step keys do nothing", async () => {
      const wrapper = await renderMobile();
      await openSheet(wrapper);

      const sheet = wrapper.find("[role=dialog]");
      expect(sheet.attributes("aria-modal")).toBe("true");
      expect(sheet.findAll("input[type=checkbox]")).toHaveLength(3);
      for (const selector of [".cook__bar", ".cook__body", ".cook__controls"]) {
        expect(wrapper.find(selector).attributes()).toHaveProperty("inert");
      }

      await press("ArrowRight");
      await press("End");
      expect(progress(wrapper)).toBe("Step 1 of 3");
      wrapper.unmount();
    });

    test("Tab wraps inside the sheet", async () => {
      const wrapper = await renderMobile();
      await openSheet(wrapper);

      const focusable = wrapper.find("[role=dialog]").findAll("button, input");
      const first = focusable[0]!.element as HTMLElement;
      const last = focusable[focusable.length - 1]!.element as HTMLElement;
      expect(document.activeElement).toBe(first);

      last.focus();
      await focusable[focusable.length - 1]!.trigger("keydown", { key: "Tab" });
      expect(document.activeElement).toBe(first);

      await focusable[0]!.trigger("keydown", { key: "Tab", shiftKey: true });
      expect(document.activeElement).toBe(last);
      wrapper.unmount();
    });

    test("Escape closes the sheet first, then leaves", async () => {
      const wrapper = await renderMobile();
      await openSheet(wrapper);

      await press("Escape");
      expect(wrapper.find("[role=dialog]").exists()).toBe(false);
      expect(wrapper.find(".cook__body").attributes()).not.toHaveProperty("inert");
      expect(replace).not.toHaveBeenCalled();

      await press("Escape");
      expect(replace).toHaveBeenCalledWith("/g/home/r/onion-soup");
      wrapper.unmount();
    });
  });
});
