<template>
  <section v-if="steps.length" class="read-steps" :aria-labelledby="headingId">
    <h2 :id="headingId" class="read-steps__heading">
      {{ $t("recipe-read.method") }}
    </h2>
    <ol class="read-steps__list">
      <li v-for="(step, index) in items" :key="step.key" class="read-steps__item">
        <h3 v-if="step.title" class="read-steps__section">
          {{ step.title }}
        </h3>
        <div class="read-steps__card">
          <span class="read-steps__number ds-title" aria-hidden="true">{{ index + 1 }}</span>
          <div class="read-steps__body">
            <SafeMarkdown class="read-steps__text ds-body" :source="step.text" />
            <ul v-if="step.timers.length" class="read-steps__timers">
              <li v-for="(timer, tIndex) in step.timers" :key="tIndex">
                <DsChip>
                  <DsIcon name="clockOutline" :size="14" />
                  <span class="read-steps__sr">{{ $t("recipe-read.timer") }}</span>
                  {{ timer.text }}
                </DsChip>
              </li>
            </ul>
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsChip from "~/components/Design/DsChip.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import SafeMarkdown from "~/components/global/SafeMarkdown.vue";
import { findStepTimers } from "~/lib/recipe/step-timers";
import type { RecipeStep } from "~/lib/api/types/recipe";

const props = defineProps<{ steps: RecipeStep[] }>();

const headingId = useId();

const items = computed(() =>
  props.steps.map((step, index) => ({
    key: step.id || `step-${index}`,
    title: step.title?.trim() || "",
    text: step.text || "",
    timers: findStepTimers(step.text),
  })),
);
</script>

<style scoped>
.read-steps__heading {
  margin: 0 0 calc(var(--ds-space) * 2);
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.read-steps__list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.5);
  margin: 0;
  padding: 0;
  list-style: none;
}

.read-steps__section {
  margin: calc(var(--ds-space) * 1.5) 0 var(--ds-space);
  font-size: var(--ds-t-3);
  font-weight: 700;
}

.read-steps__card {
  display: grid;
  grid-template-columns: calc(var(--ds-space) * 4) minmax(0, 1fr);
  gap: calc(var(--ds-space) * 2);
  padding: calc(var(--ds-space) * 2.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
}

.read-steps__number {
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.read-steps__text {
  overflow-wrap: anywhere;
}

.read-steps__text :deep(p) {
  margin: 0;
}

.read-steps__text :deep(p + p) {
  margin-top: var(--ds-space);
}

.read-steps__timers {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin: calc(var(--ds-space) * 1.5) 0 0;
  padding: 0;
  list-style: none;
}

.read-steps__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (max-width: 1023px) {
  .read-steps__card {
    grid-template-columns: calc(var(--ds-space) * 3) minmax(0, 1fr);
    gap: calc(var(--ds-space) * 1.5);
    padding: calc(var(--ds-space) * 2);
  }
}
</style>
