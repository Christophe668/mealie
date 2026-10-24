<template>
  <NuxtLink
    :to="to"
    class="home-day ds-focus"
    :class="{ 'home-day--today': isToday, 'home-day--empty': !lead }"
    :aria-current="isToday ? 'date' : undefined"
    :aria-label="lead ? undefined : $t('home-today.plan-day', { day: longDay })"
  >
    <span class="home-day__head">
      <span>{{ weekday }}</span>
      <span>{{ dayNumber }}</span>
    </span>

    <template v-if="lead">
      <span class="home-day__media">
        <img
          v-if="imageUrl && !imageFailed"
          :src="imageUrl"
          alt=""
          loading="lazy"
          @error="imageFailed = true"
        >
        <DsIcon v-else name="silverwareForkKnife" :size="22" class="home-day__placeholder" />
      </span>
      <span class="home-day__title">{{ leadTitle }}</span>
      <span v-if="moreCount" class="home-day__more">
        <DsChip>
          <span aria-hidden="true">{{ $t("home-today.more-count", { count: moreCount }) }}</span>
          <span class="home-day__sr">{{ $t("home-today.more-count-label", { count: moreCount }) }}</span>
        </DsChip>
      </span>
    </template>

    <span v-else class="home-day__empty ds-muted">{{ $t("home-today.nothing-yet") }}</span>
  </NuxtLink>
</template>

<script setup lang="ts">
import DsChip from "~/components/Design/DsChip.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useStaticRoutes } from "~/composables/api";
import { leadEntry } from "~/composables/use-today";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const props = defineProps<{
  date: Date;
  entries: ReadPlanEntry[];
  isToday: boolean;
  groupSlug: string;
  /** Where an empty day (or a day led by a note) sends you: the planner. */
  plannerTo: string;
}>();

const i18n = useI18n();
const { recipeSmallImage } = useStaticRoutes();

const lead = computed(() => leadEntry(props.entries));
const moreCount = computed(() => Math.max(props.entries.length - 1, 0));
const leadTitle = computed(() => lead.value?.recipe?.name || lead.value?.title || "");

const weekday = computed(() => props.date.toLocaleDateString(i18n.locale.value, { weekday: "short" }));
const dayNumber = computed(() => props.date.getDate());
const longDay = computed(() => props.date.toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" }));

const imageFailed = ref(false);
const imageUrl = computed(() => {
  const recipe = lead.value?.recipe;
  return recipe?.id && recipe.image ? recipeSmallImage(recipe.id, recipe.image) : "";
});
watch(imageUrl, () => (imageFailed.value = false));

const to = computed(() => {
  const slug = lead.value?.recipe?.slug;
  return slug ? `/g/${props.groupSlug}/r/${slug}` : props.plannerTo;
});
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
  text-decoration: none;
  scroll-snap-align: start;
  transition: border-color 120ms ease;
}

.home-day:hover {
  border-color: var(--ds-text-2);
}

.home-day--today {
  outline: 2px solid var(--ds-text);
  outline-offset: -1px;
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

.home-day__media {
  display: grid;
  height: 84px;
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

.home-day__title {
  display: -webkit-box;
  margin-top: calc(var(--ds-space) * 1.25);
  padding: 0 calc(var(--ds-space) * 1.5);
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-size: var(--ds-t-2);
  font-weight: 500;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.home-day__more {
  padding: var(--ds-space) calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 1.5);
}

.home-day__title:last-child {
  margin-bottom: calc(var(--ds-space) * 1.5);
}

.home-day__empty {
  margin: auto;
  padding: var(--ds-space);
  font-size: var(--ds-t-2);
  text-align: center;
}

.home-day--empty {
  border-style: dashed;
  background: transparent;
}

.home-day__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (prefers-reduced-motion: reduce) {
  .home-day {
    transition: none;
  }
}
</style>
