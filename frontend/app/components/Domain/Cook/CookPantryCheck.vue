<template>
  <div class="cook-pantry">
    <section v-if="items.length" class="cook-pantry__section" :aria-labelledby="pantryId">
      <h3 :id="pantryId" class="cook-pantry__heading">
        {{ $t("cook.from-your-pantry") }}
      </h3>
      <ul class="cook-pantry__list">
        <li v-for="item in items" :key="item.id" class="cook-pantry__item">
          <span class="cook-pantry__name">
            {{ item.name }}
            <span v-if="amount(item)" class="cook-pantry__amount">{{ amount(item) }}</span>
          </span>
          <span class="cook-pantry__chips" role="group" :aria-label="$t('cook.pantry-outcome-label', { name: item.name })">
            <button
              v-for="outcome in OUTCOMES"
              :key="outcome"
              type="button"
              class="cook-pantry__chip ds-focus"
              :aria-pressed="model.outcomes[item.id] === outcome ? 'true' : 'false'"
              :aria-disabled="disabled ? 'true' : undefined"
              @click="toggleOutcome(item.id, outcome)"
            >
              {{ $t(OUTCOME_LABELS[outcome]) }}
            </button>
          </span>
        </li>
      </ul>
    </section>

    <section class="cook-pantry__section" :aria-labelledby="leftoversId">
      <h3 :id="leftoversId" class="cook-pantry__heading">
        {{ $t("cook.leftovers") }}
      </h3>
      <div class="cook-pantry__leftovers">
        <div class="cook-pantry__stepper" role="group" :aria-labelledby="leftoversId">
          <button
            type="button"
            class="cook-pantry__step ds-focus"
            :aria-label="$t('cook.fewer-portions')"
            :aria-disabled="disabled || model.portions <= 0 ? 'true' : undefined"
            @click="stepPortions(-1)"
          >
            <DsIcon name="minus" :size="18" />
          </button>
          <output class="cook-pantry__portions" aria-live="polite">
            {{ $t("cook.leftover-portions", { count: model.portions }, model.portions) }}
          </output>
          <button
            type="button"
            class="cook-pantry__step ds-focus"
            :aria-label="$t('cook.more-portions')"
            :aria-disabled="disabled || model.portions >= MAX_PORTIONS ? 'true' : undefined"
            @click="stepPortions(1)"
          >
            <DsIcon name="createAlt" :size="18" />
          </button>
        </div>
        <span class="cook-pantry__chips cook-pantry__location" role="group" :aria-label="$t('cook.leftovers-go')">
          <button
            v-for="location in LOCATIONS"
            :key="location"
            type="button"
            class="cook-pantry__chip ds-focus"
            :aria-pressed="model.location === location ? 'true' : 'false'"
            :aria-disabled="disabled ? 'true' : undefined"
            @click="setLocation(location)"
          >
            {{ $t(`pantry.location.${location}`) }}
          </button>
        </span>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useId } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { PantryItemOut, PantryOutcome } from "~/lib/api/types/household";

export type LeftoverLocation = "fridge" | "freezer";

/** What the cook chose: an outcome only for the items they tapped, never one by default. */
export interface PantryChoices {
  outcomes: Record<string, PantryOutcome>;
  portions: number;
  location: LeftoverLocation;
}

const props = withDefaults(defineProps<{
  items: PantryItemOut[];
  disabled?: boolean;
}>(), {
  disabled: false,
});

const model = defineModel<PantryChoices>({ required: true });

const OUTCOMES: readonly PantryOutcome[] = ["used_up", "some_left"];
const OUTCOME_LABELS: Record<PantryOutcome, string> = { used_up: "cook.used-up", some_left: "cook.some-left" };
const LOCATIONS: readonly LeftoverLocation[] = ["fridge", "freezer"];
const MAX_PORTIONS = 50;

const pantryId = useId();
const leftoversId = useId();
const i18n = useI18n();

/** "250 grams", "3": the unit only when there is an amount to go with it. */
function amount(item: PantryItemOut) {
  if (!item.quantity) {
    return "";
  }
  const value = new Intl.NumberFormat(i18n.locale.value, { maximumFractionDigits: 2 }).format(item.quantity);
  const unit = item.unit;
  const unitName = unit ? (item.quantity !== 1 && unit.pluralName ? unit.pluralName : unit.name) : "";
  return [value, unitName].filter(Boolean).join(" ");
}

/** One tap chooses, a tap on the chosen one clears it. */
function toggleOutcome(itemId: string, outcome: PantryOutcome) {
  if (props.disabled) {
    return;
  }
  const { [itemId]: current, ...others } = model.value.outcomes;
  const outcomes = current === outcome ? others : { ...others, [itemId]: outcome };
  model.value = { ...model.value, outcomes };
}

function stepPortions(step: number) {
  if (props.disabled) {
    return;
  }
  const portions = Math.min(Math.max(model.value.portions + step, 0), MAX_PORTIONS);
  if (portions !== model.value.portions) {
    model.value = { ...model.value, portions };
  }
}

function setLocation(location: LeftoverLocation) {
  if (!props.disabled) {
    model.value = { ...model.value, location };
  }
}
</script>

<style scoped>
.cook-pantry {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
  margin-top: calc(var(--ds-space) * 3);
}

.cook-pantry__heading {
  margin: 0 0 calc(var(--ds-space) * 1.5);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 600;
}

.cook-pantry__list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.cook-pantry__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space) calc(var(--ds-space) * 2);
  padding: calc(var(--ds-space) * 1.25) 0;
  border-top: 1px solid var(--ds-border);
}

.cook-pantry__item:last-child {
  border-bottom: 1px solid var(--ds-border);
}

.cook-pantry__name {
  display: flex;
  flex-direction: column;
  min-width: 0;
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.cook-pantry__amount {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.cook-pantry__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

/* Same toggle chips as the effort question: hairline when off, ink-filled when chosen. */
.cook-pantry__chip {
  min-height: 44px;
  padding: 0 calc(var(--ds-space) * 2);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: transparent;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 500;
  cursor: pointer;
}

.cook-pantry__chip:hover {
  border-color: var(--ds-text-2);
}

.cook-pantry__chip[aria-pressed="true"] {
  border-color: var(--ds-text);
  background: var(--ds-text);
  color: var(--ds-bg);
}

.cook-pantry__chip[aria-disabled="true"] {
  cursor: default;
  opacity: 0.5;
}

.cook-pantry__leftovers {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space) calc(var(--ds-space) * 2);
}

.cook-pantry__stepper {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
}

.cook-pantry__step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  cursor: pointer;
}

.cook-pantry__step[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: 0.35;
}

.cook-pantry__portions {
  min-width: 12ch;
  font-size: var(--ds-t-2);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: center;
}
</style>
