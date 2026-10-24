<template>
  <div class="planner-list">
    <template v-for="group in groups" :key="group.key">
      <h3 v-if="group.title" class="planner-list__group">
        {{ group.title }}
      </h3>
      <section
        v-for="day in group.days"
        :key="day.key"
        class="planner-list__day"
        :class="{ 'planner-list__day--today': isToday(day.date) }"
        :data-date="day.key"
        :aria-labelledby="`planner-day-${day.key}`"
      >
        <header class="planner-list__head">
          <h4 :id="`planner-day-${day.key}`" class="planner-list__title" :aria-current="isToday(day.date) ? 'date' : undefined">
            {{ longDay(day.date) }}
          </h4>
          <DsChip v-if="isToday(day.date)" tone="accent">
            {{ $t("planner.today") }}
          </DsChip>
          <button
            type="button"
            class="planner-list__add ds-focus"
            :aria-label="$t('planner.add-to-day', { day: longDay(day.date) })"
            @click="emit('add', day.date, 'dinner')"
          >
            <DsIcon name="createAlt" :size="18" />
            <span aria-hidden="true">{{ $t("planner.add") }}</span>
          </button>
        </header>

        <p v-if="!day.rows.some(row => row.entries.length)" class="planner-list__empty">
          {{ $t("planner.nothing-planned") }}
        </p>
        <template v-for="row in day.rows" :key="row.type">
          <div v-if="row.entries.length" class="planner-list__meal">
            <p class="planner-list__type">
              {{ row.label }}
            </p>
            <PlannerEntryCard
              v-for="entry in row.entries"
              :key="entry.id"
              :entry="entry"
              layout="row"
              :group-slug="groupSlug"
              :move-targets="moveTargets"
              @edit="emit('edit', $event)"
              @remove="emit('remove', $event)"
              @move="emit('move', $event)"
            />
          </div>
        </template>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { isBefore, isSameDay } from "date-fns";
import PlannerEntryCard from "./PlannerEntryCard.vue";
import type { PlannerMove, PlannerMoveTarget } from "./PlannerEntryCard.vue";
import type { PlannerRow } from "./PlannerDayColumn.vue";
import DsChip from "~/components/Design/DsChip.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";

export interface PlannerDay {
  date: Date;
  /** yyyy-MM-dd */
  key: string;
  rows: PlannerRow[];
}

const props = withDefaults(defineProps<{
  days: PlannerDay[];
  today: Date;
  groupSlug: string;
  moveTargets?: PlannerMoveTarget[];
}>(), {
  moveTargets: () => [],
});

const emit = defineEmits<{
  move: [move: PlannerMove];
  add: [date: Date, type: PlanEntryType];
  remove: [entryId: number];
  edit: [entry: ReadPlanEntry];
}>();

const i18n = useI18n();

function isToday(date: Date) {
  return isSameDay(date, props.today);
}

function longDay(date: Date) {
  return date.toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" }).replace(/,/g, "");
}

/** Today pinned first, then the days still ahead, then the days already behind under their own heading. */
const groups = computed(() => {
  const todayIndex = props.days.findIndex(day => isToday(day.date));
  if (todayIndex === -1) {
    return [{ key: "week", title: "", days: props.days }];
  }
  const past = props.days.filter(day => isBefore(day.date, props.today) && !isToday(day.date));
  return [
    { key: "ahead", title: "", days: props.days.slice(todayIndex) },
    ...(past.length ? [{ key: "past", title: i18n.t("planner.earlier-this-week"), days: past }] : []),
  ];
});
</script>

<style scoped>
.planner-list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.planner-list__group {
  margin: var(--ds-space) 0 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
}

.planner-list__day {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.5);
  padding-top: calc(var(--ds-space) * 1.5);
  border-top: 1px solid var(--ds-border);
}

.planner-list__head {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
}

.planner-list__title {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
}

.planner-list__add {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.5);
  min-height: calc(var(--ds-space) * 5);
  margin-left: auto;
  padding: 0 calc(var(--ds-space) * 1.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 600;
  cursor: pointer;
}

.planner-list__empty {
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.planner-list__meal {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space);
}

.planner-list__type {
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}
</style>
