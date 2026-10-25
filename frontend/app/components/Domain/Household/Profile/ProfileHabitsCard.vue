<template>
  <DsCard class="profile-habits">
    <form class="profile-habits__form" :aria-label="$t('household-profile.how-we-cook')" @submit.prevent="save">
      <div class="profile-habits__field">
        <span :id="`${uid}-servings`" class="profile-habits__label">{{ $t("household-profile.default-servings") }}</span>
        <div class="profile-habits__stepper" role="group" :aria-labelledby="`${uid}-servings`">
          <button
            type="button"
            class="profile-habits__step ds-focus"
            :aria-label="$t('household-profile.fewer-servings')"
            :aria-disabled="draft.defaultServings === null ? 'true' : undefined"
            @click="stepServings(-1)"
          >
            <DsIcon name="minus" :size="18" />
          </button>
          <output class="profile-habits__servings" aria-live="polite">
            {{ draft.defaultServings ?? $t("household-profile.not-set") }}
          </output>
          <button
            type="button"
            class="profile-habits__step ds-focus"
            :aria-label="$t('household-profile.more-servings')"
            :aria-disabled="(draft.defaultServings ?? 0) >= MAX_SERVINGS ? 'true' : undefined"
            @click="stepServings(1)"
          >
            <DsIcon name="createAlt" :size="18" />
          </button>
        </div>
      </div>

      <div class="profile-habits__field">
        <span class="profile-habits__label">{{ $t("household-profile.quick-weekdays") }}</span>
        <ProfileWeekdayToggles
          v-model="draft.quickWeekdays"
          :first-day-of-week="firstDayOfWeek"
          :label="$t('household-profile.quick-weekdays')"
        />
      </div>

      <div class="profile-habits__row">
        <label v-for="(labelKey, field) in TIME_FIELDS" :key="field" class="profile-habits__field">
          <span class="profile-habits__label">{{ $t(labelKey) }}</span>
          <select v-model="draft[field]" class="profile-habits__input">
            <option :value="null">{{ $t("household-profile.no-limit") }}</option>
            <option v-for="minutes in minuteChoices(draft[field])" :key="minutes" :value="minutes">
              {{ $t("household-profile.minutes", { count: minutes }) }}
            </option>
          </select>
        </label>
      </div>

      <ProfileChipInput v-model="draft.favouriteCuisines" :label="$t('household-profile.favourite-cuisines')" />

      <label class="profile-habits__field">
        <span class="profile-habits__label">{{ $t("household-profile.notes") }}</span>
        <textarea
          v-model="draft.notes"
          rows="2"
          class="profile-habits__input profile-habits__textarea"
          :maxlength="MAX_NOTES_LENGTH"
        />
      </label>

      <div class="profile-habits__actions">
        <DsButton variant="dark" type="submit" :disabled="!canSave" :aria-label="$t('household-profile.save-habits')">
          {{ $t("household-profile.save") }}
        </DsButton>
      </div>
    </form>
  </DsCard>
</template>

<script setup lang="ts">
import { useId } from "vue";
import ProfileChipInput from "./ProfileChipInput.vue";
import ProfileWeekdayToggles from "./ProfileWeekdayToggles.vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useTrackedDraft } from "~/composables/use-tracked-draft";
import type { MealPreferencesOut, MealPreferencesUpdate } from "~/lib/api/types/household";
import { habitsDraft, habitsPayload, MAX_MINUTES_CHOICES, MAX_NOTES_LENGTH } from "~/lib/household-profile/profile";

const MAX_SERVINGS = 20;
const TIME_FIELDS = {
  weeknightMaxMinutes: "household-profile.weeknight-max-minutes",
  weekendMaxMinutes: "household-profile.weekend-max-minutes",
} as const;

const props = defineProps<{
  preferences: MealPreferencesOut | null;
  /** 0 = Sunday … 6 = Saturday, as Mealie stores it. */
  firstDayOfWeek: number;
  /** Saves only the fields edited here; resolves true on success. It reports its own failure. */
  savePreferences: (changes: MealPreferencesUpdate) => Promise<boolean>;
}>();

const uid = useId();

// A reload or Claude's edits flow into the fields not edited here; edited fields keep what was typed.
const { draft, changes, commit } = useTrackedDraft(() => habitsDraft(props.preferences), habitsPayload);

const saving = ref(false);
const canSave = computed(() => Object.keys(changes.value).length > 0 && !saving.value);

/** The fixed choices, plus a value set elsewhere (by Claude, say) so the select never drops it. */
function minuteChoices(current: number | null) {
  return current === null || MAX_MINUTES_CHOICES.includes(current)
    ? MAX_MINUTES_CHOICES
    : [...MAX_MINUTES_CHOICES, current].sort((a, b) => a - b);
}

/**
 * Below 1 is "Not set"; from "Not set", + starts at 1. The buttons use aria-disabled, so the focused one
 * stays focused when it reaches the end; a press there does nothing.
 */
function stepServings(step: number) {
  const current = draft.value.defaultServings;
  if ((step < 0 && current === null) || (step > 0 && (current ?? 0) >= MAX_SERVINGS)) {
    return;
  }
  const next = (current ?? 0) + step;
  draft.value.defaultServings = next < 1 ? null : Math.min(next, MAX_SERVINGS);
}

async function save() {
  if (!canSave.value) {
    return;
  }
  saving.value = true;
  try {
    const sent = { ...changes.value };
    if (await props.savePreferences(sent)) {
      await nextTick();
      commit(sent);
    }
  }
  finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.profile-habits__form {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2.5);
}

.profile-habits__field {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.75);
  min-width: 0;
}

.profile-habits__label {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}

.profile-habits__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: calc(var(--ds-space) * 2);
}

.profile-habits__stepper {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
}

.profile-habits__step {
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

.profile-habits__step[aria-disabled="true"] {
  cursor: not-allowed;
  opacity: 0.35;
}

.profile-habits__servings {
  min-width: 9ch;
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  text-align: center;
}

.profile-habits__input {
  width: 100%;
  min-height: 44px;
  padding: var(--ds-space) calc(var(--ds-space) * 1.25);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
  color: var(--ds-text);
  color-scheme: light;
  font: inherit;
  font-size: var(--ds-t-2);
  appearance: auto;
}

.profile-habits__input:focus-visible {
  border-color: var(--ds-text);
  outline: 2px solid var(--ds-text);
  outline-offset: 1px;
}

:global(.v-theme--dark) .profile-habits__input {
  color-scheme: dark;
}

.profile-habits__textarea {
  resize: vertical;
}

.profile-habits__actions {
  display: flex;
  justify-content: flex-end;
}

@media (max-width: 599px) {
  .profile-habits__row {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
