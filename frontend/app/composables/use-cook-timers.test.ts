import { effectScope } from "vue";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { parseDurations, useCookTimers } from "./use-cook-timers";

function setup(onDone?: (timer: { id: string }) => void) {
  const scope = effectScope();
  const timers = scope.run(() => useCookTimers({ onDone }))!;
  return { ...timers, stop: () => scope.stop() };
}

const byId = (list: { id: string }[], id: string) => list.find(t => t.id === id) as { remaining: number; running: boolean; done: boolean } | undefined;

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-24T18:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

describe("parseDurations", () => {
  test("reads step text into seconds", () => {
    expect(parseDurations("Simmer for 10 minutes")).toEqual([600]);
    expect(parseDurations("Braise 1 h 30")).toEqual([5400]);
    expect(parseDurations("Bake 45 min")).toEqual([2700]);
    expect(parseDurations("Add the eggs")).toEqual([]);
  });
});

describe("useCookTimers", () => {
  test("a started timer counts down once a second", () => {
    const { timers, start, stop } = setup();
    start({ id: "a", label: "10 minutes", total: 600 });

    expect(timers.value).toEqual([{ id: "a", label: "10 minutes", total: 600, remaining: 600, running: true, done: false }]);
    vi.advanceTimersByTime(3000);
    expect(byId(timers.value, "a")!.remaining).toBe(597);
    stop();
  });

  test("several timers run independently", () => {
    const { timers, start, pause, stop } = setup();
    start({ id: "a", label: "1 minute", total: 60 });
    start({ id: "b", label: "2 minutes", total: 120 });

    vi.advanceTimersByTime(30_000);
    pause("a");
    vi.advanceTimersByTime(30_000);

    expect(byId(timers.value, "a")).toMatchObject({ remaining: 30, running: false });
    expect(byId(timers.value, "b")).toMatchObject({ remaining: 60, running: true });

    start({ id: "a", label: "1 minute", total: 60 });
    vi.advanceTimersByTime(10_000);
    expect(byId(timers.value, "a")).toMatchObject({ remaining: 20, running: true });
    expect(byId(timers.value, "b")!.remaining).toBe(50);
    stop();
  });

  test("done fires once when a timer reaches zero", () => {
    const onDone = vi.fn();
    const { timers, start, stop } = setup(onDone);
    start({ id: "a", label: "5 seconds", total: 5 });

    vi.advanceTimersByTime(4000);
    expect(onDone).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
    expect(byId(timers.value, "a")).toMatchObject({ remaining: 0, running: false, done: true });

    vi.advanceTimersByTime(10_000);
    expect(onDone).toHaveBeenCalledTimes(1);
    stop();
  });

  test("keeps wall-clock time when the tab is throttled", () => {
    const { timers, start, stop } = setup();
    start({ id: "a", label: "10 minutes", total: 600 });

    // A backgrounded tab may skip ticks; the next one catches up with the clock.
    vi.setSystemTime(new Date("2026-10-24T18:04:00Z"));
    vi.advanceTimersByTime(1000);
    expect(byId(timers.value, "a")!.remaining).toBe(359);
    stop();
  });

  test("reset rewinds and stops a timer; dismiss removes it", () => {
    const { timers, start, reset, dismiss, stop } = setup();
    start({ id: "a", label: "1 minute", total: 60 });
    vi.advanceTimersByTime(20_000);

    reset("a");
    expect(byId(timers.value, "a")).toMatchObject({ remaining: 60, running: false, done: false });
    vi.advanceTimersByTime(5000);
    expect(byId(timers.value, "a")!.remaining).toBe(60);

    dismiss("a");
    expect(timers.value).toEqual([]);
    stop();
  });

  test("starting a finished timer runs it again from the top", () => {
    const { timers, start, stop } = setup();
    start({ id: "a", label: "2 seconds", total: 2 });
    vi.advanceTimersByTime(2000);
    expect(byId(timers.value, "a")!.done).toBe(true);

    start({ id: "a", label: "2 seconds", total: 2 });
    expect(byId(timers.value, "a")).toMatchObject({ remaining: 2, running: true, done: false });
    stop();
  });

  test("leaving clears every timer and stops ticking", () => {
    const onDone = vi.fn();
    const { start, stop } = setup(onDone);
    start({ id: "a", label: "1 second", total: 1 });
    stop();

    vi.advanceTimersByTime(5000);
    expect(onDone).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });
});
