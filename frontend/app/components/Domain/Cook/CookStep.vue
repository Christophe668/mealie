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
    <div class="cook-step__head">
      <span class="cook-step__number cook-step__number--current" aria-hidden="true">{{ number }}</span>
      <span v-if="action" class="cook-step__action">
        <DsIcon :name="action.icon" :size="22" />
        {{ $t(`step-action.${action.key}`) }}
      </span>
    </div>
    <div v-if="thermomix" class="cook-step__thermomix">
      <RecipeThermomixTiles
        v-for="(program, pIndex) in thermomix.programs"
        :key="pIndex"
        :program="program"
        size="cook"
        :timer="programTimers[pIndex] ?? null"
        @toggle="programTimers[pIndex] && emit('toggle-timer', programTimers[pIndex]!)"
      />
    </div>
    <!-- Sanitised markdown, as everywhere else steps are shown. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div class="cook-step__text" v-html="html" />
    <ul v-if="otherTimers.length" class="cook-step__timers" role="list">
      <li v-for="timer in otherTimers" :key="timer.id">
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
import DsIcon from "~/components/Design/DsIcon.vue";
import RecipeThermomixTiles from "~/components/Domain/Recipe/RecipeThermomixTiles.vue";
import type { CookTimerSpec } from "~/composables/use-cook-timers";
import type { RecipeStep } from "~/lib/api/types/recipe";
import { stepAction } from "~/lib/recipe/step-action";
import { parseThermomix } from "~/lib/recipe/thermomix";
import { sanitizeMarkdownHtml } from "~/lib/sanitize/markdown";

export type StepTimerState = "idle" | "running" | "paused" | "done";

const props = withDefaults(defineProps<{
  step: RecipeStep;
  number: number;
  kind?: "current" | "previous" | "next";
  timers?: (CookTimerSpec & { state: StepTimerState; remaining?: number })[];
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

const action = computed(() => stepAction(props.step.text));
const thermomix = computed(() => parseThermomix(props.step.text));

const sameTime = (a: string, b: string) => a.trim().replace(/\s+/g, " ").toLowerCase() === b.trim().replace(/\s+/g, " ").toLowerCase();

/** Each Thermomix program's time tile is the step timer for the same duration (in order, each used once). */
const programTimers = computed(() => {
  const free = [...props.timers];
  return (thermomix.value?.programs ?? []).map((program) => {
    const i = program.time ? free.findIndex(timer => sameTime(timer.label, program.time!)) : -1;
    if (i < 0) {
      return undefined;
    }
    const [timer] = free.splice(i, 1);
    return { ...timer!, remaining: timer!.remaining ?? timer!.total };
  });
});

/** Timers not shown as a time tile keep their usual button. */
const otherTimers = computed(() => {
  const used = new Set(programTimers.value.filter(Boolean).map(timer => timer!.id));
  return props.timers.filter(timer => !used.has(timer.id));
});

const html = computed(() => sanitizeMarkdownHtml(marked.parse(thermomix.value?.text ?? props.step.text ?? "", { async: false, breaks: true }) as string, []));

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

.cook-step__head {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 2);
  margin-bottom: var(--ds-space);
}

.cook-step__number--current {
  color: var(--ds-text-2);
  font-size: var(--ds-t-5);
  line-height: 1;
}

.cook-step__action {
  display: inline-flex;
  align-items: center;
  gap: var(--ds-space);
  color: var(--ds-accent);
  font-size: var(--ds-t-2);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.cook-step__thermomix {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.5);
  max-width: 520px;
  margin-bottom: calc(var(--ds-space) * 2);
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
