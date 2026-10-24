<template>
  <section class="pantry-group" :aria-labelledby="headingId">
    <h2 :id="headingId" class="pantry-group__heading">
      <span class="pantry-group__name">{{ $t(`pantry.location.${location}`) }}</span>
      <span class="pantry-group__count" aria-hidden="true">{{ items.length }}</span>
      <span class="pantry-group__sr">{{ $t("pantry.item-count", { count: items.length }, items.length) }}</span>
    </h2>
    <ul class="pantry-group__items" role="list">
      <PantryItemRow
        v-for="item in items"
        :key="item.id"
        :item="item"
        :today="today"
        @edit="$emit('edit', $event)"
        @opened="$emit('opened', $event)"
        @remove="$emit('remove', $event)"
      />
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import PantryItemRow from "./PantryItemRow.vue";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";

defineProps<{
  location: PantryLocation;
  items: PantryItemOut[];
  today: Date;
}>();

defineEmits<{
  (e: "edit" | "opened" | "remove", item: PantryItemOut): void;
}>();

const headingId = useId();
</script>

<style scoped>
.pantry-group {
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.5);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.pantry-group__heading {
  display: flex;
  align-items: baseline;
  gap: var(--ds-space);
  margin: 0;
  padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 0.5);
  font-size: var(--ds-t-3);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.pantry-group__count {
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.pantry-group__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.pantry-group__items {
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
