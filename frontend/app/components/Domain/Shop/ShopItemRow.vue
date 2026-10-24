<template>
  <li
    class="shop-row"
    :class="{ 'shop-row--bought': item.checked }"
    :data-item-id="item.id"
  >
    <input
      :id="boxId"
      type="checkbox"
      class="shop-row__box ds-focus"
      :checked="!!item.checked"
      :aria-describedby="forText ? forId : undefined"
      @click="onBoxClick"
    >
    <!-- The whole row is the checkbox's label, so a tap anywhere on it ticks the item. -->
    <label
      :for="boxId"
      class="shop-row__label"
      @click="onLabelClick"
      @pointerdown="startPress"
      @pointermove="movePress"
      @pointerup="cancelPress"
      @pointerleave="cancelPress"
      @pointercancel="cancelPress"
      @contextmenu="onContextMenu"
    >
      <span class="shop-row__text">
        <!-- The shared ingredient parser sanitises its output (fractions come as <sup>/<sub>). -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <span class="shop-row__name" v-html="text.name" />
        <span v-if="forText" :id="forId" class="shop-row__for">{{ forText }}</span>
      </span>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <span v-if="text.qty" class="shop-row__qty" v-html="text.qty" />
    </label>
    <button
      type="button"
      class="shop-row__more ds-focus"
      :aria-label="$t('shop.edit-item', { item: plainName })"
      :title="$t('shop.edit-item', { item: plainName })"
      @click="$emit('edit', item)"
    >
      <DsIcon name="dotsVertical" :size="20" />
    </button>
  </li>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import { useIngredientTextParser } from "~/composables/recipes";
import type { ShoppingListItemOut } from "~/lib/api/types/household";

const props = defineProps<{
  item: ShoppingListItemOut;
  /** Recipe names by id, from the list's recipe references. */
  recipeNames: Map<string, string>;
}>();

const emit = defineEmits<{
  (e: "toggle" | "edit", item: ShoppingListItemOut): void;
}>();

const i18n = useI18n();
const boxId = computed(() => `shop-item-${props.item.id}`);
const forId = computed(() => `shop-item-${props.item.id}-for`);

const { useParsedIngredientText } = useIngredientTextParser();

/** Food (or the free-text note) on the left, quantity and unit on the right; a note on a food follows it. */
const text = computed(() => {
  const parsed = useParsedIngredientText(props.item, 1, true);
  const name = parsed.name ? [parsed.name, parsed.note].filter(Boolean).join(", ") : (parsed.note ?? "");
  const qty = [parsed.quantity, parsed.unit].filter(Boolean).join(" ");
  return { name, qty };
});

const plainName = computed(() => props.item.food?.name || props.item.note || i18n.t("recipe.ingredient"));

const forText = computed(() => {
  const names = [...new Set((props.item.recipeReferences ?? []).map(ref => ref.recipeId))]
    .map(id => props.recipeNames.get(id))
    .filter((name): name is string => !!name);
  if (!names.length) {
    return "";
  }
  if (names.length === 1) {
    return i18n.t("shop.for-recipe", { recipe: names[0] });
  }
  return i18n.t("shop.for-recipe-and-more", { recipe: names[0], count: names.length - 1 });
});

// The checkbox stays controlled: it shows the item's state, and the parent flips it optimistically.
function onBoxClick(event: MouseEvent) {
  event.preventDefault();
  if (suppressClick) {
    suppressClick = false;
    return;
  }
  emit("toggle", props.item);
}

// =====================================================
// Long press opens the editor (the kebab is the visible way to do the same).

const LONG_PRESS_MS = 500;
const MOVE_TOLERANCE = 10;
let pressTimer: ReturnType<typeof setTimeout> | undefined;
let pressStart = { x: 0, y: 0 };
let suppressClick = false;

function startPress(event: PointerEvent) {
  if (event.pointerType === "mouse" && event.button !== 0) {
    return;
  }
  suppressClick = false;
  pressStart = { x: event.clientX, y: event.clientY };
  clearTimeout(pressTimer);
  pressTimer = setTimeout(() => {
    pressTimer = undefined;
    suppressClick = true;
    emit("edit", props.item);
  }, LONG_PRESS_MS);
}

function movePress(event: PointerEvent) {
  if (pressTimer && Math.hypot(event.clientX - pressStart.x, event.clientY - pressStart.y) > MOVE_TOLERANCE) {
    cancelPress();
  }
}

function cancelPress() {
  clearTimeout(pressTimer);
  pressTimer = undefined;
}

/** The click that ends a long press must not also tick the item. */
function onLabelClick(event: MouseEvent) {
  if (suppressClick) {
    event.preventDefault();
    suppressClick = false;
  }
}

/** Touch browsers raise the context menu on a long press; the editor replaces it. */
function onContextMenu(event: MouseEvent) {
  if (suppressClick || pressTimer) {
    event.preventDefault();
  }
}

onBeforeUnmount(cancelPress);
</script>

<style scoped>
.shop-row {
  display: flex;
  align-items: center;
  min-height: 52px;
  border-bottom: 1px solid var(--ds-border);
}

.shop-row:last-child {
  border-bottom: 0;
}

.shop-row__box {
  flex: none;
  width: 24px;
  height: 24px;
  margin: 0 0 0 calc(var(--ds-space) * 0.5);
  accent-color: var(--ds-text);
  cursor: pointer;
}

.shop-row__label {
  display: flex;
  flex: 1;
  align-items: center;
  gap: calc(var(--ds-space) * 2);
  min-width: 0;
  min-height: 52px;
  padding: var(--ds-space) var(--ds-space) var(--ds-space) calc(var(--ds-space) * 1.5);
  cursor: pointer;
  user-select: none;
  -webkit-touch-callout: none;
  -webkit-tap-highlight-color: transparent;
}

.shop-row__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.shop-row__name {
  font-size: var(--ds-t-3);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.shop-row__for {
  overflow: hidden;
  margin-top: 2px;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.shop-row__qty {
  flex: none;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-variant-numeric: tabular-nums;
  text-align: right;
  white-space: nowrap;
}

.shop-row__qty :deep(sup),
.shop-row__qty :deep(sub) {
  font-size: 0.7em;
}

.shop-row__more {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
}

.shop-row__more:hover {
  color: var(--ds-text);
}

.shop-row--bought .shop-row__name,
.shop-row--bought .shop-row__qty {
  color: var(--ds-text-2);
  text-decoration: line-through;
  text-decoration-thickness: 1px;
}

.shop-row--bought .shop-row__for {
  opacity: 0.8;
}

@media (min-width: 1024px) {
  .shop-row,
  .shop-row__label {
    min-height: 44px;
  }
}
</style>
