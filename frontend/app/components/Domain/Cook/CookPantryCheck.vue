<template>
  <div ref="root" class="cook-pantry">
    <section v-if="items.length" class="cook-pantry__section" :aria-labelledby="pantryId">
      <h3 :id="pantryId" class="cook-pantry__heading">
        {{ $t("cook.from-your-pantry") }}
      </h3>
      <ul class="cook-pantry__list">
        <li v-for="item in items" :key="item.id" class="cook-pantry__item">
          <span class="cook-pantry__name">
            {{ item.name }}
            <span v-if="replacedFood(item.id)" class="cook-pantry__hint">
              {{ $t("cook.used-instead", { food: replacedFood(item.id) }) }}
              <button
                type="button"
                class="cook-pantry__undo ds-focus"
                :aria-label="$t('general.undo')"
                :aria-disabled="disabled ? 'true' : undefined"
                @click="undoSubstitute(item.id)"
              >
                ×
              </button>
            </span>
            <span v-if="editingId === item.id" class="cook-pantry__amount">
              <input
                class="cook-pantry__input ds-focus"
                type="number"
                step="any"
                min="0"
                inputmode="decimal"
                :data-amount-input="item.id"
                :aria-label="$t('cook.amount-left')"
                :value="model.quantities[item.id]"
                @input="setQuantity(item.id, ($event.target as HTMLInputElement).value)"
                @blur="stopEditing(item.id, false)"
                @keydown.enter.prevent="stopEditing(item.id, true)"
              >
              {{ unitName(item, model.quantities[item.id]) }}
            </span>
            <button
              v-else-if="model.outcomes[item.id] === 'some_left' && amount(item)"
              type="button"
              class="cook-pantry__amount cook-pantry__amount-edit ds-focus"
              :data-amount-edit="item.id"
              :aria-disabled="disabled ? 'true' : undefined"
              @click="startEditing(item.id)"
            >
              {{ amount(item) }}
            </button>
            <span v-else-if="amount(item)" class="cook-pantry__amount">{{ amount(item) }}</span>
            <span v-if="proposalOf(item.id)?.reason === 'units_differ'" class="cook-pantry__hint">
              {{ $t("cook.units-dont-compare") }}
            </span>
          </span>
          <span class="cook-pantry__chips" role="group" :aria-label="$t('cook.pantry-outcome-label', { name: item.name })">
            <button
              v-for="outcome in OUTCOMES"
              :key="outcome"
              type="button"
              class="cook-pantry__chip ds-focus"
              :aria-pressed="model.outcomes[item.id] === outcome ? 'true' : 'false'"
              :aria-disabled="disabled ? 'true' : undefined"
              @click="toggleOutcome(item, outcome)"
            >
              {{ $t(OUTCOME_LABELS[outcome]) }}
            </button>
          </span>
        </li>
      </ul>
    </section>

    <section v-if="unmatched.length" class="cook-pantry__section">
      <ul class="cook-pantry__list">
        <li v-for="line in unmatched" :key="line.referenceId" class="cook-pantry__item cook-pantry__unmatched">
          <span class="cook-pantry__name">
            {{ $t("cook.not-in-pantry", { food: line.food.name }) }}
          </span>
          <button
            type="button"
            class="cook-pantry__chip ds-focus"
            :aria-expanded="pickerFor === line.referenceId ? 'true' : 'false'"
            :aria-disabled="disabled ? 'true' : undefined"
            @click="togglePicker(line.referenceId)"
          >
            {{ $t("cook.used-something-else") }}
          </button>
          <ul v-if="pickerFor === line.referenceId" class="cook-pantry__picker">
            <li v-for="candidate in candidates(line)" :key="candidate.id">
              <button
                type="button"
                class="cook-pantry__chip ds-focus"
                :aria-disabled="disabled ? 'true' : undefined"
                @click="pickSubstitute(line.referenceId, candidate.id)"
              >
                {{ candidate.name }}
              </button>
            </li>
          </ul>
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
import type { PantryItemOut, PantryOutcome, PantryProposal, UnmatchedIngredient } from "~/lib/api/types/household";

export type LeftoverLocation = "fridge" | "freezer";

/** What the cook chose: an outcome only for the items they tapped, never one by default. */
export interface PantryChoices {
  outcomes: Record<string, PantryOutcome>;
  /** The amount left, for the items with "Some left". */
  quantities: Record<string, number>;
  /** Unmatched ingredient reference -> the pantry item used instead. */
  substitutes: Record<string, string>;
  portions: number;
  location: LeftoverLocation;
}

const props = withDefaults(defineProps<{
  items: PantryItemOut[];
  proposals?: PantryProposal[];
  unmatched?: UnmatchedIngredient[];
  /** The whole pantry, for "Used something else?". */
  pantry?: PantryItemOut[];
  disabled?: boolean;
}>(), {
  proposals: () => [],
  unmatched: () => [],
  pantry: () => [],
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

const root = ref<HTMLElement | null>(null);
const editingId = ref<string | null>(null);
const pickerFor = ref<string | null>(null);

const proposalById = computed(() => new Map(props.proposals.map(p => [p.pantryItemId, p])));
const proposalOf = (itemId: string) => proposalById.value.get(itemId);

// A substituted ingredient leaves the unmatched list, so its food name is remembered for "instead of".
const foodNames = ref<Record<string, string>>({});
watch(() => props.unmatched, (lines) => {
  for (const line of lines) {
    foodNames.value[line.referenceId] = line.food.name;
  }
}, { immediate: true });

function replacedFood(itemId: string) {
  const reference = proposalOf(itemId)?.replacesReferenceId;
  return reference ? foodNames.value[reference] ?? "" : "";
}

function unitName(item: PantryItemOut, quantity: number | null | undefined) {
  const unit = item.unit;
  return unit ? (quantity !== 1 && unit.pluralName ? unit.pluralName : unit.name) : "";
}

function format(item: PantryItemOut, quantity: number) {
  const value = new Intl.NumberFormat(i18n.locale.value, { maximumFractionDigits: 2 }).format(quantity);
  return [value, unitName(item, quantity)].filter(Boolean).join(" ");
}

/** The amount left once cooked: the cook's own figure, else the proposal's; none after "Used up". */
function target(item: PantryItemOut) {
  // Nothing chosen (or cleared) means nothing will change, so there is no new amount to show.
  if (model.value.outcomes[item.id] !== "some_left") {
    return null;
  }
  const proposal = proposalOf(item.id);
  const proposed = proposal?.proposedOutcome === "some_left" ? proposal.proposedQuantity : null;
  return model.value.quantities[item.id] ?? proposed ?? null;
}

/** "250 grams", "3": the unit only when there is an amount to go with it; "1000 g → 800 g" once a new amount is known. */
function amount(item: PantryItemOut) {
  if (!item.quantity) {
    return "";
  }
  const current = format(item, item.quantity);
  const next = target(item);
  return next === null || next === item.quantity ? current : `${current} → ${format(item, next)}`;
}

/** One tap chooses, a tap on the chosen one clears it. */
function toggleOutcome(item: PantryItemOut, outcome: PantryOutcome) {
  if (props.disabled) {
    return;
  }
  const { [item.id]: current, ...others } = model.value.outcomes;
  const { [item.id]: quantity, ...otherQuantities } = model.value.quantities;
  const outcomes = current === outcome ? others : { ...others, [item.id]: outcome };
  let quantities = otherQuantities;
  if (outcomes[item.id] === "some_left") {
    const proposal = proposalOf(item.id);
    const start = quantity ?? (proposal?.proposedOutcome === "some_left" ? proposal.proposedQuantity : null) ?? item.quantity;
    if (start !== null && start !== undefined) {
      quantities = { ...otherQuantities, [item.id]: start };
    }
  }
  if (outcomes[item.id] !== "some_left" && editingId.value === item.id) {
    editingId.value = null;
  }
  model.value = { ...model.value, outcomes, quantities };
}

function focusAmount(attribute: string, itemId: string) {
  root.value?.querySelector<HTMLElement>(`[${attribute}="${itemId}"]`)?.focus();
}

async function startEditing(itemId: string) {
  if (props.disabled) {
    return;
  }
  editingId.value = itemId;
  await nextTick();
  focusAmount("data-amount-input", itemId);
}

/** Enter hands focus back to the amount; a blur leaves it where the cook went. */
async function stopEditing(itemId: string, refocus: boolean) {
  if (editingId.value !== itemId) {
    return;
  }
  editingId.value = null;
  if (refocus) {
    await nextTick();
    focusAmount("data-amount-edit", itemId);
  }
}

function setQuantity(itemId: string, raw: string) {
  const quantity = Number(raw);
  if (props.disabled || raw === "" || !Number.isFinite(quantity) || quantity < 0) {
    return;
  }
  model.value = { ...model.value, quantities: { ...model.value.quantities, [itemId]: quantity } };
}

/** The pantry items to pick from: the ones the recipe's food lists as substitutes first, then by name. */
function candidates(line: UnmatchedIngredient) {
  const listed = new Set(props.items.map(item => item.id));
  const picked = new Set(Object.values(model.value.substitutes));
  const preferred = new Set(line.substituteFoodIds ?? []);
  const rank = (item: PantryItemOut) => (item.foodId && preferred.has(item.foodId) ? 0 : 1);
  return props.pantry
    .filter(item => !listed.has(item.id) && !picked.has(item.id))
    .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

function togglePicker(reference: string) {
  if (!props.disabled) {
    pickerFor.value = pickerFor.value === reference ? null : reference;
  }
}

function pickSubstitute(reference: string, itemId: string) {
  if (props.disabled) {
    return;
  }
  pickerFor.value = null;
  model.value = { ...model.value, substitutes: { ...model.value.substitutes, [reference]: itemId } };
}

function undoSubstitute(itemId: string) {
  const reference = proposalOf(itemId)?.replacesReferenceId;
  if (props.disabled || !reference) {
    return;
  }
  const { [reference]: removed, ...substitutes } = model.value.substitutes;
  model.value = { ...model.value, substitutes };
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

.cook-pantry__amount-edit {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  font-family: inherit;
  text-decoration: underline dotted;
  cursor: pointer;
}

.cook-pantry__input {
  width: 8ch;
  min-height: 36px;
  padding: 0 var(--ds-space);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
}

.cook-pantry__hint {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 400;
}

.cook-pantry__undo {
  min-width: 44px;
  min-height: 44px;
  border: 0;
  background: none;
  color: var(--ds-text-2);
  font: inherit;
  cursor: pointer;
}

.cook-pantry__picker {
  display: flex;
  flex-basis: 100%;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin: 0;
  padding: 0;
  list-style: none;
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
