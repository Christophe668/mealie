<template>
  <div class="tm" :class="`tm--${size}`" role="group" :aria-label="$t('thermomix.settings', { summary })">
    <!-- A Thermomix program shown like the machine's display: time, temperature, speed, then the extras. -->
    <div class="tm__tiles">
      <button
        v-if="timer"
        type="button"
        class="tm__tile tm__tile--timer ds-focus"
        :class="{ 'tm__tile--running': timer.state === 'running', 'tm__tile--done': timer.state === 'done' }"
        :aria-pressed="timer.state === 'running' ? 'true' : 'false'"
        @click="emit('toggle')"
      >
        <b class="tm__value">{{ clock(timerSeconds) }}</b>
        <span class="tm__label">{{ $t(timerActionKey[timer.state]) }}</span>
      </button>
      <div v-else class="tm__tile">
        <b class="tm__value">{{ programSeconds === null ? "—" : clock(programSeconds) }}</b>
        <span class="tm__label">{{ $t("thermomix.time") }}</span>
      </div>

      <div class="tm__tile">
        <b class="tm__value">{{ temperatureText }}</b>
        <span class="tm__label">{{ $t("thermomix.temperature") }}</span>
      </div>

      <div class="tm__tile">
        <b class="tm__value">
          <DsIcon v-if="program.speed === 'spoon'" name="spoon" :size="size === 'cook' ? 30 : 22" :label="$t('thermomix.spoon')" />
          <DsIcon v-else-if="!program.speed && program.dough" name="knead" :size="size === 'cook' ? 30 : 22" :label="$t('thermomix.dough')" />
          <template v-else-if="!program.speed && program.turbo">{{ $t("thermomix.turbo") }}</template>
          <template v-else>{{ program.speed }}</template>
        </b>
        <span class="tm__label">{{ $t("thermomix.speed") }}</span>
      </div>
    </div>

    <ul v-if="extras.length" class="tm__extras" role="list">
      <li v-for="extra in extras" :key="extra" class="tm__extra">
        {{ extra }}
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import type { ThermomixProgram } from "~/lib/recipe/thermomix";
import { findStepTimers } from "~/lib/recipe/step-timers";

export type ThermomixTimerState = "idle" | "running" | "paused" | "done";

const props = withDefaults(defineProps<{
  program: ThermomixProgram;
  /** "page" on the recipe page, "cook" in cook mode (bigger). */
  size?: "page" | "cook";
  /** Cook mode: the time tile is this timer. */
  timer?: { state: ThermomixTimerState; remaining: number; total: number } | null;
}>(), {
  size: "page",
  timer: null,
});

const emit = defineEmits<{ (e: "toggle"): void }>();

const i18n = useI18n();

const timerActionKey: Record<ThermomixTimerState, string> = {
  idle: "thermomix.start",
  running: "thermomix.pause",
  paused: "thermomix.resume",
  done: "thermomix.restart",
};

const programSeconds = computed(() => (props.program.time ? findStepTimers(props.program.time)[0]?.seconds ?? null : null));
const timerSeconds = computed(() => (props.timer && props.timer.state !== "idle" ? props.timer.remaining : props.timer?.total ?? 0));

/** "15:00", "0:03", or "1:30:00" past an hour. */
function clock(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const ss = String(s).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

const temperatureText = computed(() => {
  const t = props.program.temperature;
  if (!t) {
    return "—";
  }
  return t === "Varoma" ? "Varoma" : t.replace(/C$/u, "");
});

const extras = computed(() => [
  props.program.reverse ? i18n.t("thermomix.reverse") : null,
  props.program.turbo && props.program.speed ? i18n.t("thermomix.turbo") : null,
  props.program.dough && props.program.speed ? i18n.t("thermomix.dough") : null,
].filter((extra): extra is string => !!extra));

/** For screen readers: "15 min, 100°C, Speed 1, Reverse". */
const summary = computed(() => {
  const speed = props.program.speed === "spoon"
    ? i18n.t("thermomix.spoon")
    : props.program.speed
      ? `${i18n.t("thermomix.speed")} ${props.program.speed}`
      : props.program.turbo ? i18n.t("thermomix.turbo") : props.program.dough ? i18n.t("thermomix.dough") : null;
  return [props.program.time, props.program.temperature, speed, ...extras.value].filter(Boolean).join(", ");
});
</script>

<style scoped>
/* The machine's display: dark tiles in both themes. */
.tm {
  --tm-bg: #1b211d;
  --tm-border: #2a322d;
  --tm-text: #eceeea;
  --tm-muted: #9aa49e;
}

.tm__tiles {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--ds-space);
}

.tm__tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 0;
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 0.5);
  border: 1px solid var(--tm-border);
  border-radius: var(--ds-radius-card);
  background: var(--tm-bg);
  color: var(--tm-text);
  font-family: var(--ds-font);
  text-align: center;
}

.tm__value {
  display: flex;
  align-items: center;
  min-height: 1.1em;
  font-size: var(--ds-t-5);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-variation-settings: "wdth" 92;
  line-height: 1.1;
}

.tm__label {
  color: var(--tm-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* Cook mode: the time tile is the timer, in saffron with ink text (as every accent fill). */
.tm__tile--timer {
  border-color: var(--ds-accent);
  background: var(--ds-accent);
  color: var(--ds-accent-text);
  cursor: pointer;
}

.tm__tile--timer .tm__label {
  color: var(--ds-accent-text);
}

.tm__tile--running {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ds-accent) 35%, transparent);
}

.tm__tile--done .tm__value {
  opacity: 0.6;
}

.tm__extras {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin: var(--ds-space) 0 0;
  padding: 0;
  list-style: none;
}

.tm__extra {
  padding: 3px calc(var(--ds-space) * 1.25);
  border: 1px solid var(--ds-accent);
  border-radius: 999px;
  background: var(--tm-bg);
  color: var(--ds-accent);
  font-size: var(--ds-t-1);
  font-weight: 700;
}

.tm--cook .tm__value {
  font-size: var(--ds-t-6);
}

.tm--cook .tm__tile {
  padding: calc(var(--ds-space) * 1.75) calc(var(--ds-space) * 0.5);
}
</style>
