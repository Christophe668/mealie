import { useUserApi } from "~/composables/api";
import { alertUnreportedError } from "~/composables/use-toast";
import type {
  MealPreferencesOut,
  MealPreferencesUpdate,
  MemberProfileCreate,
  MemberProfileOut,
  MemberProfileUpdate,
} from "~/lib/api/types/household";
import type { RequestResponse } from "~/lib/api/types/non-generated";

/**
 * The household's member profiles and meal habits, and the changes made to them.
 *
 * Every load is stamped; a response that is no longer the latest one is dropped, so a slow load that started
 * before a save can never put the old profiles back on screen. A save that went through updates the one member
 * (or the habits) in place; a failed one says so and reloads, so the screen shows what is saved.
 */
export function useHouseholdProfile() {
  const api = useUserApi();
  const i18n = useI18n();

  const members = ref<MemberProfileOut[]>([]);
  const preferences = ref<MealPreferencesOut | null>(null);
  const loading = ref(true);
  const failed = ref(false);
  /** True once a load went through: until then there is nothing to edit. */
  const loaded = ref(false);
  let seq = 0;

  async function refresh() {
    const stamp = ++seq;
    loading.value = true;
    const { data } = await api.householdProfile.get();
    if (stamp !== seq) {
      return;
    }
    if (data) {
      members.value = data.members ?? [];
      preferences.value = data.preferences ?? null;
      failed.value = false;
      loaded.value = true;
    }
    else {
      failed.value = true;
    }
    loading.value = false;
  }

  /** Runs a change; on failure shows the snackbar (unless the API already showed Mealie's message) and reloads. */
  async function save<T>(request: Promise<Pick<RequestResponse<T>, "data" | "error">>): Promise<T | null> {
    const { data, error } = await request;
    if (error || !data) {
      alertUnreportedError(error, i18n.t("household-profile.save-failed"));
      await refresh();
      return null;
    }
    // Whatever was loading started before this change: it must not overwrite it.
    seq++;
    loading.value = false;
    return data;
  }

  async function createMember(data: MemberProfileCreate) {
    const created = await save(api.householdProfile.createMember(data));
    if (created) {
      members.value = [...members.value, created];
    }
    return created;
  }

  async function updateMember(id: string, changes: MemberProfileUpdate) {
    const updated = await save(api.householdProfile.updateMember(id, changes));
    if (updated) {
      members.value = members.value.map(member => (member.id === id ? updated : member));
    }
    return updated;
  }

  async function removeMember(id: string) {
    const removed = await save(api.householdProfile.deleteMember(id));
    if (removed) {
      members.value = members.value.filter(member => member.id !== id);
    }
    return !!removed;
  }

  async function savePreferences(changes: MealPreferencesUpdate) {
    const saved = await save(api.householdProfile.updatePreferences(changes));
    if (saved) {
      preferences.value = saved;
    }
    return saved;
  }

  refresh();

  return { members, preferences, loading, failed, loaded, refresh, createMember, updateMember, removeMember, savePreferences };
}
