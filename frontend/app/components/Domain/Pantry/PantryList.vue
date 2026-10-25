<template>
  <div class="pantry-list">
    <PantryGroup
      v-for="group in groups"
      :key="group.location"
      :location="group.location"
      :items="group.items"
      :today="today"
      @edit="$emit('edit', $event)"
      @opened="$emit('opened', $event)"
      @remove="$emit('remove', $event)"
      @move="(itemId, location) => $emit('move', itemId, location)"
      @drag="dragging = $event"
    />

    <!--
      While dragging, every place (empty ones too) is a target in a bar floating over the bottom of the screen,
      so nothing on the page moves under the pointer. Each target is an empty Sortable list in the same group.
    -->
    <div
      class="pantry-list__dropbar"
      :class="{ 'pantry-list__dropbar--on': dragging }"
      :aria-hidden="dragging ? undefined : 'true'"
      :aria-label="$t('pantry.move-to')"
    >
      <span class="pantry-list__dropbar-label" aria-hidden="true">{{ $t("pantry.move-to") }}</span>
      <VueDraggable
        v-for="location in PANTRY_LOCATIONS"
        :key="location"
        :model-value="[]"
        class="pantry-list__target"
        :data-location="location"
        group="pantry"
        :sort="false"
        draggable=".pantry-row"
        ghost-class="pantry-list__target-ghost"
        @add="onDrop($event, location)"
      >
        <!-- Not a draggable item (only .pantry-row is), just the target's name. -->
        <span class="pantry-list__target-name">{{ $t(`pantry.location.${location}`) }}</span>
      </VueDraggable>
    </div>
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from "vue-draggable-plus";
import PantryGroup from "./PantryGroup.vue";
import { PANTRY_LOCATIONS, type PantryGroupData } from "~/lib/pantry/freshness";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";

const props = defineProps<{
  byLocation: PantryGroupData[];
  today: Date;
}>();

const emit = defineEmits<{
  (e: "edit" | "opened" | "remove", item: PantryItemOut): void;
  (e: "move", itemId: string, location: PantryLocation): void;
}>();

const dragging = ref(false);

/** Always Fridge, Freezer, Cupboard, Other, whatever order the groups come in; empty ones are hidden. */
const groups = computed(() =>
  PANTRY_LOCATIONS
    .map(location => props.byLocation.find(group => group.location === location))
    .filter((group): group is PantryGroupData => !!group && group.items.length > 0),
);

function onDrop(event: { item: HTMLElement }, location: PantryLocation) {
  const itemId = event.item.dataset.itemId;
  // The row was moved into the target's DOM; take it out again, the reload puts it in its new place.
  event.item.remove();
  if (itemId) {
    emit("move", itemId, location);
  }
}
</script>

<style scoped>
.pantry-list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.pantry-list__dropbar {
  position: fixed;
  z-index: 10;
  right: 0;
  bottom: var(--ds-tabbar-clearance, calc(var(--ds-space) * 2));
  left: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--ds-space);
  width: fit-content;
  max-width: calc(100% - var(--ds-space) * 4);
  margin: 0 auto;
  padding: var(--ds-space);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  box-shadow: var(--ds-shadow-float);
  /* Faded out, not removed, until a drag starts: it fades in without moving anything on the page. */
  opacity: 0;
  pointer-events: none;
  transform: translateY(var(--ds-space));
  transition:
    opacity 120ms ease,
    transform 120ms ease;
}

.pantry-list__dropbar--on {
  opacity: 1;
  pointer-events: auto;
  transform: none;
}

@media (prefers-reduced-motion: reduce) {
  .pantry-list__dropbar {
    transition: none;
  }
}

.pantry-list__dropbar-label {
  padding: 0 calc(var(--ds-space) * 0.5);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 600;
}

.pantry-list__target {
  display: flex;
  align-items: center;
  min-width: calc(var(--ds-space) * 10);
  min-height: calc(var(--ds-space) * 6);
  padding: 0 calc(var(--ds-space) * 2);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  font-weight: 600;
}

/* The pointer is over this target: it lights up; the dragged row's placeholder stays hidden inside it. */
.pantry-list__target:has(.pantry-list__target-ghost) {
  border-style: solid;
  border-color: var(--ds-accent);
  background: var(--ds-accent);
  color: var(--ds-accent-text);
}

.pantry-list__target :deep(.pantry-list__target-ghost) {
  display: none;
}
</style>
