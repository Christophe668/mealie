<template>
  <div class="home-side">
    <DsCard class="home-side__card">
      <div class="home-side__row">
        <div class="home-side__text">
          <p class="home-side__key ds-muted">
            {{ $t("home-today.lunch-today") }}
          </p>
          <template v-if="loading">
            <p class="home-side__value">
              <span class="home-side__skeleton" />
            </p>
          </template>
          <template v-else-if="lunch">
            <p class="home-side__value">
              {{ lunchTitle }}
            </p>
            <p v-if="lunchFact" class="home-side__key ds-muted">
              {{ lunchFact }}
            </p>
          </template>
          <p v-else class="home-side__value">
            {{ $t("home-today.nothing-planned") }}
          </p>
        </div>
        <DsButton v-if="!loading" variant="line" :to="lunchTo">
          {{ lunch ? $t("home-today.open") : $t("home-today.plan-lunch") }}
        </DsButton>
      </div>
    </DsCard>

    <DsCard class="home-side__card">
      <div class="home-side__row">
        <div class="home-side__text">
          <p class="home-side__key ds-muted">
            {{ $t("home-today.shopping-list") }}
          </p>
          <template v-if="loading">
            <p class="home-side__value">
              <span class="home-side__skeleton" />
            </p>
          </template>
          <template v-else-if="openList">
            <p class="home-side__value">
              {{ $t("home-today.items-to-buy", { count: openList.openCount }, openList.openCount) }}
            </p>
            <p v-if="openList.name" class="home-side__key ds-muted">
              {{ openList.name }}
            </p>
          </template>
          <p v-else class="home-side__value">
            {{ $t("home-today.no-list") }}
          </p>
        </div>
        <DsButton v-if="!loading" variant="line" :to="listTo">
          {{ openList ? $t("home-today.open-list") : $t("home-today.start-a-list") }}
        </DsButton>
      </div>
    </DsCard>
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import { useTodayFormat, type TodayList } from "~/composables/use-today";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const props = defineProps<{
  lunch: ReadPlanEntry | null;
  openList: TodayList | null;
  loading: boolean;
  groupSlug: string;
  plannerTo: string;
}>();

const { timeAndServings } = useTodayFormat();

const lunchTitle = computed(() => props.lunch?.recipe?.name || props.lunch?.title || "");
const lunchFact = computed(() => timeAndServings(props.lunch?.recipe, props.lunch?.recipeScale ?? 1));
const lunchTo = computed(() => {
  const slug = props.lunch?.recipe?.slug;
  return slug ? `/g/${props.groupSlug}/r/${slug}` : props.plannerTo;
});
const listTo = computed(() => (props.openList ? `/shopping-lists/${props.openList.id}` : "/shopping-lists"));
</script>

<style scoped>
.home-side {
  display: grid;
  grid-template-rows: 1fr 1fr;
  gap: calc(var(--ds-space) * 3);
}

.home-side__card {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.home-side__row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 1.5);
}

.home-side__text {
  min-width: 0;
}

.home-side__key {
  margin: 0 0 calc(var(--ds-space) * 0.5);
  font-size: var(--ds-t-2);
}

.home-side__key + .home-side__value,
.home-side__value + .home-side__key {
  margin-top: calc(var(--ds-space) * 0.5);
}

.home-side__value {
  display: -webkit-box;
  margin: 0;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-size: var(--ds-t-4);
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.25;
}

.home-side__skeleton {
  display: block;
  width: 8em;
  height: 1em;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-border);
}

@media (max-width: 1023px) {
  .home-side {
    grid-template-rows: none;
    gap: calc(var(--ds-space) * 1.5);
  }
}
</style>
