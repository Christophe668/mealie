<template>
  <div class="profile-weekdays" role="group" :aria-label="label">
    <button
      v-for="day in days"
      :key="day.value"
      type="button"
      class="profile-weekdays__day ds-focus"
      :aria-pressed="modelValue.includes(day.value) ? 'true' : 'false'"
      :aria-label="day.long"
      @click="toggle(day.value)"
    >
      {{ day.short }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { weekdayOrder } from "~/lib/household-profile/profile";

const props = defineProps<{
  /** Selected days as the API numbers them: 0 = Monday … 6 = Sunday. */
  modelValue: number[];
  /** The household's first day of the week, as Mealie numbers it: 0 = Sunday … 6 = Saturday. */
  firstDayOfWeek: number;
  label: string;
}>();

const emit = defineEmits<{ (e: "update:modelValue", value: number[]): void }>();

const i18n = useI18n();

// 2024-01-01 was a Monday, so day `n` (0 = Monday) is January n + 1.
const days = computed(() => {
  const short = new Intl.DateTimeFormat(i18n.locale.value, { weekday: "short" });
  const long = new Intl.DateTimeFormat(i18n.locale.value, { weekday: "long" });
  return weekdayOrder(props.firstDayOfWeek).map((value) => {
    const date = new Date(2024, 0, value + 1);
    return { value, short: short.format(date), long: long.format(date) };
  });
});

function toggle(day: number) {
  const next = props.modelValue.includes(day)
    ? props.modelValue.filter(value => value !== day)
    : [...props.modelValue, day];
  emit("update:modelValue", next.sort((a, b) => a - b));
}
</script>

<style scoped>
.profile-weekdays {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: calc(var(--ds-space) * 0.5);
  max-width: 480px;
}

.profile-weekdays__day {
  min-height: 44px;
  padding: 0;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-1);
  font-weight: 600;
  cursor: pointer;
  transition:
    background-color 120ms ease,
    color 120ms ease;
}

.profile-weekdays__day[aria-pressed="true"] {
  border-color: var(--ds-text);
  background: var(--ds-text);
  color: var(--ds-bg);
}

@media (prefers-reduced-motion: reduce) {
  .profile-weekdays__day {
    transition: none;
  }
}
</style>
