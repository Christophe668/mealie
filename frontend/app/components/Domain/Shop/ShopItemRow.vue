<template>
  <li
    class="shop-row"
    :class="{ 'shop-row--bought': item.checked }"
    :data-item-id="item.id"
  >
    <!-- Ticking stays one tap away: the checkbox's hit area is the row's whole left edge. -->
    <label class="shop-row__tick">
      <input
        :id="boxId"
        type="checkbox"
        class="shop-row__box ds-focus"
        :checked="!!item.checked"
        :aria-labelledby="nameId"
        :aria-describedby="forText ? forId : undefined"
        @click="onBoxClick"
      >
    </label>
    <!-- The rest of the row opens the item's options: bought, pantry, edit, remove. -->
    <button
      type="button"
      class="shop-row__open ds-focus"
      aria-haspopup="dialog"
      :title="$t('shop.item-actions', { item: plainName })"
      @click="$emit('actions', item)"
    >
      <span class="shop-row__text">
        <!-- The shared ingredient parser sanitises its output (fractions come as <sup>/<sub>). -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <span :id="nameId" class="shop-row__name" v-html="text.name" />
        <span v-if="forText" :id="forId" class="shop-row__for">{{ forText }}</span>
      </span>
      <!-- eslint-disable-next-line vue/no-v-html -->
      <span v-if="text.qty" class="shop-row__qty" v-html="text.qty" />
      <DsIcon name="chevronRight" :size="18" class="shop-row__chevron" />
    </button>
  </li>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import { useIngredientTextParser } from "~/composables/recipes";
import type { ShoppingListItemOut } from "~/lib/api/types/household";
import { itemForText } from "~/lib/shop/item-for-text";

const props = defineProps<{
  item: ShoppingListItemOut;
  /** Recipe names by id, from the list's recipe references. */
  recipeNames: Map<string, string>;
  /** Shown instead of the item's own quantity: one recipe's share, in the recipe view. */
  quantity?: number;
  /** In the recipe view: the item's other recipes, said as "Also for …" instead of "For …". */
  alsoFor?: string[];
  /** Tells apart the ids of the same item shown in several recipe groups; the first has none. */
  idSuffix?: string;
}>();

const emit = defineEmits<{
  (e: "toggle" | "actions", item: ShoppingListItemOut): void;
}>();

const i18n = useI18n();
const boxId = computed(() => `shop-item-${props.item.id}${props.idSuffix ? `-${props.idSuffix}` : ""}`);
const forId = computed(() => `${boxId.value}-for`);
const nameId = computed(() => `${boxId.value}-name`);

const { useParsedIngredientText } = useIngredientTextParser();

/** Food (or the free-text note) on the left, quantity and unit on the right; a note on a food follows it. */
const text = computed(() => {
  const shown = props.quantity === undefined ? props.item : { ...props.item, quantity: props.quantity };
  const parsed = useParsedIngredientText(shown, 1, true);
  const name = parsed.name ? [parsed.name, parsed.note].filter(Boolean).join(", ") : (parsed.note ?? "");
  const qty = [parsed.quantity, parsed.unit].filter(Boolean).join(" ");
  return { name, qty };
});

const plainName = computed(() => props.item.food?.name || props.item.note || i18n.t("recipe.ingredient"));

const forText = computed(() => {
  if (!props.alsoFor) {
    return itemForText(props.item, props.recipeNames, i18n.t);
  }
  const [first, ...rest] = props.alsoFor;
  if (!first) {
    return "";
  }
  return rest.length
    ? i18n.t("shop.also-for-recipe-and-more", { recipe: first, count: rest.length })
    : i18n.t("shop.also-for-recipe", { recipe: first });
});

// The checkbox stays controlled: it shows the item's state, and the parent flips it optimistically.
// preventDefault makes the browser restore the old state after dispatch; that is only safe because a toggled
// row always moves between an aisle and Bought and so unmounts. A row that ever toggles in place must also
// set `(event.target as HTMLInputElement).checked = !!props.item.checked` on nextTick.
function onBoxClick(event: MouseEvent) {
  event.preventDefault();
  emit("toggle", props.item);
}
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

.shop-row__tick {
  display: flex;
  flex: none;
  align-items: center;
  align-self: stretch;
  padding: 0 calc(var(--ds-space) * 1) 0 calc(var(--ds-space) * 0.5);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.shop-row__box {
  width: 24px;
  height: 24px;
  margin: 0;
  accent-color: var(--ds-text);
  cursor: pointer;
}

.shop-row__open {
  display: flex;
  flex: 1;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  min-width: 0;
  min-height: 52px;
  padding: var(--ds-space) calc(var(--ds-space) * 0.5) var(--ds-space) calc(var(--ds-space) * 0.5);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.shop-row__open:hover .shop-row__chevron {
  color: var(--ds-text);
}

.shop-row__open:active {
  background: var(--ds-bg);
}

.shop-row__chevron {
  flex: none;
  color: var(--ds-text-2);
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

/* Wraps like the name: a long recipe title is read in full rather than cut at the row's edge. */
.shop-row__for {
  margin-top: 2px;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  line-height: 1.3;
  overflow-wrap: anywhere;
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
  .shop-row__open {
    min-height: 44px;
  }
}
</style>
