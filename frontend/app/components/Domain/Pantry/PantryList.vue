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
    />
  </div>
</template>

<script setup lang="ts">
import PantryGroup from "./PantryGroup.vue";
import { PANTRY_LOCATIONS, type PantryGroupData } from "~/lib/pantry/freshness";
import type { PantryItemOut } from "~/lib/api/types/household";

const props = defineProps<{
  byLocation: PantryGroupData[];
  today: Date;
}>();

defineEmits<{
  (e: "edit" | "opened" | "remove", item: PantryItemOut): void;
}>();

/** Always Fridge, Freezer, Cupboard, Other, whatever order the groups come in; empty ones are hidden. */
const groups = computed(() =>
  PANTRY_LOCATIONS
    .map(location => props.byLocation.find(group => group.location === location))
    .filter((group): group is PantryGroupData => !!group && group.items.length > 0),
);
</script>

<style scoped>
.pantry-list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}
</style>
