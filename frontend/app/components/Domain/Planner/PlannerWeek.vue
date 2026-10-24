<template>
  <div class="planner-week" :class="{ 'planner-week--empty': !entries.length }">
    <!-- Desktop: 7 day columns, one row per meal type in use. -->
    <div
      class="planner-grid ds-desktop-only"
      :style="{ gridTemplateRows: `auto repeat(${rows.length}, minmax(0, auto))` }"
    >
      <div class="planner-grid__labels" :style="{ gridRow: `1 / span ${rows.length + 1}` }" aria-hidden="true">
        <span />
        <span v-for="row in rows" :key="row.type" class="planner-grid__label">{{ row.label }}</span>
      </div>
      <PlannerDayColumn
        v-for="(day, index) in days"
        :key="day.key"
        :date="day.date"
        :rows="day.rows"
        :is-today="isSameDay(day.date, today)"
        :group-slug="groupSlug"
        :move-targets="moveTargets"
        :menu-placement="index < 3 ? 'bottom-start' : 'bottom-end'"
        @move="emit('move', $event)"
        @add="(date, type) => emit('add', date, type)"
        @remove="emit('remove', $event)"
        @edit="emit('edit', $event)"
      />
    </div>

    <!-- Mobile: a list of days, today first. -->
    <PlannerDayList
      class="ds-mobile-only"
      :days="days"
      :today="today"
      :group-slug="groupSlug"
      :move-targets="moveTargets"
      @move="emit('move', $event)"
      @add="(date, type) => emit('add', date, type)"
      @remove="emit('remove', $event)"
      @edit="emit('edit', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { addDays, format, isSameDay } from "date-fns";
import PlannerDayColumn from "./PlannerDayColumn.vue";
import PlannerDayList from "./PlannerDayList.vue";
import type { PlannerDay } from "./PlannerDayList.vue";
import type { PlannerMove, PlannerMoveTarget } from "./PlannerEntryCard.vue";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";

const props = withDefaults(defineProps<{
  /** First day of the week shown. */
  start: Date;
  entries: ReadPlanEntry[];
  /** Every meal type, in display order; rows show the ones in use. */
  mealTypes: PlanEntryType[];
  groupSlug: string;
  today?: Date;
}>(), {
  today: () => new Date(),
});

const emit = defineEmits<{
  move: [move: PlannerMove];
  add: [date: Date, type: PlanEntryType];
  remove: [entryId: number];
  edit: [entry: ReadPlanEntry];
}>();

const i18n = useI18n();

const ymd = (date: Date) => format(date, "yyyy-MM-dd");

const dates = computed(() => Array.from({ length: 7 }, (_, i) => addDays(props.start, i)));

/** Meal types with at least one entry this week, in the given order; dinner always has a row. */
const rowTypes = computed(() =>
  props.mealTypes.filter(type => type === "dinner" || props.entries.some(entry => entry.entryType === type)),
);

const rows = computed(() => rowTypes.value.map(type => ({ type, label: i18n.t(`meal-plan.${type}`) })));

const days = computed<PlannerDay[]>(() =>
  dates.value.map((date) => {
    const key = ymd(date);
    return {
      date,
      key,
      rows: rows.value.map(row => ({
        ...row,
        entries: props.entries.filter(entry => entry.date === key && (entry.entryType ?? "dinner") === row.type),
      })),
    };
  }),
);

function shortDay(date: Date) {
  const weekday = date.toLocaleDateString(i18n.locale.value, { weekday: "long" });
  return `${weekday.charAt(0).toLocaleUpperCase(i18n.locale.value)}${weekday.slice(1)} ${date.getDate()}`;
}

const moveTargets = computed<PlannerMoveTarget[]>(() => dates.value.map(date => ({ date: ymd(date), label: shortDay(date) })));
</script>

<style scoped>
.planner-grid {
  display: grid;
  grid-template-columns: auto repeat(7, minmax(0, 1fr));
  column-gap: calc(var(--ds-space) * 1.25);
}

/* With nothing planned, the add buttons are the next step, so they stay in view. */
.planner-week--empty :deep(.planner-cell__add) {
  opacity: 1;
}

.planner-grid__labels {
  display: grid;
  grid-template-rows: subgrid;
}

.planner-grid__label {
  padding: calc(var(--ds-space) * 1.25) var(--ds-space) 0 0;
  border-top: 1px solid var(--ds-border);
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}
</style>
