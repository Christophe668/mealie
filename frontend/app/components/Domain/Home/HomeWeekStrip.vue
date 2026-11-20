<template>
  <section :aria-label="$t('home-today.next-days')">
    <DsSectionTitle :title="$t('home-today.next-days')" />
    <ol class="home-week">
      <li
        v-for="day in days"
        :key="day.date.getTime()"
        :data-today="isToday(day.date) ? 'true' : undefined"
      >
        <HomeDayCard
          :date="day.date"
          :entries="day.entries"
          :is-today="isToday(day.date)"
          :group-slug="groupSlug"
          :planner-path="plannerPath"
          :loading="loading"
          @move="emit('move', $event)"
        />
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { isSameDay } from "date-fns";
import HomeDayCard from "./HomeDayCard.vue";
import type { HomeDayMove } from "./HomeDayCard.vue";
import DsSectionTitle from "~/components/Design/DsSectionTitle.vue";
import type { TodayDay } from "~/composables/use-today";

const props = defineProps<{
  days: TodayDay[];
  today: Date;
  groupSlug: string;
  /** The planner page; each empty day links to it with its own date. */
  plannerPath: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  /** An entry dragged onto another day. */
  move: [move: HomeDayMove];
}>();

// The strip starts with today, so it needs no scrolling to bring today into view.
function isToday(date: Date) {
  return isSameDay(date, props.today);
}
</script>

<style scoped>
.home-week {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  /* Each day is as tall as its own meals; a busy day does not stretch the others. */
  align-items: start;
  gap: calc(var(--ds-space) * 1.5);
  margin: 0;
  padding: 0;
  list-style: none;
}

.home-week > li {
  min-width: 0;
}

@media (max-width: 1023px) {
  /* Horizontal snap strip, bleeding to the screen edges like the board above. */
  .home-week {
    grid-auto-columns: 150px;
    grid-auto-flow: column;
    grid-template-columns: none;
    /* 4 px of vertical padding, cancelled by the margin, keeps the cards' focus ring inside the clip box. */
    margin: calc(var(--ds-space) * -0.5) calc(var(--ds-space) * -2);
    padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 2);
    overflow-x: auto;
    scroll-padding-inline: calc(var(--ds-space) * 2);
    scroll-snap-type: x mandatory;
    scrollbar-width: none;
  }
}
</style>
