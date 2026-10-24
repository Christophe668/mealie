import { addDays, startOfDay } from "date-fns";
import { tryOnScopeDispose, useEventListener } from "@vueuse/core";

/**
 * Today's date that moves on by itself: a tab left open past midnight picks up the new day when it
 * comes back into view and from a timer set for just after midnight.
 */
export function useDayRollover() {
  const today = ref(startOfDay(new Date()));

  function rollOverIfNewDay() {
    const now = startOfDay(new Date());
    if (now.getTime() !== today.value.getTime()) {
      today.value = now;
    }
  }

  let midnightTimer: ReturnType<typeof setTimeout> | undefined;
  function scheduleMidnight() {
    clearTimeout(midnightTimer);
    const nextMidnight = addDays(startOfDay(new Date()), 1);
    midnightTimer = setTimeout(() => {
      rollOverIfNewDay();
      scheduleMidnight();
    }, nextMidnight.getTime() - Date.now() + 1000);
  }

  if (typeof document !== "undefined") {
    useEventListener(document, "visibilitychange", () => {
      if (document.visibilityState === "visible") {
        rollOverIfNewDay();
      }
    });
    scheduleMidnight();
  }
  tryOnScopeDispose(() => clearTimeout(midnightTimer));

  return today;
}
