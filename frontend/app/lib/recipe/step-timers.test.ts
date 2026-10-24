import { describe, expect, test } from "vitest";
import { findStepTimers, timerName } from "./step-timers";

const seconds = (text: string) => findStepTimers(text).map(t => t.seconds);

describe("findStepTimers", () => {
  test("finds minutes and hours in their common spellings", () => {
    expect(findStepTimers("Simmer for 10 minutes, then rest 1 hour.")).toMatchObject([
      { text: "10 minutes", minutes: 10, seconds: 600 },
      { text: "1 hour", minutes: 60, seconds: 3600 },
    ]);
    expect(seconds("Bake 25 min")).toEqual([1500]);
    expect(seconds("Prove 2h, chill 3 hrs, stir 5 mins")).toEqual([7200, 10800, 300]);
  });

  test("reads decimals and fractions as one amount", () => {
    expect(findStepTimers("Roast for 1.5 hours")).toMatchObject([{ text: "1.5 hours", minutes: 90, seconds: 5400 }]);
    expect(seconds("Laisser reposer 1,5 h")).toEqual([5400]);
    expect(findStepTimers("Braise 1 1/2 hours")).toMatchObject([{ text: "1 1/2 hours", minutes: 90, seconds: 5400 }]);
    expect(findStepTimers("Chill 1/2 hour")).toMatchObject([{ text: "1/2 hour", minutes: 30, seconds: 1800 }]);
  });

  test("reads Thermomix-style steps", () => {
    expect(findStepTimers("Sauté 3 min/120°C/speed 1, then cook 2 min 30 sec/100°C/speed 2.")).toMatchObject([
      { text: "3 min", seconds: 180, name: "Sauté" },
      { text: "2 min 30 sec", seconds: 150, name: "Cook" },
    ]);
    expect(findStepTimers("Mixer 5 sec/vitesse 5, puis cuire 10 min/100°C/sens inverse/vitesse 1.")).toMatchObject([
      { text: "5 sec", seconds: 5, name: "Mixer" },
      { text: "10 min", seconds: 600, name: "Cuire" },
    ]);
    expect(seconds("Turbo/1 sec/3 times")).toEqual([]);
  });

  test("reads French units", () => {
    expect(findStepTimers("Laisser mijoter 1 heure")).toMatchObject([{ text: "1 heure", minutes: 60, seconds: 3600 }]);
    expect(seconds("Cuire 2 heures, puis encore 1 heure 15.")).toEqual([7200, 4500]);
    expect(seconds("Fouetter 30 secondes, puis 1 seconde de plus")).toEqual([30, 1]);
    expect(seconds("Remuer 10 minutes, réserver 5 min")).toEqual([600, 300]);
    expect(seconds("Cuire 8 à 10 minutes")).toEqual([600]);
    expect(seconds("Saisir 45 s de chaque côté")).toEqual([45]);
  });

  test("reads seconds in English too", () => {
    expect(findStepTimers("Blitz for 20 seconds")).toMatchObject([{ text: "20 seconds", minutes: 0, seconds: 20 }]);
    expect(seconds("Pulse 10 secs, then 5 sec")).toEqual([10, 5]);
  });

  test("an s that starts a word is not seconds", () => {
    expect(seconds("Add 2 shallots and 3 sprigs of thyme")).toEqual([]);
  });

  test("a duration followed by more words still counts", () => {
    expect(seconds("Take it out 10 minutes before cooking")).toEqual([600]);
  });

  test("hours followed by minutes are one timer", () => {
    expect(findStepTimers("Braise 1 h 30")).toMatchObject([{ text: "1 h 30", minutes: 90, seconds: 5400 }]);
    expect(seconds("Bake for 1 hour 20 minutes, then rest 10 min")).toEqual([4800, 600]);
    expect(seconds("Laisser lever 2 h 15.")).toEqual([8100]);
    expect(seconds("Rest 1 h, then add 30 g sugar")).toEqual([3600]);
    expect(seconds("Rest 1 h 30 g butter")).toEqual([3600]);
  });

  test("a range is one timer for its upper bound", () => {
    expect(findStepTimers("Cook 2–3 minutes per side")).toMatchObject([{ text: "2–3 minutes", minutes: 3, seconds: 180 }]);
    expect(seconds("Bake 10-15 min")).toEqual([900]);
  });

  test("ignores numbers that are not durations", () => {
    expect(findStepTimers("Add 2 eggs and 200 g flour to a 20 cm tin")).toEqual([]);
    expect(findStepTimers("Use 3 handfuls")).toEqual([]);
    expect(findStepTimers("")).toEqual([]);
    expect(findStepTimers(null)).toEqual([]);
  });
});

describe("timerName", () => {
  const nameOf = (text: string) => findStepTimers(text).map(t => t.name);

  test("names the action the duration belongs to", () => {
    expect(nameOf("Meanwhile fry the guanciale in a dry, wide pan over medium heat for 5 minutes until the fat renders.")).toEqual(["Fry the guanciale"]);
    expect(nameOf("Bring a large pan of salted water to the boil and cook the spaghetti until just al dente, about 9 minutes.")).toEqual(["Cook the spaghetti"]);
    expect(nameOf("Rest the chicken under foil for 15 minutes while you crush the potatoes.")).toEqual(["Rest the chicken"]);
    expect(nameOf("Put the potatoes in a pan of cold salted water, bring to the boil and simmer for 10 minutes.")).toEqual(["Simmer"]);
    expect(nameOf("Take the chicken out of the fridge 30 minutes before cooking and heat the oven to 220 °C.")).toEqual(["Take the chicken"]);
  });

  test("works in French and keeps several timers apart", () => {
    expect(nameOf("Pendant ce temps, faire revenir les lardons 5 minutes, puis laisser reposer 10 minutes.")).toEqual([
      "Faire revenir les lardons",
      "Laisser reposer",
    ]);
  });

  test("returns null when nothing usable precedes the duration", () => {
    expect(timerName("10 minutes", 0)).toBeNull();
    expect(nameOf("About 2 minutes.")).toEqual([null]);
  });
});
