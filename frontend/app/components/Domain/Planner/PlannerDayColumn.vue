<template>
  <div
    class="planner-day"
    :class="{ 'planner-day--today': isToday }"
    :data-date="dateKey"
    :style="{ gridRow: `1 / span ${rows.length + 1}` }"
  >
    <h3 class="planner-day__head" :aria-current="isToday ? 'date' : undefined">
      <span class="planner-day__weekday" aria-hidden="true">{{ weekday }}</span>
      <span class="planner-day__number" aria-hidden="true">{{ dayNumber }}</span>
      <span class="planner-day__sr">{{ longDay }}</span>
    </h3>

    <div
      v-for="row in rows"
      :key="row.type"
      class="planner-cell"
      :data-date="dateKey"
      :data-type="row.type"
    >
      <VueDraggable
        v-model="lists[row.type]"
        class="planner-cell__list"
        :data-date="dateKey"
        :data-type="row.type"
        group="planner-week"
        :sort="false"
        :animation="reduceMotion ? 0 : 150"
        force-fallback
        :fallback-tolerance="4"
        filter=".planner-card__kebab"
        :prevent-on-filter="false"
        ghost-class="planner-drag-placeholder"
        chosen-class="planner-drag-chosen"
        fallback-class="planner-drag-lifted"
        @add="onAdd($event, row.type)"
      >
        <PlannerEntryCard
          v-for="entry in lists[row.type]"
          :key="entry.id"
          :entry="entry"
          :group-slug="groupSlug"
          :move-targets="moveTargets"
          :menu-placement="menuPlacement"
          @edit="emit('edit', $event)"
          @remove="emit('remove', $event)"
          @move="emit('move', $event)"
        />
      </VueDraggable>
      <button
        type="button"
        class="planner-cell__add ds-focus"
        :aria-label="$t('planner.add-type-to-day', { type: row.label.toLowerCase(), day: longDay })"
        @click="emit('add', date, row.type)"
      >
        <DsIcon name="createAlt" :size="18" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import { useMediaQuery } from "@vueuse/core";
import { VueDraggable } from "vue-draggable-plus";
import PlannerEntryCard from "./PlannerEntryCard.vue";
import type { PlannerMove, PlannerMoveTarget } from "./PlannerEntryCard.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";

export interface PlannerRow {
  type: PlanEntryType;
  label: string;
  entries: ReadPlanEntry[];
}

const props = withDefaults(defineProps<{
  date: Date;
  rows: PlannerRow[];
  isToday: boolean;
  groupSlug: string;
  moveTargets?: PlannerMoveTarget[];
  menuPlacement?: "bottom-start" | "bottom-end";
}>(), {
  moveTargets: () => [],
  menuPlacement: "bottom-end",
});

const emit = defineEmits<{
  move: [move: PlannerMove];
  add: [date: Date, type: PlanEntryType];
  remove: [entryId: number];
  edit: [entry: ReadPlanEntry];
}>();

const i18n = useI18n();
const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

const dateKey = computed(() => format(props.date, "yyyy-MM-dd"));
const weekday = computed(() => props.date.toLocaleDateString(i18n.locale.value, { weekday: "short" }));
const dayNumber = computed(() => props.date.getDate());
const longDay = computed(() => props.date.toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" }));

// Sortable moves items between these lists while dragging; they are rebuilt whenever the plan reloads.
const lists = ref<Partial<Record<PlanEntryType, ReadPlanEntry[]>>>({});
watch(
  () => props.rows,
  (rows) => {
    lists.value = Object.fromEntries(rows.map(row => [row.type, [...row.entries]]));
  },
  { immediate: true, deep: true },
);

function onAdd(event: { item: HTMLElement }, type: PlanEntryType) {
  const entryId = Number(event.item.dataset.entryId);
  if (Number.isFinite(entryId)) {
    emit("move", { entryId, date: dateKey.value, entryType: type });
  }
}
</script>

<style scoped>
.planner-day {
  display: grid;
  min-width: 0;
  grid-template-rows: subgrid;
}

.planner-day__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 0.5);
  margin: 0;
  padding: 0 calc(var(--ds-space) * 0.5) var(--ds-space);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
}

.planner-day__number {
  display: inline-grid;
  min-width: calc(var(--ds-space) * 3.5);
  height: calc(var(--ds-space) * 3.5);
  place-items: center;
  padding: 0 calc(var(--ds-space) * 0.5);
  border-radius: var(--ds-radius-ctl);
  font-variant-numeric: tabular-nums;
}

.planner-day--today .planner-day__head {
  color: var(--ds-text);
  font-weight: 700;
}

/* The screen's one saffron element on desktop. */
.planner-day--today .planner-day__number {
  background: var(--ds-accent);
  color: var(--ds-accent-text);
}

.planner-day__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.planner-cell {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: calc(var(--ds-space) * 13);
  flex-direction: column;
  gap: var(--ds-space);
  padding: var(--ds-space) 0;
  border-top: 1px solid var(--ds-border);
}

.planner-cell__list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--ds-space);
}

.planner-cell__list > * {
  cursor: grab;
}

/* Quiet "+": shows on hover or keyboard focus; always there where nothing can hover. */
.planner-cell__add {
  display: grid;
  align-self: stretch;
  place-items: center;
  height: calc(var(--ds-space) * 3.5);
  padding: 0;
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
  opacity: 0;
  transition: opacity 120ms ease;
}

.planner-cell:hover .planner-cell__add,
.planner-cell__add:focus-visible {
  opacity: 1;
}

.planner-cell__add:hover {
  border-color: var(--ds-text-2);
  color: var(--ds-text);
}

@media (hover: none) {
  .planner-cell__add {
    opacity: 1;
  }
}

/* Drag states. The lifted copy is the one floating thing here, so it gets the float shadow. */
.planner-drag-placeholder {
  opacity: 0.35;
}

.planner-drag-lifted {
  box-shadow: var(--ds-shadow-float);
  cursor: grabbing;
}

@media (prefers-reduced-motion: reduce) {
  .planner-cell__add {
    transition: none;
  }
}
</style>
