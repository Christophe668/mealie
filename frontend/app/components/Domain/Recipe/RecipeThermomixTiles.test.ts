import { mount } from "@vue/test-utils";
import { describe, expect, test } from "vitest";
import RecipeThermomixTiles from "./RecipeThermomixTiles.vue";
import CookStep from "~/components/Domain/Cook/CookStep.vue";
import type { ThermomixProgram } from "~/lib/recipe/thermomix";

const stubs = { "v-icon": { template: "<i class=\"v-icon\" aria-hidden=\"true\" />" } };

const program = (extra: Partial<ThermomixProgram> = {}): ThermomixProgram => ({
  time: "15 min", temperature: "100°C", speed: "1", reverse: false, turbo: false, dough: false, ...extra,
});

const tiles = (wrapper: ReturnType<typeof mount>) => wrapper.findAll(".tm__tile").map(t => [t.find(".tm__value").text(), t.find(".tm__label").text()]);

describe("RecipeThermomixTiles", () => {
  test("shows time, temperature and speed like the machine, with extras as pills", () => {
    const wrapper = mount(RecipeThermomixTiles, { props: { program: program({ reverse: true }) }, global: { stubs } });

    expect(tiles(wrapper)).toEqual([["15:00", "Time"], ["100°", "Temp."], ["1", "Speed"]]);
    expect(wrapper.findAll(".tm__extra").map(e => e.text())).toEqual(["Reverse"]);
    expect(wrapper.attributes("aria-label")).toBe("Thermomix: 15 min, 100°C, Speed 1, Reverse");
    expect(wrapper.find("button").exists()).toBe(false);
  });

  test("missing values, Varoma, Turbo and seconds", () => {
    const wrapper = mount(RecipeThermomixTiles, { props: { program: program({ time: "3 sec", temperature: null, speed: null, turbo: true }) }, global: { stubs } });
    expect(tiles(wrapper)).toEqual([["0:03", "Time"], ["—", "Temp."], ["Turbo", "Speed"]]);

    const varoma = mount(RecipeThermomixTiles, { props: { program: program({ temperature: "Varoma", time: null }) }, global: { stubs } });
    expect(tiles(varoma)).toEqual([["—", "Time"], ["Varoma", "Temp."], ["1", "Speed"]]);
  });

  test("in cook mode the time tile is the timer: it shows the countdown and asks to toggle", async () => {
    const wrapper = mount(RecipeThermomixTiles, {
      props: { program: program(), size: "cook", timer: { state: "running", remaining: 754, total: 900 } },
      global: { stubs },
    });
    const button = wrapper.find("button.tm__tile--timer");

    expect(button.text()).toContain("12:34");
    expect(button.text()).toContain("Pause");
    expect(button.attributes("aria-pressed")).toBe("true");
    await button.trigger("click");
    expect(wrapper.emitted("toggle")).toHaveLength(1);
  });
});

describe("CookStep with a Thermomix step", () => {
  const step = { text: "Mettre la semoule. Cuire **15 min**/**100°C**//**vitesse 1**, puis laisser reposer 5 min." };
  const timers = [
    { id: "step-1-timer-0", label: "15 min", total: 900, state: "idle" as const },
    { id: "step-1-timer-1", label: "5 min", total: 300, state: "idle" as const },
  ];

  test("the time tile toggles the matching timer; the other duration keeps its button; settings leave the text", async () => {
    const wrapper = mount(CookStep, { props: { step, number: 2, timers }, global: { stubs } });

    // Two sentences, so two bullets; the settings are gone from the text.
    expect(wrapper.findAll(".cook-step__text li").map(li => li.text())).toEqual(["Mettre la semoule.", "Cuire, puis laisser reposer 5 min."]);
    expect(wrapper.find(".tm__tile--timer").text()).toContain("15:00");
    expect(wrapper.findAll(".cook-step__timers li")).toHaveLength(1);
    expect(wrapper.find(".cook-step__timers").text()).toContain("5 min");

    await wrapper.find(".tm__tile--timer").trigger("click");
    expect(wrapper.emitted("toggle-timer")?.[0]?.[0]).toMatchObject({ id: "step-1-timer-0" });
  });

  test("an ordinary step is unchanged", () => {
    const wrapper = mount(CookStep, { props: { step: { text: "Préchauffer le four à 180°C." }, number: 1, timers: [] }, global: { stubs } });

    expect(wrapper.find(".tm").exists()).toBe(false);
    expect(wrapper.find(".cook-step__text").text()).toBe("Préchauffer le four à 180°C.");
  });
});
