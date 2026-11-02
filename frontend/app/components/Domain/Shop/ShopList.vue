<template>
  <div ref="root" class="shop-list">
    <!-- First in the DOM (it is the main action); CSS pins it at the bottom on mobile. -->
    <ShopQuickAdd ref="quickAdd" class="shop-list__add" @add="$emit('add', $event)" />

    <!-- Only offered when the list holds recipes: without them the recipe view is one "No recipe" group. -->
    <div
      v-if="recipeNames.size"
      class="shop-list__view"
      role="radiogroup"
      :aria-label="$t('shop.group-by')"
    >
      <button
        v-for="option in viewOptions"
        :key="option.value"
        type="button"
        role="radio"
        class="shop-list__view-option ds-focus"
        :class="{ 'shop-list__view-option--on': groupBy === option.value }"
        :aria-checked="groupBy === option.value ? 'true' : 'false'"
        @click="preferences.groupBy = option.value"
      >
        <DsIcon :name="option.icon" :size="18" />
        {{ option.label }}
      </button>
    </div>

    <div v-if="!groups.length" ref="empty" class="shop-list__empty" tabindex="-1">
      <p class="shop-list__empty-title">
        {{ bought.length ? $t("shop.all-bought") : $t("shop.nothing-to-buy") }}
      </p>
      <p class="shop-list__empty-text ds-muted">
        {{ $t("shop.nothing-to-buy-hint") }}
      </p>
    </div>

    <template v-if="groupBy === 'recipe'">
      <ShopAisle
        v-for="group in recipeGroups"
        :key="group.recipeId ?? 'no-recipe'"
        :title="group.name ?? $t('shop.no-recipe')"
        :entries="group.entries"
        :recipe-names="recipeNames"
        @toggle="onToggle"
        @actions="$emit('actions', $event)"
      />
    </template>
    <template v-else>
      <ShopAisle
        v-for="aisle in aisles"
        :key="aisle.label?.id ?? 'other'"
        :label="aisle.label"
        :items="aisle.items"
        :recipe-names="recipeNames"
        @toggle="onToggle"
        @actions="$emit('actions', $event)"
      />
    </template>

    <ShopBought
      v-if="bought.length"
      :items="bought"
      :recipe-names="recipeNames"
      :putting="putting"
      @toggle="onToggle"
      @actions="$emit('actions', $event)"
      @clear="$emit('clearBought')"
      @put-away="onPutAway"
    />
  </div>
</template>

<script setup lang="ts">
import ShopAisle from "./ShopAisle.vue";
import ShopBought from "./ShopBought.vue";
import ShopQuickAdd from "./ShopQuickAdd.vue";
import { nextTick, useTemplateRef } from "vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { shopAisles, shopBought, shopRecipes, type ShopAisleGroup } from "~/composables/use-shop";
import { useShoppingListPreferences } from "~/composables/use-users/preferences";
import { recipeNamesOf } from "~/lib/shop/item-for-text";
import type { ComponentPublicInstance } from "vue";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";

const props = defineProps<{
  list: ShoppingListOut;
  /** The upstream composable's label grouping, mapped with `toByLabel`. */
  byLabel: ShopAisleGroup[];
  /** A put away is running. */
  putting?: boolean;
}>();

const emit = defineEmits<{
  (e: "toggle" | "actions", item: ShoppingListItemOut): void;
  (e: "add", text: string): void;
  (e: "clearBought" | "putAway"): void;
}>();

const aisles = computed(() => shopAisles(props.list, props.byLabel));
const bought = computed(() => shopBought(props.list));

const recipeNames = computed(() => recipeNamesOf(props.list));

// =====================================================
// Grouping: by aisle (the shop's walk) or by recipe (what each dish needs). Remembered on this device.

const i18n = useI18n();
const preferences = useShoppingListPreferences();
const groupBy = computed(() => (recipeNames.value.size ? preferences.value.groupBy : "aisle"));
const viewOptions = computed(() => [
  { value: "aisle" as const, label: i18n.t("shop.group-by-aisle"), icon: "tags" as const },
  { value: "recipe" as const, label: i18n.t("shop.group-by-recipe"), icon: "silverwareForkKnife" as const },
]);

/** The same item in a second recipe group gets its own ids, so each checkbox keeps its own label. */
const recipeGroups = computed(() => {
  const seen = new Set<string>();
  return shopRecipes(props.list, recipeNames.value).map(group => ({
    ...group,
    entries: group.entries.map((entry) => {
      const repeat = seen.has(entry.item.id);
      seen.add(entry.item.id);
      return { ...entry, idSuffix: repeat ? (group.recipeId ?? "none") : undefined };
    }),
  }));
});

const groups = computed(() => (groupBy.value === "recipe" ? recipeGroups.value : aisles.value));

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

/**
 * Where focus should go once the item's row is gone, worked out now while the row is still there: the
 * returned getter gives the first of those rows still on screen, else the quick-add field. The page's item
 * sheet uses it too, for actions that take the row (and the button that opened the sheet) away.
 */
function focusAfter(itemId: string): () => HTMLElement | null {
  const candidates = focusCandidates(itemId);
  return () => {
    for (const id of candidates) {
      const box = document.getElementById(`shop-item-${id}`);
      if (box) {
        return box;
      }
    }
    return (quickAdd.value?.$el as HTMLElement | undefined)?.querySelector("input") ?? null;
  };
}

defineExpose({ focusAfter });

async function onToggle(item: ShoppingListItemOut) {
  const row = root.value?.querySelector(`[data-item-id="${CSS.escape(item.id)}"]`);
  const hadFocus = !!row && row.contains(document.activeElement);
  const target = hadFocus ? focusAfter(item.id) : null;
  emit("toggle", item);
  if (!target) {
    return;
  }
  await nextTick();
  if (row?.isConnected && row.contains(document.activeElement)) {
    return;
  }
  target()?.focus();
}

// Put away empties the Bought section, taking the focused button with it. Land on the first open row,
// else on the empty state (not the quick-add field, which would pop the keyboard on a phone).
const emptyState = useTemplateRef<HTMLElement>("empty");
let refocusAfterPutAway = false;

function onPutAway() {
  refocusAfterPutAway = !!root.value?.querySelector(".shop-bought")?.contains(document.activeElement);
  emit("putAway");
}

// A put away that ends with the items still there (it failed) leaves focus alone from then on. Checked a
// tick later, so a successful reload has already emptied the section and moved focus.
watch(() => props.putting, async (busy) => {
  if (busy) {
    return;
  }
  await nextTick();
  if (bought.value.length) {
    refocusAfterPutAway = false;
  }
});

watch(bought, async (items) => {
  if (items.length || !refocusAfterPutAway) {
    return;
  }
  refocusAfterPutAway = false;
  await nextTick();
  if (document.activeElement && document.activeElement !== document.body) {
    return;
  }
  const firstRow = root.value?.querySelector<HTMLElement>(".shop-aisle input[type=checkbox]");
  (firstRow ?? emptyState.value)?.focus();
});
</script>

<style scoped>
.shop-list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.shop-list__empty {
  outline: none;
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

.shop-list__view {
  display: flex;
  align-self: flex-start;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
}

.shop-list__view-option {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.75);
  min-height: 38px;
  padding: 0 calc(var(--ds-space) * 1.5);
  border: 0;
  border-radius: calc(var(--ds-radius-ctl) - 2px);
  background: none;
  color: var(--ds-text-2);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 600;
  cursor: pointer;
}

.shop-list__view-option:hover {
  color: var(--ds-text);
}

/* Ink, not saffron: the open-count badge stays the screen's one accent. */
.shop-list__view-option--on,
.shop-list__view-option--on:hover {
  background: var(--ds-text);
  color: var(--ds-bg);
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
