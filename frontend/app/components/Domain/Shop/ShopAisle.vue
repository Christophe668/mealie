<template>
  <section class="shop-aisle" :aria-labelledby="headingId">
    <h2 :id="headingId" class="shop-aisle__heading">
      <span class="shop-aisle__name">{{ name }}</span>
      <span class="shop-aisle__count" aria-hidden="true">{{ items.length }}</span>
      <span class="shop-aisle__sr">{{ $t("shop.to-buy", { count: items.length }) }}</span>
    </h2>
    <ul class="shop-aisle__items" role="list">
      <ShopItemRow
        v-for="item in items"
        :key="item.id"
        :item="item"
        :recipe-names="recipeNames"
        @toggle="$emit('toggle', $event)"
        @edit="$emit('edit', $event)"
      />
    </ul>
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import ShopItemRow from "./ShopItemRow.vue";
import type { ShoppingListItemOut } from "~/lib/api/types/household";
import type { MultiPurposeLabelSummary } from "~/lib/api/types/labels";

const props = defineProps<{
  /** null = the unlabelled items, shown as "Other". */
  label: MultiPurposeLabelSummary | null;
  items: ShoppingListItemOut[];
  recipeNames: Map<string, string>;
}>();

defineEmits<{
  (e: "toggle" | "edit", item: ShoppingListItemOut): void;
}>();

const i18n = useI18n();
const headingId = useId();
const name = computed(() => props.label?.name || i18n.t("shop.other"));
</script>

<style scoped>
.shop-aisle {
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.5);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.shop-aisle__heading {
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

.shop-aisle__count {
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.shop-aisle__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.shop-aisle__items {
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
