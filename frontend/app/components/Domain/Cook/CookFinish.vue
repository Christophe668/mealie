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
            :aria-disabled="busy ? 'true' : undefined"
            @click="toggleEffort(level)"
          >
            {{ $t(effortLabelKey(level)) }}
          </button>
        </div>
      </div>
      <div class="cook-finish__choices">
        <DsButton
          v-for="verdict in FEEDBACK_VERDICTS"
          :key="verdict"
          variant="line"
          size="lg"
          :disabled="busy"
          @click="record(verdict)"
        >
          {{ $t(verdictLabelKey(verdict)) }}
        </DsButton>
        <DsButton variant="ghost" size="lg" class="cook-finish__skip" :disabled="busy" @click="skip">
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
import { useId } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { FeedbackVerdict, RecipeFeedbackCreate } from "~/lib/api/types/household";
import { FEEDBACK_EFFORTS, FEEDBACK_VERDICTS, effortLabelKey, verdictLabelKey } from "~/lib/recipe/recipe-feedback";
import type { FeedbackEffort } from "~/lib/recipe/recipe-feedback";

const props = defineProps<{
  recipeId: string;
  recipeSlug: string;
  /** The recipe page, where every way out leads. */
  backTo: string;
  /** Feedback and last made belong to a household, so visitors get a plain "Done". */
  loggedIn: boolean;
}>();

const headingId = useId();
const effortId = useId();
const router = useRouter();
const i18n = useI18n();

const effort = ref<FeedbackEffort | null>(null);
const busy = ref(false);

/** Single choice; pressing the chosen chip again clears it. */
function toggleEffort(level: FeedbackEffort) {
  if (busy.value) {
    return;
  }
  effort.value = effort.value === level ? null : level;
}

// Replace, so Back from the recipe does not land in cook mode again.
function goBack() {
  router.replace(props.backTo);
}

/** Records the verdict (the server also sets last made); stays here so it can be retried when it fails. */
async function record(verdict: FeedbackVerdict) {
  if (busy.value) {
    return;
  }
  busy.value = true;
  const payload: RecipeFeedbackCreate = { recipeId: props.recipeId, verdict };
  if (effort.value !== null) {
    payload.effort = effort.value;
  }
  let saved = false;
  try {
    const { error } = await useUserApi().recipeFeedback.create(payload);
    saved = !error;
  }
  catch {
    saved = false;
  }
  busy.value = false;
  if (!saved) {
    alert.error(i18n.t("cook.save-failed"));
    return;
  }
  goBack();
}

/** No verdict: only last made is recorded, and the way out never blocks on it. */
async function skip() {
  if (busy.value) {
    return;
  }
  busy.value = true;
  try {
    const { error } = await useUserApi().recipes.updateLastMade(props.recipeSlug, new Date().toISOString());
    if (error) {
      alert.error(i18n.t("cook.save-failed"));
    }
  }
  catch {
    alert.error(i18n.t("cook.save-failed"));
  }
  busy.value = false;
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

/* Skip is the quiet way out: no outline next to the three answers. */
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

.cook-finish__choices {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

@media (max-width: 1023px) {
  .cook-finish__choices {
    flex-direction: column;
  }

  .cook-finish__choices :deep(.ds-btn) {
    width: 100%;
  }
}
</style>
