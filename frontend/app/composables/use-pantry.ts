import { format } from "date-fns";
import { useUserApi } from "~/composables/api";
import { alertUnreportedError } from "~/composables/use-toast";
import { groupByLocation } from "~/lib/pantry/freshness";
import type { PantryItemOut, PantryItemUpdate } from "~/lib/api/types/household";
import type { RequestResponse } from "~/lib/api/types/non-generated";

/** The writable fields of an item, as the full-replace PUT expects them. */
export function toPantryUpdate(item: PantryItemOut, changes: Partial<PantryItemUpdate> = {}): PantryItemUpdate {
  return {
    name: item.name,
    foodId: item.foodId ?? null,
    quantity: item.quantity ?? null,
    unitId: item.unitId ?? null,
    location: item.location,
    boughtOn: item.boughtOn ?? null,
    openedOn: item.openedOn ?? null,
    useBy: item.useBy ?? null,
    source: item.source,
    note: item.note ?? null,
    ...changes,
  };
}

/**
 * The household's pantry and the changes made to it.
 *
 * Every load is stamped; a response that is no longer the latest one is dropped, so a slow load that
 * started before a change can never put the old pantry back on screen.
 */
export function usePantry() {
  const api = useUserApi();
  const i18n = useI18n();

  const items = ref<PantryItemOut[]>([]);
  const loading = ref(true);
  const failed = ref(false);
  let seq = 0;

  async function refresh() {
    const stamp = ++seq;
    loading.value = true;
    const { data } = await api.householdPantry.getAll(1, -1);
    if (stamp !== seq) {
      return;
    }
    if (data) {
      items.value = data.items ?? [];
      failed.value = false;
    }
    else {
      failed.value = true;
    }
    loading.value = false;
  }

  const byLocation = computed(() => groupByLocation(items.value));

  /**
   * Runs a change, says so if it failed (unless the API interceptor already showed Mealie's own message),
   * and reloads either way so the screen shows what is saved.
   */
  async function save(request: Promise<Pick<RequestResponse<unknown>, "error">>) {
    const { error } = await request;
    if (error) {
      alertUnreportedError(error, i18n.t("pantry.save-failed"));
    }
    await refresh();
    return !error;
  }

  function update(id: string, changes: Partial<PantryItemUpdate>) {
    const current = items.value.find(item => item.id === id);
    if (!current) {
      return Promise.resolve(false);
    }
    return save(api.householdPantry.updateOne(id, toPantryUpdate(current, changes)));
  }

  refresh();

  return {
    items,
    byLocation,
    loading,
    failed,
    refresh,
    /** Quick add: a manual item in the cupboard (the server merges it into a same-named item). */
    add: (name: string) => save(api.householdPantry.createOne({ name, source: "manual", location: "cupboard" })),
    /** Puts a removed item back, e.g. from the undo after Remove. */
    restore: (item: PantryItemOut) => save(api.householdPantry.createOne(toPantryUpdate(item))),
    update,
    remove: (id: string) => save(api.householdPantry.deleteOne(id)),
    markOpened: (id: string) => update(id, { openedOn: format(new Date(), "yyyy-MM-dd") }),
  };
}
