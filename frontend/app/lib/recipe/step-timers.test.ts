import { describe, expect, test } from "vitest";
import { findStepTimers } from "./step-timers";

describe("findStepTimers", () => {
  test("finds minutes and hours in their common spellings", () => {
    expect(findStepTimers("Simmer for 10 minutes, then rest 1 hour.")).toEqual([
      { text: "10 minutes", seconds: 600 },
      { text: "1 hour", seconds: 3600 },
    ]);
    expect(findStepTimers("Bake 25 min").map(t => t.seconds)).toEqual([1500]);
    expect(findStepTimers("Prove 2h, chill 3 hrs, stir 5 mins").map(t => t.seconds)).toEqual([7200, 10800, 300]);
  });

  test("ignores numbers that are not durations", () => {
    expect(findStepTimers("Add 2 eggs and 200 g flour to a 20 cm tin")).toEqual([]);
    expect(findStepTimers("Use 3 handfuls")).toEqual([]);
    expect(findStepTimers("")).toEqual([]);
    expect(findStepTimers(null)).toEqual([]);
  });
});
