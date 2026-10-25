<template>
  <section class="pantry-group" :aria-labelledby="headingId">
    <h2 :id="headingId" class="pantry-group__heading">
      <span class="pantry-group__name">{{ $t(`pantry.location.${location}`) }}</span>
      <span class="pantry-group__count" aria-hidden="true">{{ items.length }}</span>
      <span class="pantry-group__sr">{{ $t("pantry.item-count", { count: items.length }, items.length) }}</span>
    </h2>
    <!-- Drag an item onto another place to move it there; the order inside a place stays "use first". -->
    <VueDraggable
      v-model="list"
      tag="ul"
      class="pantry-group__items"
      role="list"
      :data-location="location"
      group="pantry"
      draggable=".pantry-row"
      :sort="false"
      :animation="reduceMotion ? 0 : 150"
      force-fallback
      :fallback-tolerance="4"
      filter=".pantry-row__more"
      :prevent-on-filter="false"
      ghost-class="pantry-drag-placeholder"
      fallback-class="pantry-drag-lifted"
      @start="$emit('drag', true)"
      @end="$emit('drag', false)"
      @add="onAdd"
    >
      <PantryItemRow
        v-for="item in list"
        :key="item.id"
        :item="item"
        :today="today"
        @edit="$emit('edit', $event)"
        @opened="$emit('opened', $event)"
        @remove="$emit('remove', $event)"
      />
    </VueDraggable>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import { useMediaQuery } from "@vueuse/core";
import { VueDraggable } from "vue-draggable-plus";
import PantryItemRow from "./PantryItemRow.vue";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";

const props = defineProps<{
  location: PantryLocation;
  items: PantryItemOut[];
  today: Date;
}>();

const emit = defineEmits<{
  (e: "edit" | "opened" | "remove", item: PantryItemOut): void;
  (e: "move", itemId: string, location: PantryLocation): void;
  (e: "drag", dragging: boolean): void;
}>();

const headingId = useId();
const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

// Sortable moves rows between these lists while dragging; rebuilt whenever the pantry reloads.
const list = ref<PantryItemOut[]>([]);
watch(() => props.items, (items) => {
  list.value = [...items];
}, { immediate: true });

function onAdd(event: { item: HTMLElement }) {
  const itemId = event.item.dataset.itemId;
  if (itemId) {
    emit("move", itemId, props.location);
  }
}
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

.pantry-drag-placeholder {
  opacity: 0.35;
}

.pantry-drag-lifted {
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow-float);
  cursor: grabbing;
}
</style>
