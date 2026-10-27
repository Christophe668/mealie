<template>
  <section class="cook-finish" :aria-labelledby="headingId">
    <template v-if="loggedIn">
      <h2 :id="headingId" class="cook-finish__title">
        {{ $t("cook.how-was-it") }}
      </h2>
      <div class="cook-finish__effort" role="group" :aria-labelledby="effortId">
        <span :id="effortId" class="cook-finish__effort-label">{{ $t("cook.how-much-work") }}</span>
        <div class="cook-finish__effort-chips">
          <button
            v-for="level in FEEDBACK_EFFORTS"
            :key="level"
            type="button"
            class="cook-finish__chip ds-focus"
            :aria-pressed="effort === level ? 'true' : 'false'"
            :aria-disabled="busy || !chosenVerdict ? 'true' : undefined"
            @click="toggleEffort(level)"
          >
            {{ $t(effortLabelKey(level)) }}
          </button>
        </div>
      </div>
      <div class="cook-finish__verdicts" role="group" :aria-labelledby="headingId">
        <DsButton
          v-for="verdict in FEEDBACK_VERDICTS"
          :key="verdict"
          variant="line"
          size="lg"
          class="cook-finish__verdict"
          :aria-pressed="chosenVerdict === verdict ? 'true' : 'false'"
          :disabled="busy"
          @click="toggleVerdict(verdict)"
        >
          {{ $t(verdictLabelKey(verdict)) }}
        </DsButton>
      </div>
      <CookPantryCheck
        v-if="check && (check.items.length || check.unmatchedIngredients?.length || check.suggestedLeftoverPortions > 0)"
        v-model="choices"
        :items="check.items"
        :proposals="check.proposals ?? []"
        :unmatched="check.unmatchedIngredients ?? []"
        :pantry="pantry"
        :disabled="busy"
      />
      <div class="cook-finish__choices cook-finish__actions">
        <DsButton variant="dark" size="lg" :disabled="busy" @click="save(true)">
          {{ $t("cook.done") }}
        </DsButton>
        <DsButton variant="ghost" size="lg" class="cook-finish__skip" :disabled="busy" @click="save(false)">
          {{ $t("cook.skip") }}
        </DsButton>
      </div>
    </template>
    <template v-else>
      <h2 :id="headingId" class="cook-finish__title">
        {{ $t("cook.last-step") }}
      </h2>
      <div class="cook-finish__choices">
        <DsButton variant="line" size="lg" @click="goBack">
          {{ $t("cook.done") }}
        </DsButton>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import { useId } from "vue";
import CookPantryCheck from "./CookPantryCheck.vue";
import type { PantryChoices } from "./CookPantryCheck.vue";
import DsButton from "~/components/Design/DsButton.vue";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import { apiErrorInfo } from "~/lib/api/error-info";
import type { CookedMealCreate, CookedPantryOutcome, FeedbackVerdict, PantryCheckOut, PantryItemOut } from "~/lib/api/types/household";
import { FEEDBACK_EFFORTS, FEEDBACK_VERDICTS, effortLabelKey, verdictLabelKey } from "~/lib/recipe/recipe-feedback";
import type { FeedbackEffort } from "~/lib/recipe/recipe-feedback";

const props = defineProps<{
  recipeId: string;
  /** The recipe page, where every way out leads. */
  backTo: string;
  /** Cooking is recorded for a household, so visitors get a plain "Done". */
  loggedIn: boolean;
  /** The scale cooked: it sizes the suggested leftovers. */
  scale: number;
  /** The day it was cooked (`YYYY-MM-DD`) when told later; else today. */
  cookedOn?: string;
  /** The meal plan entry it was cooked for, when known; else the server's pick for the day. */
  mealPlanEntryId?: number;
  /** Told later: a cooking already recorded (ticked done, or skipped here) still takes the pantry and verdict. */
  amend?: boolean;
}>();

const headingId = useId();
const effortId = useId();
const router = useRouter();
const i18n = useI18n();

const chosenVerdict = ref<FeedbackVerdict | null>(null);
const effort = ref<FeedbackEffort | null>(null);
const busy = ref(false);
/** An earlier attempt of this screen failed without a verdict from the server, so it may have gone through. */
let retrying = false;

/** Null until the pantry check answers; a failed check just leaves the pantry part out. */
const check = ref<PantryCheckOut | null>(null);
const choices = ref<PantryChoices>({ outcomes: {}, quantities: {}, substitutes: {}, portions: 0, location: "fridge" });
/** The whole pantry, for "Used something else?". */
const pantry = ref<PantryItemOut[]>([]);

// The cook's own day, not the server's: a container on UTC would date a late dinner the day before.
const cookedOn = () => props.cookedOn || format(new Date(), "yyyy-MM-dd");

/** The substitutes the last good check was made with; `latestCheck` makes an older, slower answer lose. */
let checkedSubstitutes: Record<string, string> = {};
let latestCheck = 0;
/** Items already given their proposed choice: a refetch never redoes what the cook has since changed or cleared. */
const seeded = new Set<string>();

/** Pre-selects what the server proposes, for the items not seen before; drops choices for items no longer listed. */
function seed(data: PantryCheckOut) {
  const listed = new Set(data.items.map(item => item.id));
  // An item that left the list gets its proposal again if it comes back.
  for (const id of [...seeded]) {
    if (!listed.has(id)) {
      seeded.delete(id);
    }
  }
  const outcomes = Object.fromEntries(Object.entries(choices.value.outcomes).filter(([id]) => listed.has(id)));
  const quantities = Object.fromEntries(Object.entries(choices.value.quantities).filter(([id]) => listed.has(id)));
  for (const proposal of data.proposals ?? []) {
    if (seeded.has(proposal.pantryItemId) || !listed.has(proposal.pantryItemId)) {
      continue;
    }
    seeded.add(proposal.pantryItemId);
    if (proposal.proposedOutcome === "used_up") {
      outcomes[proposal.pantryItemId] = "used_up";
    }
    else if (proposal.proposedOutcome === "some_left") {
      outcomes[proposal.pantryItemId] = "some_left";
      if (proposal.proposedQuantity !== null && proposal.proposedQuantity !== undefined) {
        quantities[proposal.pantryItemId] = proposal.proposedQuantity;
      }
    }
  }
  choices.value = { ...choices.value, outcomes, quantities };
}

async function loadCheck() {
  const request = ++latestCheck;
  const substitutes = { ...choices.value.substitutes };
  const first = check.value === null;
  try {
    const cooking = useUserApi().householdCooking;
    const { data } = Object.keys(substitutes).length
      ? await cooking.pantryCheck(props.recipeId, cookedOn(), props.scale, substitutes)
      : await cooking.pantryCheck(props.recipeId, cookedOn(), props.scale);
    if (request !== latestCheck) {
      return;
    }
    if (data) {
      check.value = data;
      checkedSubstitutes = substitutes;
      seed(data);
      if (first) {
        choices.value = { ...choices.value, portions: data.suggestedLeftoverPortions };
      }
      return;
    }
  }
  catch {
    // Finishing never depends on the pantry check.
  }
  if (request === latestCheck) {
    // Keep the previous check; the substitute that could not be checked is dropped.
    choices.value = { ...choices.value, substitutes: { ...checkedSubstitutes } };
  }
}

async function loadPantry() {
  try {
    const { data } = await useUserApi().householdPantry.getAll();
    pantry.value = data?.items ?? [];
  }
  catch {
    // Without the pantry there is just no "Used something else?" to pick from.
  }
}

onMounted(async () => {
  if (!props.loggedIn) {
    return;
  }
  await Promise.all([loadCheck(), loadPantry()]);
});

watch(() => JSON.stringify(choices.value.substitutes), (now) => {
  if (props.loggedIn && now !== JSON.stringify(checkedSubstitutes)) {
    loadCheck();
  }
});

/** Single choice, once a verdict is picked; pressing the chosen chip again clears it. */
function toggleEffort(level: FeedbackEffort) {
  // effort is only ever sent with a verdict, so it waits for one
  if (busy.value || !chosenVerdict.value) {
    return;
  }
  effort.value = effort.value === level ? null : level;
}

/** A verdict is only chosen here, Done sends it; pressing it again clears it. */
function toggleVerdict(verdict: FeedbackVerdict) {
  chosenVerdict.value = chosenVerdict.value === verdict ? null : verdict;
}

// Replace, so Back from the recipe does not land in cook mode again.
function goBack() {
  router.replace(props.backTo);
}

/** An amount only when "Some left" differs from what the pantry holds; the substitute's ingredient when it stands in for one. */
function pantryEntry(pantryItemId: string, outcome: CookedPantryOutcome["outcome"]): CookedPantryOutcome {
  const entry: CookedPantryOutcome = { pantryItemId, outcome };
  const quantity = choices.value.quantities[pantryItemId];
  const current = check.value?.items.find(item => item.id === pantryItemId)?.quantity;
  if (outcome === "some_left" && quantity !== undefined && quantity !== current) {
    entry.quantity = quantity;
  }
  const replaces = check.value?.proposals?.find(proposal => proposal.pantryItemId === pantryItemId)?.replacesReferenceId;
  if (replaces) {
    entry.replacesReferenceId = replaces;
  }
  return entry;
}

function cookedMeal(withFeedback: boolean): CookedMealCreate {
  const body: CookedMealCreate = { recipeId: props.recipeId, cookedOn: cookedOn(), scale: props.scale };
  const entryId = props.mealPlanEntryId ?? check.value?.mealPlanEntryId;
  if (entryId) {
    body.mealPlanEntryId = entryId;
  }
  const entries = Object.entries(choices.value.outcomes).map(([pantryItemId, outcome]) => pantryEntry(pantryItemId, outcome));
  if (entries.length) {
    body.pantry = entries;
  }
  if (choices.value.portions > 0) {
    body.leftovers = { portions: choices.value.portions, location: choices.value.location };
  }
  if (withFeedback && chosenVerdict.value) {
    body.feedback = { verdict: chosenVerdict.value };
    if (effort.value !== null) {
      body.feedback.effort = effort.value;
    }
  }
  return body;
}

/**
 * One request records it all: last made, the meal plan entry, the pantry, the leftovers and the verdict.
 * Skip sends the same without the verdict. A failure stays here so it can be retried.
 */
async function save(withFeedback: boolean) {
  if (busy.value) {
    return;
  }
  busy.value = true;
  let saved = false;
  try {
    const cooking = useUserApi().householdCooking;
    const result = props.amend
      ? await cooking.record(cookedMeal(withFeedback), { amend: true })
      : await cooking.record(cookedMeal(withFeedback));
    if (!result.error) {
      saved = true;
    }
    else {
      const { status, message } = apiErrorInfo(result);
      if (status === 409) {
        // Our own earlier attempt got through: that is all we wanted. Otherwise it was recorded before, and
        // nothing of what was chosen here was applied.
        if (!retrying) {
          alert.info(`${message ?? i18n.t("cook.already-recorded")} ${i18n.t("cook.pantry-unchanged")}`);
        }
        saved = true;
      }
    }
  }
  catch {
    saved = false;
  }
  busy.value = false;
  if (!saved) {
    retrying = true;
    alert.error(i18n.t("cook.save-failed"));
    return;
  }
  goBack();
}
</script>

<style scoped>
.cook-finish {
  padding-top: calc(var(--ds-space) * 4);
  border-top: 1px solid var(--ds-border);
}

.cook-finish__title {
  margin: 0 0 calc(var(--ds-space) * 2);
  font-size: var(--ds-t-5);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

/* Skip is the quiet way out: no outline next to Done. */
.cook-finish__choices :deep(.cook-finish__skip) {
  border-color: transparent;
  color: var(--ds-text-2);
}

.cook-finish__effort {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space) calc(var(--ds-space) * 1.5);
  margin-bottom: calc(var(--ds-space) * 2.5);
}

.cook-finish__effort-label {
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
}

.cook-finish__effort-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

/* Toggle chips: hairline when off, ink-filled when chosen. Never saffron: cook mode's accent is the ingredients. */
.cook-finish__chip {
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

.cook-finish__chip[aria-disabled="true"] {
  cursor: default;
  opacity: 0.5;
}

.cook-finish__chip:hover {
  border-color: var(--ds-text-2);
}

.cook-finish__chip[aria-pressed="true"] {
  border-color: var(--ds-text);
  background: var(--ds-text);
  color: var(--ds-bg);
}

.cook-finish__choices,
.cook-finish__verdicts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

/* A chosen verdict is ink-filled, like the chips. */
.cook-finish__verdicts :deep(.cook-finish__verdict[aria-pressed="true"]) {
  border-color: var(--ds-text);
  background: var(--ds-text);
  color: var(--ds-bg);
}

.cook-finish__actions {
  margin-top: calc(var(--ds-space) * 4);
}

@media (max-width: 1023px) {
  .cook-finish__choices,
  .cook-finish__verdicts {
    flex-direction: column;
  }

  .cook-finish__choices :deep(.ds-btn),
  .cook-finish__verdicts :deep(.ds-btn) {
    width: 100%;
  }
}
</style>
