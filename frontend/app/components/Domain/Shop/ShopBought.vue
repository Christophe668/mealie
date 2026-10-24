<template>
  <section class="shop-bought" :aria-labelledby="headingId">
    <div class="shop-bought__head">
      <h2 :id="headingId" class="shop-bought__heading">
        <button
          type="button"
          class="shop-bought__toggle ds-focus"
          :aria-expanded="open ? 'true' : 'false'"
          :aria-controls="listId"
          @click="open = !open"
        >
          {{ $t("shop.bought", { count: items.length }, items.length) }}
          <DsIcon name="chevronDown" :size="22" class="shop-bought__chevron" :class="{ 'shop-bought__chevron--open': open }" />
        </button>
      </h2>
      <div class="shop-bought__actions">
        <DsButton variant="line" icon="delete" class="shop-bought__clear" @click="$emit('clear')">
          {{ $t("shop.clear-bought") }}
        </DsButton>
        <!-- Ink, not saffron: the open-count badge is this screen's one accent. -->
        <DsButton
          variant="dark"
          icon="archiveArrowDown"
          class="shop-bought__put-away"
          :disabled="putting"
          :aria-label="$t('shop.put-away-label', { count: items.length }, items.length)"
          @click="$emit('put-away')"
        >
          {{ $t("shop.put-away") }}
        </DsButton>
      </div>
    </div>
    <!-- v-if: bought rows (each running the ingredient parser) only exist while the section is open. -->
    <ul v-if="open" :id="listId" class="shop-bought__list" role="list">
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
import DsButton from "~/components/Design/DsButton.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { ShoppingListItemOut } from "~/lib/api/types/household";

withDefaults(defineProps<{
  items: ShoppingListItemOut[];
  recipeNames: Map<string, string>;
  /** A put away is running: the button stays focusable but does nothing. */
  putting?: boolean;
}>(), { putting: false });

defineEmits<{
  (e: "toggle" | "edit", item: ShoppingListItemOut): void;
  (e: "clear" | "put-away"): void;
}>();

const headingId = useId();
const listId = useId();
const open = ref(false);
</script>

<style scoped>
.shop-bought {
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.shop-bought__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 0.5) 0;
}

.shop-bought__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
}

.shop-bought__heading {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  line-height: 1.2;
}

.shop-bought__toggle {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.5);
  min-height: 44px;
  padding: 0 calc(var(--ds-space) * 0.5);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  font: inherit;
  letter-spacing: inherit;
  cursor: pointer;
}

.shop-bought__toggle:hover {
  color: var(--ds-text);
}

.shop-bought__chevron {
  transition: transform 160ms ease;
}

.shop-bought__chevron--open {
  transform: rotate(180deg);
}

.shop-bought__list {
  margin: 0;
  padding: 0 0 calc(var(--ds-space) * 0.5);
  border-top: 1px solid var(--ds-border);
  list-style: none;
}

@media (prefers-reduced-motion: reduce) {
  .shop-bought__chevron {
    transition: none;
  }
}
</style>
