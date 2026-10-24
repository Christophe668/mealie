import { describe, expect, test } from "vitest";
import { findStepTimers } from "./step-timers";

const seconds = (text: string) => findStepTimers(text).map(t => t.seconds);

describe("findStepTimers", () => {
  test("finds minutes and hours in their common spellings", () => {
    expect(findStepTimers("Simmer for 10 minutes, then rest 1 hour.")).toEqual([
      { text: "10 minutes", minutes: 10, seconds: 600 },
      { text: "1 hour", minutes: 60, seconds: 3600 },
    ]);
    expect(seconds("Bake 25 min")).toEqual([1500]);
    expect(seconds("Prove 2h, chill 3 hrs, stir 5 mins")).toEqual([7200, 10800, 300]);
  });

  test("reads decimals and fractions as one amount", () => {
    expect(findStepTimers("Roast for 1.5 hours")).toEqual([{ text: "1.5 hours", minutes: 90, seconds: 5400 }]);
    expect(seconds("Laisser reposer 1,5 h")).toEqual([5400]);
    expect(findStepTimers("Braise 1 1/2 hours")).toEqual([{ text: "1 1/2 hours", minutes: 90, seconds: 5400 }]);
    expect(findStepTimers("Chill 1/2 hour")).toEqual([{ text: "1/2 hour", minutes: 30, seconds: 1800 }]);
  });

  test("a duration followed by more words still counts", () => {
    expect(seconds("Take it out 10 minutes before cooking")).toEqual([600]);
  });

  test("hours followed by minutes are one timer", () => {
    expect(findStepTimers("Braise 1 h 30")).toEqual([{ text: "1 h 30", minutes: 90, seconds: 5400 }]);
    expect(seconds("Bake for 1 hour 20 minutes, then rest 10 min")).toEqual([4800, 600]);
    expect(seconds("Laisser lever 2 h 15.")).toEqual([8100]);
    expect(seconds("Rest 1 h, then add 30 g sugar")).toEqual([3600]);
    expect(seconds("Rest 1 h 30 g butter")).toEqual([3600]);
  });

  test("a range is one timer for its upper bound", () => {
    expect(findStepTimers("Cook 2–3 minutes per side")).toEqual([{ text: "2–3 minutes", minutes: 3, seconds: 180 }]);
    expect(seconds("Bake 10-15 min")).toEqual([900]);
  });

  test("ignores numbers that are not durations", () => {
    expect(findStepTimers("Add 2 eggs and 200 g flour to a 20 cm tin")).toEqual([]);
    expect(findStepTimers("Use 3 handfuls")).toEqual([]);
    expect(findStepTimers("")).toEqual([]);
    expect(findStepTimers(null)).toEqual([]);
  });
});
