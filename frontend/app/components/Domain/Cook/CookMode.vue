<template>
  <div class="ds-cook cook">
    <header class="cook__bar" :inert="sheetOpen || undefined">
      <DsButton variant="ghost" size="lg" icon="close" :aria-label="$t('cook.exit-label')" @click="exit">
        {{ $t("cook.exit") }}
      </DsButton>
      <p class="cook__title">
        {{ recipe.name }}
      </p>
      <p v-if="total" class="cook__progress" aria-live="polite" aria-atomic="true">
        {{ $t("cook.progress", { current: index + 1, total }) }}
      </p>
    </header>

    <div class="cook__body" :style="{ '--cook-timer-count': timers.length }" :inert="sheetOpen || undefined">
      <div class="cook__steps">
        <p v-if="!total" class="cook__empty">
          {{ $t("cook.no-steps") }}
        </p>
        <template v-else>
          <div class="cook__before">
            <CookStep
              v-if="index > 0"
              :step="steps[index - 1]!"
              :number="index"
              kind="previous"
              @select="go(index - 1)"
            />
          </div>
          <!-- Mobile: what this step needs, above it; the sheet keeps the full list. -->
          <CookIngredients
            v-if="isMobile && activeIngredients.length"
            compact
            class="cook__strip"
            :ingredients="ingredients"
            :active="activeIngredients"
            :scale="scale"
            :recipe-slug="recipe.slug || ''"
            :group-slug="groupSlug"
          />
          <Transition name="cook-step" mode="out-in">
            <CookStep
              :key="index"
              :step="currentStep!"
              :number="index + 1"
              :timers="currentTimers"
              class="cook__current"
              @toggle-timer="toggleTimer"
            />
          </Transition>
          <CookStep
            v-if="!isLast"
            :step="steps[index + 1]!"
            :number="index + 2"
            kind="next"
            class="cook__after"
            @select="go(index + 1)"
          />
        </template>
        <CookFinish
          v-if="isLast"
          class="cook__finish"
          :recipe-slug="recipe.slug || ''"
          :back-to="backTo"
          :logged-in="loggedIn"
        />
      </div>

      <aside v-if="!isMobile && ingredients.length" class="cook__aside">
        <CookIngredients
          :ingredients="ingredients"
          :active="activeIngredients"
          :scale="scale"
          :recipe-slug="recipe.slug || ''"
          :group-slug="groupSlug"
        />
      </aside>
    </div>

    <div v-if="timers.length" class="cook__timers" role="region" :aria-label="$t('cook.timers')" :inert="sheetOpen || undefined">
      <CookTimer
        v-for="timer in timers"
        :key="timer.id"
        :timer="timer"
        :caption="timerCaption(timer)"
        @pause="pause(timer.id)"
        @resume="start(timer)"
        @reset="reset(timer.id)"
        @dismiss="dismiss(timer.id)"
      />
    </div>
    <p class="cook-sr-only" aria-live="assertive">
      {{ doneAnnouncement }}
    </p>

    <nav v-if="total" class="cook__controls" :inert="sheetOpen || undefined">
      <DsButton variant="ghost" size="lg" icon="chevronLeft" :disabled="index === 0" @click="go(index - 1)">
        <span class="cook__control-label">{{ $t("cook.previous-step") }}</span>
      </DsButton>
      <DsButton
        v-if="isMobile && ingredients.length"
        ref="sheetToggle"
        variant="ghost"
        size="lg"
        icon="formatListCheck"
        :aria-expanded="sheetOpen ? 'true' : 'false'"
        aria-controls="cook-ingredients-sheet"
        @click="openSheet"
      >
        {{ $t("cook.show-ingredients") }}
      </DsButton>
      <DsButton variant="line" size="lg" :disabled="isLast" class="cook__next" @click="go(index + 1)">
        <span class="cook__control-label">{{ $t("cook.next-step") }}</span>
        <DsIcon name="chevronRight" :size="18" />
      </DsButton>
    </nav>

    <!-- Mobile: the ingredients in a bottom sheet over the step. -->
    <Transition name="cook-sheet">
      <div v-if="isMobile && sheetOpen" class="cook__sheet-scrim" @click.self="closeSheet">
        <div
          id="cook-ingredients-sheet"
          ref="sheet"
          class="cook__sheet"
          role="dialog"
          aria-modal="true"
          :aria-label="$t('cook.ingredients')"
          @keydown.tab="trapTab"
        >
          <button ref="sheetClose" type="button" class="cook__sheet-close ds-focus" :aria-label="$t('cook.close-ingredients')" @click="closeSheet">
            <DsIcon name="close" :size="22" />
          </button>
          <CookIngredients
            :ingredients="ingredients"
            :active="activeIngredients"
            :scale="scale"
            :recipe-slug="recipe.slug || ''"
            :group-slug="groupSlug"
          />
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { useEventListener, useMediaQuery } from "@vueuse/core";
import CookFinish from "./CookFinish.vue";
import CookIngredients from "./CookIngredients.vue";
import CookStep from "./CookStep.vue";
import type { StepTimerState } from "./CookStep.vue";
import CookTimer from "./CookTimer.vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useCookTimers } from "~/composables/use-cook-timers";
import type { CookTimer as CookTimerState, CookTimerSpec } from "~/composables/use-cook-timers";
import { useWakeLock } from "~/composables/use-wake-lock";
import type { Recipe } from "~/lib/api/types/recipe";
import { ingredientsInStep } from "~/lib/recipe/step-ingredients";
import { findStepTimers } from "~/lib/recipe/step-timers";

const props = withDefaults(defineProps<{
  recipe: Recipe;
  /** The recipe page: Escape, Exit and the finish all lead there. */
  backTo: string;
  /** The read page's scale, so quantities match what you were reading. */
  scale?: number;
  groupSlug?: string;
  /** Signed in to the recipe's group: the finish records last made. */
  loggedIn?: boolean;
}>(), {
  scale: 1,
  groupSlug: "",
  loggedIn: false,
});

const i18n = useI18n();
const router = useRouter();
const isMobile = useMediaQuery("(max-width: 1023px)");

useWakeLock();

const steps = computed(() => props.recipe.recipeInstructions ?? []);
const ingredients = computed(() => props.recipe.recipeIngredient ?? []);
const total = computed(() => steps.value.length);

const index = ref(0);
const currentStep = computed(() => steps.value[index.value]);
const isLast = computed(() => index.value >= total.value - 1);

function go(to: number) {
  index.value = Math.min(Math.max(to, 0), Math.max(total.value - 1, 0));
}

// Replace, so Back from the recipe does not land in cook mode again.
function exit() {
  router.replace(props.backTo);
}

const activeIngredients = computed(() => ingredientsInStep(ingredients.value, currentStep.value));

/* Timers: parsed from each step's text; started ones live on across step changes until dismissed or exit. */
const announced = ref("");
const { timers, start, pause, toggle, reset, dismiss } = useCookTimers({
  onDone: (timer) => {
    announced.value = i18n.t("cook.timer-done-announce", { time: timer.label, n: stepOf(timer.id) });
  },
});
const doneAnnouncement = computed(() => announced.value);

const timerId = (step: number, n: number) => `step-${step}-timer-${n}`;
const stepOf = (id: string) => Number(id.split("-")[1]) + 1;

/** A day at most: "marinate for 48 hours" is a plan, not a countdown. */
const MAX_TIMER_SECONDS = 24 * 3600;

function stepTimers(step: number): CookTimerSpec[] {
  return findStepTimers(steps.value[step]?.text)
    .map((timer, n) => ({ id: timerId(step, n), label: timer.text, name: timer.name ?? undefined, total: timer.seconds }))
    .filter(timer => timer.total <= MAX_TIMER_SECONDS);
}

function stateOf(id: string): StepTimerState {
  const timer = timers.value.find(t => t.id === id);
  if (!timer) {
    return "idle";
  }
  return timer.done ? "done" : timer.running ? "running" : "paused";
}

const currentTimers = computed(() => stepTimers(index.value).map(spec => ({ ...spec, state: stateOf(spec.id) })));

function toggleTimer(spec: CookTimerSpec) {
  toggle(spec);
}

/** "Fry the guanciale, 5 minutes, step 2" — the name first when the step gives one. */
function timerCaption(timer: CookTimerState) {
  const detail = `${timer.label}, ${i18n.t("cook.timer-step", { n: stepOf(timer.id) })}`;
  return timer.name ? `${timer.name}, ${detail}` : detail;
}

/*
 * Mobile ingredient sheet, a modal: everything else is inert while it is open, Tab wraps inside it,
 * focus moves in on open and back to its toggle on close.
 */
const sheetOpen = ref(false);
const sheet = useTemplateRef<HTMLElement>("sheet");
const sheetClose = useTemplateRef<HTMLButtonElement>("sheetClose");
const sheetToggle = useTemplateRef<{ $el: HTMLElement }>("sheetToggle");

async function openSheet() {
  sheetOpen.value = true;
  await nextTick();
  sheetClose.value?.focus();
}

async function closeSheet() {
  sheetOpen.value = false;
  await nextTick();
  sheetToggle.value?.$el?.focus?.();
}

const FOCUSABLE = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

function trapTab(event: KeyboardEvent) {
  const focusable = Array.from(sheet.value?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(el => !el.hasAttribute("disabled"));
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (!first || !last) {
    return;
  }
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  }
  else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

watch(isMobile, (mobile) => {
  if (!mobile) {
    sheetOpen.value = false;
  }
});

/*
 * Keyboard: arrows (and j/k) move, Home/End jump, Space runs the step's first timer, Escape leaves.
 * Keys meant for a form control or a focused button stay with it.
 */
function onKeydown(event: KeyboardEvent) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) {
    return;
  }
  const target = event.target instanceof Element ? event.target : null;
  if (event.key === "Escape") {
    event.preventDefault();
    if (sheetOpen.value) {
      closeSheet();
    }
    else {
      exit();
    }
    return;
  }
  // Nothing moves behind the open sheet.
  if (sheetOpen.value || target?.closest("input, textarea, select, [contenteditable='true']")) {
    return;
  }
  switch (event.key) {
    case "ArrowRight":
    case "j":
      go(index.value + 1);
      break;
    case "ArrowLeft":
    case "k":
      go(index.value - 1);
      break;
    case "Home":
      go(0);
      break;
    case "End":
      go(total.value - 1);
      break;
    case " ": {
      if (target?.closest("button, a, [role='button']")) {
        return;
      }
      const first = stepTimers(index.value)[0];
      if (first) {
        toggle(first);
      }
      break;
    }
    default:
      return;
  }
  event.preventDefault();
}

useEventListener(window, "keydown", onKeydown);
</script>

<style>
/*
 * Cook mode is always dark, whatever the user's theme: the cook root takes the dark token block.
 * The float shadow is deepened so the timer pill still lifts off ink.
 */
.ds-cook {
  /* The dark palette itself comes from tokens.css (.v-theme--dark, .ds-cook). */
  --ds-shadow-float: 0 8px 24px rgb(0 0 0 / 45%);

  background: var(--ds-bg);
  color: var(--ds-text);
  color-scheme: dark;
}

.cook-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>

<style scoped>
.cook {
  --cook-gutter: calc(var(--ds-space) * 4);

  position: relative;
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  flex-direction: column;
  font-family: var(--ds-font);
}

/* Stays in reach on long steps: a phone has no Escape key. */
.cook__bar {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--ds-bg);
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 2);
  padding: calc(var(--ds-space) * 2) var(--cook-gutter);
}

.cook__title {
  flex: 1;
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cook__progress {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* Room under the content for the floating timers, so they never sit on the last words or the finish. */
.cook__body {
  --cook-timer-room: calc(var(--cook-timer-count, 0) * (var(--ds-space) * 8));

  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: calc(var(--ds-space) * 6);
  padding: calc(var(--ds-space) * 2) var(--cook-gutter) calc(var(--ds-space) * 4 + var(--cook-timer-room));
}

.cook__steps {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
}

/* Holds its place on step 1 so the current step never jumps up. */
.cook__before {
  min-height: calc(var(--ds-t-4) * 2.7 + var(--ds-space) * 2);
}

.cook__strip {
  margin-bottom: calc(var(--ds-space) * -1);
}

.cook__current {
  padding: calc(var(--ds-space) * 2) 0;
}

.cook__empty {
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-5);
}

.cook__finish {
  margin-top: calc(var(--ds-space) * 2);
}

.cook__aside {
  align-self: start;
  position: sticky;
  top: calc(var(--ds-space) * 3);
  max-height: calc(100dvh - var(--ds-space) * 6);
  overflow-y: auto;
  padding: calc(var(--ds-space) * 2.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
}

.cook__controls {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 2) var(--cook-gutter);
  border-top: 1px solid var(--ds-border);
  background: var(--ds-bg);
}

.cook__next {
  margin-left: auto;
}

.cook__timers {
  position: fixed;
  right: var(--cook-gutter);
  bottom: calc(var(--ds-space) * 11);
  z-index: 3;
  display: flex;
  width: min(340px, calc(100vw - var(--cook-gutter) * 2));
  flex-direction: column-reverse;
  gap: var(--ds-space);
}

/* Step change: a short fade and lift, only in answer to the move. */
.cook-step-enter-active,
.cook-step-leave-active {
  transition:
    opacity 180ms ease,
    transform 180ms ease;
}

.cook-step-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.cook-step-leave-to {
  opacity: 0;
}

.cook__sheet-scrim {
  position: fixed;
  inset: 0;
  z-index: 4;
  display: flex;
  align-items: flex-end;
  background: var(--ds-scrim);
}

.cook__sheet {
  position: relative;
  width: 100%;
  max-height: 80dvh;
  overflow-y: auto;
  padding: calc(var(--ds-space) * 3) calc(var(--ds-space) * 2) calc(var(--ds-space) * 4);
  border-top: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-hero) var(--ds-radius-hero) 0 0;
  background: var(--ds-surface);
}

.cook__sheet-close {
  position: absolute;
  top: calc(var(--ds-space) * 1.5);
  right: calc(var(--ds-space) * 1.5);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ds-text);
  cursor: pointer;
}

.cook-sheet-enter-active,
.cook-sheet-leave-active {
  transition: opacity 200ms ease;
}

.cook-sheet-enter-active .cook__sheet,
.cook-sheet-leave-active .cook__sheet {
  transition: transform 200ms ease;
}

.cook-sheet-enter-from,
.cook-sheet-leave-to {
  opacity: 0;
}

.cook-sheet-enter-from .cook__sheet,
.cook-sheet-leave-to .cook__sheet {
  transform: translateY(24px);
}

@media (max-width: 1023px) {
  .cook {
    --cook-gutter: calc(var(--ds-space) * 2);
  }

  .cook__title {
    visibility: hidden;
  }

  .cook__body {
    grid-template-columns: minmax(0, 1fr);
    padding-bottom: calc(var(--ds-space) * 3 + var(--cook-timer-room));
  }

  .cook__before {
    min-height: 0;
  }

  .cook__timers {
    right: var(--cook-gutter);
    left: var(--cook-gutter);
    bottom: calc(var(--ds-space) * 10);
    width: auto;
  }
}

@media (max-width: 599px) {
  /* Icons alone on a phone; the buttons keep their names for assistive tech. */
  .cook__control-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cook-step-enter-active,
  .cook-step-leave-active,
  .cook-sheet-enter-active,
  .cook-sheet-leave-active,
  .cook-sheet-enter-active .cook__sheet,
  .cook-sheet-leave-active .cook__sheet {
    transition: none;
  }
}
</style>
