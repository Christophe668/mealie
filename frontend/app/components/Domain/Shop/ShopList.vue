<template>
  <div ref="root" class="shop-list">
    <!-- First in the DOM (it is the main action); CSS pins it at the bottom on mobile. -->
    <ShopQuickAdd ref="quickAdd" class="shop-list__add" @add="$emit('add', $event)" />

    <div v-if="!aisles.length" class="shop-list__empty">
      <p class="shop-list__empty-title">
        {{ bought.length ? $t("shop.all-bought") : $t("shop.nothing-to-buy") }}
      </p>
      <p class="shop-list__empty-text ds-muted">
        {{ $t("shop.nothing-to-buy-hint") }}
      </p>
    </div>

    <ShopAisle
      v-for="aisle in aisles"
      :key="aisle.label?.id ?? 'other'"
      :label="aisle.label"
      :items="aisle.items"
      :recipe-names="recipeNames"
      @toggle="onToggle"
      @edit="$emit('edit', $event)"
    />

    <ShopBought
      v-if="bought.length"
      :items="bought"
      :recipe-names="recipeNames"
      @toggle="onToggle"
      @edit="$emit('edit', $event)"
      @clear="$emit('clearBought')"
    />
  </div>
</template>

<script setup lang="ts">
import ShopAisle from "./ShopAisle.vue";
import ShopBought from "./ShopBought.vue";
import ShopQuickAdd from "./ShopQuickAdd.vue";
import { nextTick, useTemplateRef } from "vue";
import { shopAisles, shopBought, type ShopAisleGroup } from "~/composables/use-shop";
import type { ComponentPublicInstance } from "vue";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";

const props = defineProps<{
  list: ShoppingListOut;
  /** The upstream composable's label grouping, mapped with `toByLabel`. */
  byLabel: ShopAisleGroup[];
}>();

const emit = defineEmits<{
  (e: "toggle" | "edit", item: ShoppingListItemOut): void;
  (e: "add", text: string): void;
  (e: "clearBought"): void;
}>();

const aisles = computed(() => shopAisles(props.list, props.byLabel));
const bought = computed(() => shopBought(props.list));

const recipeNames = computed(() => new Map(
  (props.list.recipeReferences ?? [])
    .filter(ref => ref.recipe?.name)
    .map(ref => [ref.recipeId, ref.recipe.name as string]),
));

// =====================================================
// Keyboard focus: a toggled row moves to the other section and unmounts, which would drop focus to <body>.
// Keep the user where they were: the next row of the same section, else the previous one; when the section
// empties (and disappears) the first row of the following section, else the last row before it; else the
// quick-add field.

const root = useTemplateRef<HTMLElement>("root");
const quickAdd = useTemplateRef<ComponentPublicInstance>("quickAdd");

function focusCandidates(itemId: string): string[] {
  const sections = [...(root.value?.querySelectorAll<HTMLElement>(".shop-aisle, .shop-bought") ?? [])];
  const rowIds = (section: Element) =>
    [...section.querySelectorAll<HTMLElement>("[data-item-id]")].map(row => row.dataset.itemId!).filter(id => id !== itemId);
  const index = sections.findIndex(section => section.querySelector(`[data-item-id="${CSS.escape(itemId)}"]`));
  if (index === -1) {
    return [];
  }
  const own = [...sections[index]!.querySelectorAll<HTMLElement>("[data-item-id]")].map(row => row.dataset.itemId!);
  const at = own.indexOf(itemId);
  const after = sections.slice(index + 1).flatMap(rowIds);
  const before = sections.slice(0, index).flatMap(rowIds).reverse();
  return [...own.slice(at + 1), ...own.slice(0, at).reverse(), ...after, ...before];
}

async function onToggle(item: ShoppingListItemOut) {
  const row = root.value?.querySelector(`[data-item-id="${CSS.escape(item.id)}"]`);
  const hadFocus = !!row && row.contains(document.activeElement);
  const candidates = hadFocus ? focusCandidates(item.id) : [];
  emit("toggle", item);
  if (!hadFocus) {
    return;
  }
  await nextTick();
  if (row?.isConnected && row.contains(document.activeElement)) {
    return;
  }
  for (const id of candidates) {
    const box = document.getElementById(`shop-item-${id}`);
    if (box) {
      box.focus();
      return;
    }
  }
  (quickAdd.value?.$el as HTMLElement | undefined)?.querySelector("input")?.focus();
}
</script>

<style scoped>
.shop-list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.shop-list__empty {
  padding: calc(var(--ds-space) * 3);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.shop-list__empty-title {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.shop-list__empty-text {
  margin: calc(var(--ds-space) * 0.5) 0 0;
  max-width: 70ch;
  font-size: var(--ds-t-2);
}

/* Mobile: the field rides just above the floating tab bar while the list scrolls under it. */
@media (max-width: 1023px) {
  .shop-list__add {
    position: sticky;
    bottom: var(--ds-tabbar-clearance, calc(var(--ds-space) * 2));
    z-index: 2;
    order: 99;
    box-shadow: var(--ds-shadow-float);
  }
}
</style>
