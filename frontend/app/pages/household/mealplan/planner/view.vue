<template>
  <div class="plan">
    <div class="plan__bar">
      <nav class="plan__nav" :aria-label="$t('planner.week-navigation')">
        <button
          type="button"
          class="plan__step ds-focus"
          :aria-label="$t('planner.previous-week')"
          :title="$t('planner.previous-week')"
          @click="goToWeek(-1)"
        >
          <DsIcon name="chevronLeft" :size="22" />
        </button>
        <DsButton variant="line" :disabled="isThisWeek" @click="goToThisWeek">
          {{ $t("planner.this-week") }}
        </DsButton>
        <button
          type="button"
          class="plan__step ds-focus"
          :aria-label="$t('planner.next-week')"
          :title="$t('planner.next-week')"
          @click="goToWeek(1)"
        >
          <DsIcon name="chevronRight" :size="22" />
        </button>
      </nav>

      <AppShellMenu
        class="plan__more"
        :items="moreItems"
        :label="$t('planner.more-actions')"
        :trigger-label="$t('planner.more-actions')"
        trigger-class="plan__step ds-focus"
        placement="bottom-end"
      >
        <template #trigger>
          <DsIcon name="dotsVertical" :size="22" />
        </template>
      </AppShellMenu>
    </div>

    <p class="plan__sr" role="status">
      {{ loading ? $t("planner.loading") : "" }}
    </p>

    <p v-if="failed" class="plan__hint plan__hint--error">
      <span class="plan__hint-title">{{ $t("planner.load-failed") }}</span>
      <button type="button" class="plan__retry ds-focus" @click="reload()">
        {{ $t("planner.try-again") }}
      </button>
    </p>

    <p v-else-if="isEmpty" class="plan__hint">
      <span class="plan__hint-title">{{ $t("planner.empty-week") }}</span>
      <span class="ds-muted">{{ $t("planner.empty-week-hint") }}</span>
    </p>

    <PlannerWeek
      :start="weekStart"
      :entries="entries"
      :meal-types="mealTypes"
      :group-slug="groupSlug"
      :today="today"
      :aria-busy="loading ? 'true' : undefined"
      @move="moveEntry"
      @add="addEntry"
      @remove="remove($event)"
      @edit="editEntry"
    />

    <GroupMealPlanEntryDialog
      v-model="dialog.open"
      :entry="dialog.entry"
      :date="dialog.date"
      :default-entry-type="dialog.type"
      @create="create($event)"
      @update="update($event)"
    />
    <RecipeDialogAddToShoppingList
      v-if="shoppingLists"
      v-model="shoppingListDialog"
      :recipes="weekRecipes"
      :shopping-lists="shoppingLists"
      @list-created="addShoppingList"
    />
    <GroupMealPlanCalendarDialog v-model="calendarDialog" />
  </div>
</template>

<script setup lang="ts">
import { nextTick } from "vue";
import { addDays, format, isValid, parseISO, startOfDay } from "date-fns";
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import PlannerWeek from "~/components/Domain/Planner/PlannerWeek.vue";
import type { PlannerMove } from "~/components/Domain/Planner/PlannerEntryCard.vue";
import GroupMealPlanCalendarDialog from "~/components/Domain/Household/GroupMealPlanCalendarDialog.vue";
import GroupMealPlanEntryDialog from "~/components/Domain/Household/GroupMealPlanEntryDialog.vue";
import RecipeDialogAddToShoppingList from "~/components/Domain/Recipe/RecipeDialogAddToShoppingList.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import { useAddToShoppingListDialog } from "~/composables/shopping-list-page/use-add-to-shopping-list-dialog";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useDayRollover } from "~/composables/use-day-rollover";
import { getScaledRecipes, usePlanTypeOptions } from "~/composables/use-group-mealplan";
import { useHouseholdSelf } from "~/composables/use-households";
import { useMealieAuth } from "~/composables/use-mealie-auth";
import { usePlannerWeek } from "~/composables/use-planner-week";
import { startOfHouseholdWeek } from "~/composables/use-today";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";
import type { AppShellMenuItem } from "~/types/application-types";

const route = useRoute();
const router = useRouter();
const i18n = useI18n();
const auth = useMealieAuth();
const { household, actions: householdActions } = useHouseholdSelf();
const { shoppingLists, open: shoppingListDialog, addAllToList, addShoppingList } = useAddToShoppingListDialog();

const ymd = (date: Date) => format(date, "yyyy-MM-dd");

const groupSlug = computed(() => auth.user.value?.groupSlug || "");
const today = useDayRollover();
const firstDayOfWeek = computed(() => household.value?.preferences?.firstDayOfWeek ?? 0);
const mealTypes = usePlanTypeOptions().map(option => option.value);

// The page cached household preferences may be stale (see the classic planner); refresh on entry.
onMounted(() => {
  householdActions.refresh();
});

/** `?start=` may be any day; the planner shows the household week containing it. */
const anchor = computed(() => {
  const raw = typeof route.query.start === "string" ? parseISO(route.query.start) : null;
  return raw && isValid(raw) ? startOfDay(raw) : today.value;
});
const weekStart = computed(() => startOfHouseholdWeek(anchor.value, firstDayOfWeek.value));
const range = computed(() => ({ start: weekStart.value, end: addDays(weekStart.value, 6) }));
const isThisWeek = computed(() => ymd(weekStart.value) === ymd(startOfHouseholdWeek(today.value, firstDayOfWeek.value)));

const { entries, loading, failed, reload, create, update, remove } = usePlannerWeek(range);
const isEmpty = computed(() => !loading.value && !failed.value && entries.value.length === 0);
const weekRecipes = computed(() => getScaledRecipes(entries.value));

/** The query without the planner's own keys; `end` is left over from the classic planner. */
function otherQuery() {
  const { start: _start, end: _end, ...query } = route.query;
  return query;
}

function goToWeek(step: number) {
  router.push({ query: { ...otherQuery(), start: ymd(addDays(weekStart.value, step * 7)) } });
}

function goToThisWeek() {
  router.push({ query: otherQuery() });
}

const weekTitle = computed(() => {
  const formatter = new Intl.DateTimeFormat(i18n.locale.value, { day: "numeric", month: "long" });
  return formatter.formatRange(range.value.start, range.value.end);
});
useAppShellTitle(weekTitle);
useSeoMeta({ title: () => i18n.t("app-shell.plan") });

// =====================================================
// Entries

const dialog = reactive({
  open: false,
  entry: null as ReadPlanEntry | null,
  date: null as Date | null,
  type: null as PlanEntryType | null,
});

function addEntry(date: Date, type: PlanEntryType) {
  Object.assign(dialog, { entry: null, date, type, open: true });
}

function editEntry(entry: ReadPlanEntry) {
  Object.assign(dialog, { entry, date: null, type: null, open: true });
}

async function moveEntry(move: PlannerMove) {
  const entry = entries.value.find(e => e.id === move.entryId);
  if (!entry) {
    return;
  }
  // Reloads either way, so a failed move snaps the card back to where it is saved.
  await update({ ...entry, date: move.date, entryType: move.entryType });
  // The card re-rendered in its new cell; keep keyboard users on it rather than dropping focus to the page.
  await nextTick();
  const kebab = [...document.querySelectorAll<HTMLElement>(`[data-entry-id="${move.entryId}"] [aria-haspopup="menu"]`)]
    .find(el => el.offsetParent !== null);
  kebab?.focus();
}

const moreItems = computed<AppShellMenuItem[]>(() => [
  { key: "list", label: i18n.t("planner.add-week-to-list"), icon: "cartCheck", onSelect: addAllToList },
  { key: "calendar", label: i18n.t("planner.calendar-feed"), icon: "calendar", onSelect: () => (calendarDialog.value = true) },
  { key: "settings", label: i18n.t("planner.settings"), icon: "cog", to: "/household/mealplan/settings", dividerBefore: true },
  {
    key: "classic",
    label: i18n.t("planner.classic-planner"),
    icon: "calendarMultiselect",
    to: `/household/mealplan/planner/edit?start=${ymd(range.value.start)}&end=${ymd(range.value.end)}`,
  },
]);
const calendarDialog = ref(false);
</script>

<style scoped>
.plan {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
}

.plan__bar {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
}

.plan__nav {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
}

.plan__bar :deep(.plan__step) {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 5);
  height: calc(var(--ds-space) * 5);
  padding: 0;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}

.plan__bar :deep(.plan__step:hover) {
  border-color: var(--ds-text-2);
}

.plan__more {
  margin-left: auto;
}

.plan__more :deep(.ds-menu__list) {
  z-index: 6;
}

.plan__hint {
  display: flex;
  flex-wrap: wrap;
  gap: 0 var(--ds-space);
  margin: 0;
  font-size: var(--ds-t-2);
}

.plan__hint-title {
  font-weight: 600;
}

.plan__retry {
  padding: 0;
  border: 0;
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.plan__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (max-width: 1023px) {
  .plan {
    gap: calc(var(--ds-space) * 2);
  }

  .plan__hint {
    flex-direction: column;
  }
}
</style>
