<template>
  <div class="ds-places" role="radiogroup" :aria-label="$t('pantry.where')">
    <button
      v-for="place in PANTRY_LOCATIONS"
      :key="place"
      type="button"
      role="radio"
      class="ds-places__chip ds-focus"
      :class="{ 'ds-places__chip--on': place === model }"
      :aria-checked="place === model"
      :tabindex="place === model ? 0 : -1"
      @click="model = place"
      @keydown="onKey($event, place)"
    >
      {{ $t(`pantry.location.${place}`) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { PANTRY_LOCATIONS } from "~/lib/pantry/freshness";

const model = defineModel<string>({ required: true });

/** Arrow keys move the selection (and focus) to the next or previous place, wrapping at the ends. */
async function onKey(event: KeyboardEvent, place: string) {
  const step = event.key === "ArrowRight" || event.key === "ArrowDown"
    ? 1
    : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
  if (!step) {
    return;
  }
  event.preventDefault();
  const count = PANTRY_LOCATIONS.length;
  const next = PANTRY_LOCATIONS[(PANTRY_LOCATIONS.indexOf(place as never) + step + count) % count]!;
  model.value = next;
  const group = (event.currentTarget as HTMLElement).parentElement;
  await nextTick();
  group?.querySelector<HTMLElement>("[aria-checked=true]")?.focus();
}
</script>

<style scoped>
.ds-places {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

.ds-places__chip {
  min-height: 40px;
  padding: 0 calc(var(--ds-space) * 2);
  border: 1px solid var(--ds-border);
  border-radius: 999px;
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 600;
  cursor: pointer;
}

.ds-places__chip--on {
  background: var(--ds-text);
  border-color: var(--ds-text);
  color: var(--ds-bg);
}
</style>
