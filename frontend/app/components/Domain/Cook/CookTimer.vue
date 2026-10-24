<template>
  <div class="cook-timer" :class="{ 'cook-timer--done': timer.done }">
    <svg class="cook-timer__ring" viewBox="0 0 36 36" aria-hidden="true">
      <circle class="cook-timer__track" cx="18" cy="18" r="15.5" />
      <circle
        class="cook-timer__progress"
        cx="18"
        cy="18"
        r="15.5"
        :stroke-dasharray="CIRCUMFERENCE"
        :stroke-dashoffset="CIRCUMFERENCE * (1 - fraction)"
      />
    </svg>
    <div class="cook-timer__text">
      <span class="cook-timer__time">{{ clock }}</span>
      <span class="cook-timer__label">{{ timer.done ? $t("cook.timer-done") : (timer.name ?? caption) }}</span>
    </div>
    <div class="cook-timer__actions">
      <button
        v-if="!timer.done"
        type="button"
        class="cook-timer__btn ds-focus"
        :aria-label="`${$t(timer.running ? 'cook.timer-pause' : 'cook.timer-resume')}, ${caption}`"
        @click="emit(timer.running ? 'pause' : 'resume')"
      >
        <DsIcon :name="timer.running ? 'pause' : 'play'" :size="20" />
      </button>
      <button
        type="button"
        class="cook-timer__btn ds-focus"
        :aria-label="`${$t('cook.timer-reset')}, ${caption}`"
        @click="emit('reset')"
      >
        <DsIcon name="refresh" :size="20" />
      </button>
      <button
        type="button"
        class="cook-timer__btn ds-focus"
        :aria-label="`${$t('cook.timer-dismiss')}, ${caption}`"
        @click="emit('dismiss')"
      >
        <DsIcon name="close" :size="20" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import type { CookTimer } from "~/composables/use-cook-timers";

const props = defineProps<{
  timer: CookTimer;
  /** "Fry the guanciale, 5 minutes, step 2" (or just "5 minutes, step 2"); shown when the timer has no name, always used for aria. */
  caption: string;
}>();

const emit = defineEmits<{
  (e: "pause" | "resume" | "reset" | "dismiss"): void;
}>();

const CIRCUMFERENCE = 2 * Math.PI * 15.5;

const fraction = computed(() => (props.timer.total ? props.timer.remaining / props.timer.total : 0));

const pad = (n: number) => String(n).padStart(2, "0");
const clock = computed(() => {
  const s = props.timer.remaining;
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const seconds = s % 60;
  return hours ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${pad(minutes)}:${pad(seconds)}`;
});
</script>

<style scoped>
/* A floating thing, so it is the one place cook mode casts a shadow. */
.cook-timer {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  padding: var(--ds-space) var(--ds-space) var(--ds-space) calc(var(--ds-space) * 1.25);
  border: 1px solid var(--ds-border);
  border-radius: 999px;
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow-float);
  color: var(--ds-text);
}

.cook-timer__ring {
  flex: none;
  width: 36px;
  height: 36px;
  transform: rotate(-90deg);
}

.cook-timer__track,
.cook-timer__progress {
  fill: none;
  stroke-width: 3;
}

.cook-timer__track {
  stroke: var(--ds-border);
}

.cook-timer__progress {
  stroke: currentColor;
  stroke-linecap: round;
  transition: stroke-dashoffset 250ms linear;
}

.cook-timer__text {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.cook-timer__time {
  font-size: var(--ds-t-5);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.cook-timer__label {
  overflow: hidden;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cook-timer__actions {
  display: flex;
  gap: calc(var(--ds-space) * 0.5);
}

.cook-timer__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.cook-timer__btn:hover {
  background: color-mix(in srgb, currentColor 12%, transparent);
}

/* Done: the pill turns saffron with ink text until dismissed. */
.cook-timer--done {
  border-color: var(--ds-accent);
  background: var(--ds-accent);
  color: var(--ds-accent-text);
}

.cook-timer--done .cook-timer__label {
  color: var(--ds-accent-text);
  font-weight: 600;
}

.cook-timer--done .cook-timer__track {
  stroke: color-mix(in srgb, var(--ds-accent-text) 25%, transparent);
}

.cook-timer--done .cook-timer__btn:focus-visible {
  outline-color: var(--ds-accent-text);
}

@media (prefers-reduced-motion: reduce) {
  .cook-timer__progress {
    transition: none;
  }
}
</style>
