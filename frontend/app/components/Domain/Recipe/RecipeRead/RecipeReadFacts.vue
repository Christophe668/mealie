<template>
  <!-- With no facts, only the desktop button is left; mobile has its own sticky one. -->
  <div class="read-facts" :class="{ 'ds-desktop-only': !hasFacts }">
    <ul v-if="hasFacts" class="read-facts__list" role="list">
      <li v-for="line in lines" :key="line.key" class="read-facts__line">
        {{ line.text }}
      </li>
      <li v-if="servingsBase" class="read-facts__line read-facts__servings">
        <i18n-t keypath="recipe-read.serves" :plural="servings.scaledAmount" tag="span" class="read-facts__serves" scope="global">
          <template #servings>
            <!-- Fraction markup from useScaledAmount, built from numbers only. -->
            <!-- eslint-disable-next-line vue/no-v-html -->
            <span v-html="servings.scaledAmountDisplay" />
          </template>
        </i18n-t>
        <span v-if="canScale" class="read-facts__stepper">
          <button
            type="button"
            class="read-facts__step ds-focus"
            :aria-label="$t('recipe-read.fewer-servings')"
            :title="$t('recipe-read.fewer-servings')"
            :aria-disabled="servings.scaledAmount <= 1 ? 'true' : undefined"
            @click="servings.scaledAmount > 1 && setServings(servings.scaledAmount - 1)"
          >
            <DsIcon name="minus" :size="18" />
          </button>
          <button
            type="button"
            class="read-facts__step ds-focus"
            :aria-label="$t('recipe-read.more-servings')"
            :title="$t('recipe-read.more-servings')"
            @click="setServings(servings.scaledAmount + 1)"
          >
            <DsIcon name="createAlt" :size="18" />
          </button>
        </span>
      </li>
    </ul>

    <DsButton
      v-if="cookTo"
      class="read-facts__cook ds-desktop-only"
      size="lg"
      block
      :to="cookTo"
    >
      {{ $t("recipe-read.start-cooking") }}
    </DsButton>
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { calculateScaleFromYield, useScaledAmount } from "~/composables/recipes/use-scaled-amount";
import type { Recipe } from "~/lib/api/types/recipe";

const props = withDefaults(defineProps<{
  recipe: Recipe;
  /** Link for the desktop "Start cooking" button (the screen's one accent); empty hides it. */
  cookTo?: string;
}>(), {
  cookTo: "",
});

const scale = defineModel<number>("scale", { default: 1 });

const i18n = useI18n();

function duration(seconds: number | null | undefined, written: string | null | undefined): string {
  if (!seconds || seconds <= 0) {
    return written?.trim() || "";
  }
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  const h = hours ? i18n.t("recipe-read.hours", { n: hours }, hours) : "";
  const m = minutes ? i18n.t("recipe-read.minutes", { n: minutes }, minutes) : "";
  return h && m ? i18n.t("recipe-read.duration", { hours: h, minutes: m }) : h || m;
}

const lines = computed(() => {
  const r = props.recipe;
  const facts = [
    { key: "prep", time: duration(r.prepTimeSeconds, r.prepTime) },
    { key: "cook", time: duration(r.performTimeSeconds, r.performTime || r.cookTime) },
    { key: "total", time: duration(r.totalTimeSeconds, r.totalTime) },
  ];
  const result = facts
    .filter(f => f.time)
    .map(f => ({ key: f.key, text: i18n.t(`recipe-read.${f.key}`, { time: f.time }) }));
  // A yield without servings ("12 cookies") is still worth saying.
  if (!servingsBase.value && r.recipeYield?.trim()) {
    const qty = r.recipeYieldQuantity ? `${r.recipeYieldQuantity} ` : "";
    result.push({ key: "yield", text: `${qty}${r.recipeYield.trim()}` });
  }
  return result;
});

const servingsBase = computed(() => props.recipe.recipeServings || 0);
const servings = computed(() => useScaledAmount(servingsBase.value, scale.value));
// Scaling only changes parsed quantities, so the stepper needs at least one parsed food or unit.
const canScale = computed(() => (props.recipe.recipeIngredient ?? []).some(i => i.food || i.unit));

function setServings(value: number) {
  const next = calculateScaleFromYield(value, servingsBase.value);
  if (next !== null) {
    scale.value = next;
  }
}

const hasFacts = computed(() => !!(lines.value.length || servingsBase.value));
</script>

<style scoped>
.read-facts__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.read-facts__line {
  font-size: var(--ds-t-3);
  font-weight: 500;
  line-height: 1.5;
}

.read-facts__servings {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  margin-top: calc(var(--ds-space) * 0.5);
}

.read-facts__stepper {
  display: inline-flex;
  gap: calc(var(--ds-space) * 0.5);
}

.read-facts__step {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 4.5);
  height: calc(var(--ds-space) * 4.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}

.read-facts__step:hover:not([aria-disabled="true"]) {
  border-color: var(--ds-text-2);
}

.read-facts__step[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: 0.45;
}

.read-facts__serves :deep(sup),
.read-facts__serves :deep(sub) {
  font-size: 0.7em;
}

.read-facts__list + .read-facts__cook {
  margin-top: calc(var(--ds-space) * 2.5);
}
</style>
