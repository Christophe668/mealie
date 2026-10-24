import { addDays, differenceInCalendarDays, differenceInCalendarMonths, format, parseISO, startOfDay, subDays } from "date-fns";
import { useUserApi } from "~/composables/api";
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

  async function loadPlan() {
    const { data } = await api.mealplans.getAll(1, -1, {
      start_date: ymd(weekStart.value),
      end_date: ymd(addDays(weekStart.value, 6)),
    });
    plan.value = data?.items ?? [];

    const slug = tonight.value?.recipe?.slug;
    tonightLastMade.value = slug ? (await lookUpLastMade(slug)) ?? null : null;
  }

  async function loadList() {
    const { data } = await api.shopping.lists.getAll(1, 1, { orderBy: "updated_at", orderDirection: "desc" });
    const summary = data?.items?.[0];
    if (!summary) {
      openList.value = null;
      return;
    }
    // The paginated list endpoint returns summaries without items, so the count needs the list itself.
    const { data: list } = await api.shopping.lists.getOne(summary.id);
    openList.value = list
      ? {
          id: list.id,
          name: list.name || summary.name || "",
          openCount: (list.listItems ?? []).filter(item => !item.checked).length,
        }
      : null;
  }

  async function loadShelves() {
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
    makeAgain.value = again.data?.items ?? [];
    recent.value = latest.data?.items ?? [];

    // Recipe summaries carry no household last-made date; it is a per-recipe lookup.
    const entries = await Promise.all(
      makeAgain.value
        .map(recipe => recipe.slug)
        .filter((slug): slug is string => !!slug)
        .map(async slug => [slug, await lookUpLastMade(slug)] as const),
    );
    lastMade.value = Object.fromEntries(entries.filter(([, value]) => value !== undefined));
  }

  async function loadConnections() {
    const { data } = await api.mcpConnections.getConnections();
    hasConnection.value = data ? data.length > 0 : null;
  }

  async function refresh() {
    loading.value = true;
    today.value = startOfDay(new Date());
    if (!household.value) {
      // The week cannot be framed before the household's first day of week is known.
      await householdActions.refresh();
    }
    await Promise.all([loadPlan(), loadList(), loadShelves(), loadConnections()]);
    loading.value = false;
  }

  async function saveEntry(payload: CreatePlanEntry | UpdatePlanEntry) {
    if ("id" in payload && payload.id !== undefined) {
      await api.mealplans.updateOne(payload.id, payload);
    }
    else {
      await api.mealplans.createOne(payload);
    }
    await loadPlan();
  }

  // Household preferences can arrive (or change) after the first load; reframe the week when they do.
  watch(firstDayOfWeek, () => {
    if (!loading.value) {
      loadPlan();
    }
  });

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
