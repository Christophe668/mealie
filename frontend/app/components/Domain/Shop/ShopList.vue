<template>
  <div class="shop-list">
    <!-- First in the DOM (it is the main action); CSS pins it at the bottom on mobile. -->
    <ShopQuickAdd class="shop-list__add" @add="$emit('add', $event)" />

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
      @toggle="$emit('toggle', $event)"
      @edit="$emit('edit', $event)"
    />

    <ShopBought
      v-if="bought.length"
      :items="bought"
      :recipe-names="recipeNames"
      @toggle="$emit('toggle', $event)"
      @edit="$emit('edit', $event)"
      @clear="$emit('clearBought')"
    />
  </div>
</template>

<script setup lang="ts">
import ShopAisle from "./ShopAisle.vue";
import ShopBought from "./ShopBought.vue";
import ShopQuickAdd from "./ShopQuickAdd.vue";
import { shopAisles, shopBought, type ShopAisleGroup } from "~/composables/use-shop";
import type { ShoppingListItemOut, ShoppingListOut } from "~/lib/api/types/household";

const props = defineProps<{
  list: ShoppingListOut;
  /** The upstream composable's label grouping, mapped with `toByLabel`. */
  byLabel: ShopAisleGroup[];
}>();

defineEmits<{
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
