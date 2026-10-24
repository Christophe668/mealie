import { format } from "date-fns";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { CreatePlanEntry, ReadPlanEntry, UpdatePlanEntry } from "~/lib/api/types/meal-plan";

export interface PlannerRange {
  start: Date;
  end: Date;
}

const ymd = (date: Date) => format(date, "yyyy-MM-dd");

/**
 * The plan entries of the planner's week, and the changes made to them.
 *
 * Every load is stamped; a response that is no longer the latest one is dropped, so a slow request for
 * a week the user has already left (or for the week computed before household preferences arrived)
 * can never overwrite the week on screen.
 */
export function usePlannerWeek(range: MaybeRefOrGetter<PlannerRange>) {
  const api = useUserApi();
  const i18n = useI18n();

  const entries = ref<ReadPlanEntry[]>([]);
  const loading = ref(true);
  const failed = ref(false);
  let seq = 0;

  async function reload() {
    const stamp = ++seq;
    const { start, end } = toValue(range);
    loading.value = true;
    const { data } = await api.mealplans.getAll(1, -1, { start_date: ymd(start), end_date: ymd(end) });
    if (stamp !== seq) {
      return;
    }
    if (data) {
      entries.value = data.items ?? [];
      failed.value = false;
    }
    else {
      failed.value = true;
    }
    loading.value = false;
  }

  // A new week starts blank, so the previous week's entries never sit under the new dates.
  watch(
    () => {
      const { start, end } = toValue(range);
      return `${ymd(start)}/${ymd(end)}`;
    },
    () => {
      entries.value = [];
      failed.value = false;
      reload();
    },
    { immediate: true },
  );

  /** Runs a change, says so if it failed, and reloads either way so the screen shows what is saved. */
  async function save(request: Promise<{ error: unknown }>) {
    const { error } = await request;
    if (error) {
      alert.error(i18n.t("planner.save-failed"));
    }
    await reload();
    return !error;
  }

  return {
    entries,
    loading,
    failed,
    reload,
    create: (payload: CreatePlanEntry) => save(api.mealplans.createOne(payload)),
    update: (payload: UpdatePlanEntry) => save(api.mealplans.updateOne(payload.id, payload)),
    remove: (id: number) => save(api.mealplans.deleteOne(id)),
  };
}
