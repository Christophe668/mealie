<template>
  <section class="pantry-group" :aria-labelledby="headingId">
    <h2 :id="headingId" class="pantry-group__heading">
      <span class="pantry-group__icon" aria-hidden="true">
        <DsIcon :name="LOCATION_ICONS[location]" :size="18" />
      </span>
      <span class="pantry-group__name">{{ $t(`pantry.location.${location}`) }}</span>
      <span class="pantry-group__count" aria-hidden="true">{{ items.length }}</span>
      <span class="pantry-group__sr">{{ $t("pantry.item-count", { count: items.length }, items.length) }}</span>
    </h2>
    <!--
      Long-press an item, then drag it onto another place to move it there; the order inside a place stays
      "use first". The press delay keeps a plain swipe a scroll and a tap a tap; moving the finger before the
      delay ends cancels the drag.
    -->
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
      :delay="LONG_PRESS_MS"
      :touch-start-threshold="8"
      filter=".pantry-row__more"
      :prevent-on-filter="false"
      ghost-class="pantry-drag-placeholder"
      fallback-class="pantry-drag-lifted"
      chosen-class="pantry-drag-chosen"
      @choose="onChoose"
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
    <button
      v-if="hiddenCount > 0 || expanded"
      type="button"
      class="pantry-group__fold ds-focus"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? $t("pantry.show-less") : $t("pantry.show-more", { count: hiddenCount }) }}
      <DsIcon name="chevronDown" :size="18" :class="{ 'pantry-group__chevron--up': expanded }" />
    </button>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import { useMediaQuery } from "@vueuse/core";
import { VueDraggable } from "vue-draggable-plus";
import PantryItemRow from "./PantryItemRow.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { byFreshness } from "~/lib/pantry/freshness";
import type { PantryItemOut, PantryLocation } from "~/lib/api/types/household";
import type { Icon } from "~/lib/icons/icon-type";

const props = withDefaults(defineProps<{
  location: PantryLocation;
  items: PantryItemOut[];
  today: Date;
  /** Show only the first few items behind a "Show N more" button (off while searching or filtering). */
  foldable?: boolean;
}>(), { foldable: true });

/** Items shown before the group folds. */
const FOLD_AFTER = 5;

const LOCATION_ICONS: Record<PantryLocation, keyof Icon> = {
  fridge: "fridgeOutline",
  freezer: "snowflake",
  cupboard: "cupboard",
  other: "otherPlace",
};

const emit = defineEmits<{
  (e: "edit" | "opened" | "remove", item: PantryItemOut): void;
  (e: "move", itemId: string, location: PantryLocation): void;
  (e: "drag", dragging: boolean): void;
}>();

/** How long an item must be held before it can be dragged. */
const LONG_PRESS_MS = 400;

const headingId = useId();
const reduceMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

const expanded = ref(false);

// Worst first, so a folded group still shows what needs attention.
const sorted = computed(() => byFreshness(props.items, props.today));
const folded = computed(() => props.foldable && !expanded.value);
const hiddenCount = computed(() => (folded.value ? Math.max(0, sorted.value.length - FOLD_AFTER) : 0));

// Sortable moves rows between these lists while dragging; rebuilt whenever the pantry reloads or folds.
const list = ref<PantryItemOut[]>([]);
watch([sorted, folded], ([items, isFolded]) => {
  list.value = isFolded ? items.slice(0, FOLD_AFTER) : [...items];
}, { immediate: true });

// The long press succeeded: a short buzz where the device supports it (Android), the lift style everywhere.
function onChoose() {
  navigator.vibrate?.(15);
}

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
  align-items: center;
  gap: var(--ds-space);
  margin: 0;
  padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 0.5);
  font-size: var(--ds-t-3);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.pantry-group__icon {
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
}

.pantry-group__name {
  flex: 1;
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

.pantry-group__fold {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: calc(var(--ds-space) * 0.5);
  width: 100%;
  min-height: 44px;
  padding: 0;
  border: 0;
  border-top: 1px solid var(--ds-border);
  border-radius: 0;
  background: none;
  color: var(--ds-text-2);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 600;
  cursor: pointer;
}

.pantry-group__fold:hover {
  color: var(--ds-text);
}

.pantry-group__chevron--up {
  transform: rotate(180deg);
}

/* A long press must not open the system text-selection or link callout. */
.pantry-group__items > :deep(.pantry-row) {
  -webkit-touch-callout: none;
  user-select: none;
}

.pantry-drag-chosen {
  background: var(--ds-surface);
  box-shadow: var(--ds-shadow-float);
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
