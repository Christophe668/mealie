<template>
  <!-- While the plan loads the card is a plain placeholder: no entries, no "Nothing yet". -->
  <div
    class="home-day"
    :class="{
      'home-day--today': isToday,
      'home-day--empty': !loading && !list.length,
      'home-day--loading': loading,
    }"
    :aria-current="isToday ? 'date' : undefined"
  >
    <span class="home-day__head">
      <span>{{ weekday }}</span>
      <span>{{ dayNumber }}</span>
    </span>

    <VueDraggable
      v-if="!loading"
      v-model="list"
      class="home-day__list"
      group="home-week"
      draggable=".home-day__entry"
      :sort="false"
      :empty-insert-threshold="32"
      :animation="reduceMotion ? 0 : 150"
      :force-fallback="true"
      :fallback-tolerance="4"
      :delay="200"
      :delay-on-touch-only="true"
      ghost-class="home-drag-placeholder"
      chosen-class="home-drag-chosen"
      fallback-class="home-drag-lifted"
      @add="onAdd"
    >
      <div
        v-for="entry in list"
        :key="entry.id"
        class="home-day__entry"
        :data-entry-id="entry.id"
      >
        <NuxtLink :to="entryTo(entry)" class="home-day__link ds-focus" draggable="false">
          <span class="home-day__media">
            <img
              v-if="imageUrl(entry) && !failedImages.has(entry.id)"
              :src="imageUrl(entry)"
              alt=""
              loading="lazy"
              draggable="false"
              @error="failedImages.add(entry.id)"
            >
            <DsIcon v-else name="silverwareForkKnife" :size="22" class="home-day__placeholder" />
          </span>
          <span v-if="showTypes" class="home-day__type">{{ typeLabel(entry) }}</span>
          <span class="home-day__title">{{ entryTitle(entry) }}</span>
        </NuxtLink>
      </div>

      <NuxtLink
        v-if="!list.length"
        :to="plannerTo"
        class="home-day__empty ds-focus ds-muted"
        :aria-label="$t('home-today.plan-day', { day: longDay })"
      >
        {{ $t("home-today.nothing-yet") }}
      </NuxtLink>
    </VueDraggable>
  </div>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import { useMediaQuery } from "@vueuse/core";
import { VueDraggable } from "vue-draggable-plus";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useStaticRoutes } from "~/composables/api";
import { leadEntry } from "~/composables/use-today";
import type { PlanEntryType, ReadPlanEntry } from "~/lib/api/types/meal-plan";

export interface HomeDayMove {
  entryId: number;
  /** yyyy-MM-dd */
  date: string;
}

const props = defineProps<{
  date: Date;
  entries: ReadPlanEntry[];
  isToday: boolean;
  groupSlug: string;
  /** The planner page; an empty day (or a note) links there with `?start=<that day>`. */
  plannerPath: string;
  loading?: boolean;
}>();

const emit = defineEmits<{
  move: [move: HomeDayMove];
}>();

const TYPE_ORDER: PlanEntryType[] = ["breakfast", "lunch", "dinner", "side", "snack", "drink", "dessert"];

const i18n = useI18n();
const { recipeSmallImage } = useStaticRoutes();
const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

const dateKey = computed(() => format(props.date, "yyyy-MM-dd"));
const weekday = computed(() => props.date.toLocaleDateString(i18n.locale.value, { weekday: "short" }));
const dayNumber = computed(() => props.date.getDate());
const longDay = computed(() => props.date.toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" }));
const plannerTo = computed(() => `${props.plannerPath}?start=${dateKey.value}`);

const leadId = computed(() => leadEntry(props.entries)?.id ?? null);

/** The lead (the dinner, else the first entry) first, then the rest in meal order. */
const ordered = computed(() => {
  const rank = (entry: ReadPlanEntry) => TYPE_ORDER.indexOf(entry.entryType ?? "dinner");
  return [...props.entries].sort((a, b) =>
    (a.id === leadId.value ? -1 : b.id === leadId.value ? 1 : rank(a) - rank(b)),
  );
});

// Sortable moves items between the day lists while dragging; they are rebuilt whenever the plan reloads.
const list = ref<ReadPlanEntry[]>([]);
watch(ordered, (entries) => {
  list.value = [...entries];
}, { immediate: true });

/** A lone dinner speaks for itself; any other day names each entry's meal. */
const showTypes = computed(() =>
  list.value.length > 1 || list.value.some(entry => (entry.entryType ?? "dinner") !== "dinner"),
);

function typeLabel(entry: ReadPlanEntry) {
  return i18n.t(`meal-plan.${entry.entryType ?? "dinner"}`);
}

function entryTitle(entry: ReadPlanEntry) {
  return entry.recipe?.name || entry.title || "";
}

function entryTo(entry: ReadPlanEntry) {
  const slug = entry.recipe?.slug;
  return slug ? `/g/${props.groupSlug}/r/${slug}` : plannerTo.value;
}

/** Entries whose photo failed to load; they fall back to the placeholder. Reset when the plan reloads. */
const failedImages = reactive(new Set<number>());
watch(() => props.entries, () => failedImages.clear());

function imageUrl(entry: ReadPlanEntry) {
  const recipe = entry.recipe;
  return recipe?.id && recipe.image ? recipeSmallImage(recipe.id, recipe.image) : "";
}

function onAdd(event: { item: HTMLElement }) {
  const entryId = Number(event.item.dataset.entryId);
  if (Number.isFinite(entryId)) {
    emit("move", { entryId, date: dateKey.value });
  }
}
</script>

<style scoped>
.home-day {
  position: relative;
  display: flex;
  min-height: 168px;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
  color: var(--ds-text);
  scroll-snap-align: start;
  transition: border-color 120ms ease;
}

.home-day:hover {
  border-color: var(--ds-text-2);
}

.home-day--loading {
  border-style: dashed;
  background: transparent;
}

.home-day__head {
  display: flex;
  justify-content: space-between;
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 0.75);
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
}

.home-day--today .home-day__head {
  color: var(--ds-text);
  font-weight: 700;
}

/* The whole body is the drop target, so an empty day takes a drop anywhere below its head. */
.home-day__list {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.home-day__entry {
  cursor: grab;
}

.home-day__entry + .home-day__entry {
  border-top: 1px solid var(--ds-border);
}

.home-day__link {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.25);
  padding-bottom: calc(var(--ds-space) * 1.25);
  color: inherit;
  text-decoration: none;
}

.home-day__link:hover .home-day__title {
  text-decoration: underline;
  text-underline-offset: 3px;
}

.home-day__media {
  display: grid;
  height: 84px;
  margin-bottom: calc(var(--ds-space) * 0.75);
  place-items: center;
  overflow: hidden;
  background: var(--ds-bg);
  color: var(--ds-text-2);
}

.home-day__placeholder {
  opacity: 0.6;
}

.home-day__media img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.home-day__type {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
}

.home-day__title {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-size: var(--ds-t-2);
  font-weight: 500;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.home-day__type,
.home-day__title {
  padding: 0 calc(var(--ds-space) * 1.5);
}

.home-day__empty {
  display: grid;
  flex: 1;
  place-items: center;
  padding: var(--ds-space);
  color: inherit;
  font-size: var(--ds-t-2);
  text-align: center;
  text-decoration: none;
}

/* An entry hovering over an empty day takes the place of its "Nothing yet". */
.home-day__list:has(.home-drag-placeholder) .home-day__empty {
  display: none;
}

.home-day--empty {
  border-style: dashed;
  background: transparent;
}

/* The today mark is a border, so `outline` stays free for the keyboard focus ring. */
.home-day--today,
.home-day--today:hover {
  border: 2px solid var(--ds-text);
}

/* Drag states. The lifted copy is the one floating thing here, so it gets the float shadow. */
.home-drag-placeholder {
  opacity: 0.35;
}

.home-drag-lifted {
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow-float);
  cursor: grabbing;
}

@media (prefers-reduced-motion: reduce) {
  .home-day {
    transition: none;
  }
}
</style>
