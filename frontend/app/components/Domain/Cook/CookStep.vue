<template>
  <!-- A neighbour is a dimmed preview you can tap to go there. -->
  <button
    v-if="kind !== 'current'"
    type="button"
    class="cook-step cook-step--neighbour ds-focus"
    :class="`cook-step--${kind}`"
    :aria-label="$t('cook.go-to-step', { n: number })"
    @click="emit('select')"
  >
    <span class="cook-step__number" aria-hidden="true">{{ number }}</span>
    <span class="cook-step__preview">{{ plain }}</span>
  </button>

  <div v-else class="cook-step cook-step--current">
    <p v-if="step.title?.trim()" class="cook-step__section">
      {{ step.title }}
    </p>
    <span class="cook-step__number cook-step__number--current" aria-hidden="true">{{ number }}</span>
    <!-- Sanitised markdown, as everywhere else steps are shown. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div class="cook-step__text" v-html="html" />
    <ul v-if="timers.length" class="cook-step__timers" role="list">
      <li v-for="timer in timers" :key="timer.id">
        <DsButton
          variant="ghost"
          :icon="timer.state === 'running' ? 'pause' : 'clockOutline'"
          :aria-pressed="timer.state === 'running' ? 'true' : 'false'"
          @click="emit('toggle-timer', timer)"
        >
          {{ $t(timerActionKey[timer.state], { time: timer.label }) }}
        </DsButton>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { marked } from "marked";
import DsButton from "~/components/Design/DsButton.vue";
import type { CookTimerSpec } from "~/composables/use-cook-timers";
import type { RecipeStep } from "~/lib/api/types/recipe";
import { sanitizeMarkdownHtml } from "~/lib/sanitize/markdown";

export type StepTimerState = "idle" | "running" | "paused" | "done";

const props = withDefaults(defineProps<{
  step: RecipeStep;
  number: number;
  kind?: "current" | "previous" | "next";
  timers?: (CookTimerSpec & { state: StepTimerState })[];
}>(), {
  kind: "current",
  timers: () => [],
});

const emit = defineEmits<{
  (e: "select"): void;
  (e: "toggle-timer", timer: CookTimerSpec): void;
}>();

const timerActionKey: Record<StepTimerState, string> = {
  idle: "cook.start-timer",
  running: "cook.pause-timer",
  paused: "cook.resume-timer",
  done: "cook.restart-timer",
};

const html = computed(() => sanitizeMarkdownHtml(marked.parse(props.step.text || "", { async: false, breaks: true }) as string, []));

/** The preview drops the markup: a neighbour is a hint, not a second copy of the step. */
const plain = computed(() => {
  if (typeof document === "undefined") {
    return props.step.text || "";
  }
  const el = document.createElement("div");
  el.innerHTML = html.value;
  return (el.textContent || "").replace(/\s+/g, " ").trim();
});
</script>

<style scoped>
.cook-step {
  display: block;
  width: 100%;
  font-family: var(--ds-font);
  text-align: left;
}

.cook-step--neighbour {
  display: grid;
  grid-template-columns: calc(var(--ds-space) * 4) minmax(0, 1fr);
  gap: calc(var(--ds-space) * 1.5);
  padding: var(--ds-space) 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  /* Dimmed by colour, not opacity: still a readable tap target (text-2 on ink is about 6.9:1). */
  color: var(--ds-text-2);
  font-size: var(--ds-t-4);
  line-height: 1.35;
  cursor: pointer;
  transition: color 120ms ease;
}

.cook-step--neighbour:hover,
.cook-step--neighbour:focus-visible {
  color: var(--ds-text);
}

.cook-step__preview {
  display: -webkit-box;
  max-width: 60ch;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.cook-step__number {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-variation-settings: "wdth" 92;
}

.cook-step__section {
  margin: 0 0 var(--ds-space);
  color: var(--ds-text-2);
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.cook-step__number--current {
  display: block;
  margin-bottom: var(--ds-space);
  color: var(--ds-text-2);
  font-size: var(--ds-t-5);
  line-height: 1;
}

.cook-step__text {
  max-width: 32ch;
  font-size: var(--ds-t-7);
  font-weight: 500;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.cook-step__text :deep(p) {
  margin: 0;
}

.cook-step__text :deep(p + p) {
  margin-top: calc(var(--ds-space) * 2);
}

.cook-step__timers {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin: calc(var(--ds-space) * 3) 0 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 1023px) {
  .cook-step__text {
    font-size: var(--ds-t-6);
    line-height: 1.2;
  }

  .cook-step--neighbour {
    grid-template-columns: calc(var(--ds-space) * 3) minmax(0, 1fr);
    font-size: var(--ds-t-3);
  }
}

@media (prefers-reduced-motion: reduce) {
  .cook-step--neighbour {
    transition: none;
  }
}
</style>
