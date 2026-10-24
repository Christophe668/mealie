import { addDays, differenceInCalendarDays, differenceInCalendarMonths, format, parseISO, startOfDay, subDays } from "date-fns";
import { tryOnScopeDispose, useEventListener } from "@vueuse/core";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import { useHouseholdSelf } from "~/composables/use-households";
import type { CreatePlanEntry, ReadPlanEntry, UpdatePlanEntry } from "~/lib/api/types/meal-plan";
import type { RecipeSummary } from "~/lib/api/types/recipe";

export interface TodayDay {
  date: Date;
  entries: ReadPlanEntry[];
}

export interface TodayList {
  id: string;
  name: string;
  openCount: number;
}

const SHELF_SIZE = 8;
/** "Make again" means not cooked for at least this long (never-cooked recipes count too). */
const MAKE_AGAIN_AFTER_DAYS = 30;

const ymd = (date: Date) => format(date, "yyyy-MM-dd");

/** First day of the week containing `today`, where `firstDayOfWeek` is 0 = Sunday … 6 = Saturday. */
export function startOfHouseholdWeek(today: Date, firstDayOfWeek: number): Date {
  const day = startOfDay(today);
  return subDays(day, (day.getDay() - firstDayOfWeek + 7) % 7);
}

/** The entry a day card leads with: the dinner, else the first entry. */
export function leadEntry(entries: ReadPlanEntry[]): ReadPlanEntry | null {
  return entries.find(e => e.entryType === "dinner") ?? entries[0] ?? null;
}

/**
 * Data for the Home screen. All fetching lives here; the Home components only render.
 * Failed calls leave their part empty (null or []) rather than throwing.
 */
export function useToday() {
  const api = useUserApi();
  const i18n = useI18n();
  const { household, actions: householdActions } = useHouseholdSelf();

  const today = ref(startOfDay(new Date()));
  const firstDayOfWeek = computed(() => household.value?.preferences?.firstDayOfWeek ?? 0);

  const plan = ref<ReadPlanEntry[]>([]);
  const openList = ref<TodayList | null>(null);
  const makeAgain = ref<RecipeSummary[]>([]);
  const recent = ref<RecipeSummary[]>([]);
  /** Last-made timestamps by recipe slug; null = never cooked. Absent = unknown (lookup failed). */
  const lastMade = ref<Record<string, string | null>>({});
  const tonightLastMade = ref<string | null>(null);
  /** null when the connections call failed, so the caller can say nothing rather than something wrong. */
  const hasConnection = ref<boolean | null>(null);
  const loading = ref(true);
  /** Which loads failed outright (as opposed to coming back empty). */
  const failed = reactive({ plan: false, list: false, shelves: false });

  const weekStart = computed(() => startOfHouseholdWeek(today.value, firstDayOfWeek.value));

  const week = computed<TodayDay[]>(() =>
    Array.from({ length: 7 }, (_, i) => {
      const date = addDays(weekStart.value, i);
      const key = ymd(date);
      return { date, entries: plan.value.filter(e => e.date === key) };
    }),
  );

  const todaysEntries = computed(() => plan.value.filter(e => e.date === ymd(today.value)));
  const lunch = computed(() => todaysEntries.value.find(e => e.entryType === "lunch") ?? null);
  // Lunch has its own card, so a lunch-only day has nothing for tonight.
  const tonight = computed(
    () => todaysEntries.value.find(e => e.entryType === "dinner")
      ?? todaysEntries.value.find(e => e.entryType !== "lunch")
      ?? null,
  );

  async function lookUpLastMade(slug: string): Promise<string | null | undefined> {
    const { data } = await api.households.getCurrentUserHouseholdRecipe(slug);
    return data ? data.lastMade ?? null : undefined;
  }

  // Each loader stamps its request; a response that is no longer the latest one is dropped, so a slow
  // first load cannot overwrite a reload (e.g. after a Swap) that finished before it.
  const seq = { plan: 0, list: 0, shelves: 0, connections: 0 };

  /**
   * Loaders resolve once their own data is in and return a follow-up for the slower per-recipe
   * last-made lookups, so the page can render before those arrive.
   */
  async function loadPlan(): Promise<() => Promise<void>> {
    const stamp = ++seq.plan;
    const { data, error } = await api.mealplans.getAll(1, -1, {
      start_date: ymd(weekStart.value),
      end_date: ymd(addDays(weekStart.value, 6)),
    });
    if (stamp !== seq.plan) {
      return async () => {};
    }
    plan.value = data?.items ?? [];
    failed.plan = !data && !!error;

    const slug = tonight.value?.recipe?.slug;
    tonightLastMade.value = null;
    return async () => {
      if (!slug) {
        return;
      }
      const value = await lookUpLastMade(slug);
      if (stamp === seq.plan) {
        tonightLastMade.value = value ?? null;
      }
    };
  }

  async function loadList() {
    const stamp = ++seq.list;
    const { data, error } = await api.shopping.lists.getAll(1, 1, { orderBy: "updated_at", orderDirection: "desc" });
    const summary = data?.items?.[0];
    if (!summary) {
      if (stamp === seq.list) {
        openList.value = null;
        failed.list = !data && !!error;
      }
      return;
    }
    // The paginated list endpoint returns summaries without items, so the count needs the list itself.
    const { data: list, error: listError } = await api.shopping.lists.getOne(summary.id);
    if (stamp !== seq.list) {
      return;
    }
    failed.list = !list && !!listError;
    openList.value = list
      ? {
          id: list.id,
          name: list.name || summary.name || "",
          openCount: (list.listItems ?? []).filter(item => !item.checked).length,
        }
      : null;
  }

  async function loadShelves(): Promise<() => Promise<void>> {
    const stamp = ++seq.shelves;
    const cutoff = ymd(subDays(today.value, MAKE_AGAIN_AFTER_DAYS));
    const [again, latest] = await Promise.all([
      api.recipes.getAll(1, SHELF_SIZE, {
        orderBy: "last_made",
        orderDirection: "asc",
        // last_made is coalesced to 1900 for never-cooked recipes, so they pass this filter and sort first.
        queryFilter: `lastMade < "${cutoff}"`,
      }),
      api.recipes.getAll(1, SHELF_SIZE, { orderBy: "created_at", orderDirection: "desc" }),
    ]);
    if (stamp !== seq.shelves) {
      return async () => {};
    }
    makeAgain.value = again.data?.items ?? [];
    recent.value = latest.data?.items ?? [];
    failed.shelves = (!again.data && !!again.error) || (!latest.data && !!latest.error);
    lastMade.value = {};

    // Recipe summaries carry no household last-made date; it is a per-recipe lookup. Results fill in
    // one by one as they arrive.
    const slugs = makeAgain.value.map(recipe => recipe.slug).filter((slug): slug is string => !!slug);
    return async () => {
      await Promise.all(slugs.map(async (slug) => {
        const value = await lookUpLastMade(slug);
        if (stamp === seq.shelves && value !== undefined) {
          lastMade.value = { ...lastMade.value, [slug]: value };
        }
      }));
    };
  }

  async function loadConnections() {
    const stamp = ++seq.connections;
    const { data } = await api.mcpConnections.getConnections();
    if (stamp === seq.connections) {
      hasConnection.value = data ? data.length > 0 : null;
    }
  }

  async function refresh() {
    loading.value = true;
    today.value = startOfDay(new Date());
    if (!household.value) {
      // The week cannot be framed before the household's first day of week is known.
      await householdActions.refresh();
    }
    const [planFollowUp, , shelvesFollowUp] = await Promise.all([loadPlan(), loadList(), loadShelves(), loadConnections()]);
    loading.value = false;
    await Promise.all([planFollowUp(), shelvesFollowUp()]);
  }

  async function reloadPlan() {
    const followUp = await loadPlan();
    await followUp();
  }

  /** Creates or updates a plan entry, then reloads the week. Resolves false (and tells the user) on failure. */
  async function saveEntry(payload: CreatePlanEntry | UpdatePlanEntry): Promise<boolean> {
    const { error } = "id" in payload && payload.id !== undefined
      ? await api.mealplans.updateOne(payload.id, payload)
      : await api.mealplans.createOne(payload);
    if (error) {
      alert.error(i18n.t("home-today.save-failed"));
      return false;
    }
    await reloadPlan();
    return true;
  }

  // Household preferences can arrive (or change) after the first load; reframe the week when they do.
  watch(firstDayOfWeek, () => {
    if (!loading.value) {
      reloadPlan();
    }
  });

  // A tab left open past midnight moves on to the new day: checked when the tab comes back into view
  // and by a timer set for just after midnight.
  function rollOverIfNewDay() {
    if (ymd(new Date()) !== ymd(today.value)) {
      refresh();
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

  const loadFailed = computed(() => failed.plan || failed.list || failed.shelves);

  return {
    today,
    tonight,
    tonightLastMade,
    lunch,
    week,
    weekStart,
    openList,
    makeAgain,
    recent,
    lastMade,
    hasConnection,
    loading,
    loadFailed,
    refresh,
    saveEntry,
  };
}

/**
 * "3 days ago", "6 weeks ago", "yesterday": the coarsest unit that still reads naturally.
 * Uses Intl so the phrase follows the UI locale.
 */
export function relativeAgo(iso: string, now: Date, locale: string): string {
  const date = parseISO(iso);
  const days = differenceInCalendarDays(now, date);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (days < 7) {
    return rtf.format(-Math.max(days, 0), "day");
  }
  if (days < 60) {
    return rtf.format(-Math.round(days / 7), "week");
  }
  const months = differenceInCalendarMonths(now, date);
  if (months < 12) {
    return rtf.format(-months, "month");
  }
  return rtf.format(-Math.floor(months / 12), "year");
}

/** Display strings shared by the Home components. Each fact is its own string: no joined meta lines. */
export function useTodayFormat() {
  const i18n = useI18n();

  function duration(recipe: RecipeSummary | null | undefined): string {
    const seconds = recipe?.totalTimeSeconds;
    if (!seconds || seconds <= 0) {
      return recipe?.totalTime?.trim() || "";
    }
    const totalMinutes = Math.round(seconds / 60);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    if (hours && minutes) {
      return i18n.t("home-today.duration-hours-minutes", { hours, minutes: String(minutes).padStart(2, "0") });
    }
    return hours
      ? i18n.t("home-today.duration-hours", { hours })
      : i18n.t("home-today.duration-minutes", { minutes });
  }

  /** "1 h 10 for 4", "1 h 10", "Serves 4" or "". */
  function timeAndServings(recipe: RecipeSummary | null | undefined, scale = 1): string {
    const time = duration(recipe);
    const base = recipe?.recipeServings || 0;
    const servings = base > 0 ? Math.round(base * (scale || 1) * 10) / 10 : 0;
    if (time && servings) {
      return i18n.t("home-today.time-for-servings", { time, servings });
    }
    if (time) {
      return time;
    }
    return servings ? i18n.t("home-today.serves", { servings }) : "";
  }

  /** "Last made 6 weeks ago", "Never cooked" (null), or "" when unknown (undefined). */
  function lastMadeLabel(iso: string | null | undefined, now: Date): string {
    if (iso === undefined) {
      return "";
    }
    if (iso === null) {
      return i18n.t("home-today.never-cooked");
    }
    return i18n.t("home-today.last-made", { when: relativeAgo(iso, now, i18n.locale.value) });
  }

  return { duration, timeAndServings, lastMadeLabel };
}
