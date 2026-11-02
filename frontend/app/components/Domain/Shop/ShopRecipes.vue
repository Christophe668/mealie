<template>
  <ul class="shop-recipes" role="list">
    <li v-for="recipe in recipes" :key="recipe.id!" class="shop-recipes__row">
      <!-- The name takes the whole width left of the counter and wraps, so a long title is read in full. -->
      <div class="shop-recipes__text">
        <NuxtLink
          v-if="!disabled && recipe.slug"
          :to="recipeRoute(recipe)"
          class="shop-recipes__name shop-recipes__name--link ds-focus"
        >
          {{ recipe.name }}
        </NuxtLink>
        <span v-else class="shop-recipes__name">{{ recipe.name }}</span>
        <p v-if="recipe.description" class="shop-recipes__description">
          {{ recipe.description }}
        </p>
      </div>
      <div class="shop-recipes__count">
        <button
          type="button"
          class="shop-recipes__step ds-focus"
          :disabled="disabled"
          :aria-label="$t('shop.recipe-less', { recipe: recipe.name })"
          @click="$emit('less', recipe.id!)"
        >
          <DsIcon name="minus" :size="20" />
        </button>
        <span class="shop-recipes__quantity">{{ quantityOf(recipe.id!) }}</span>
        <button
          type="button"
          class="shop-recipes__step ds-focus"
          :disabled="disabled"
          :aria-label="$t('shop.recipe-more', { recipe: recipe.name })"
          @click="$emit('more', recipe.id!)"
        >
          <DsIcon name="createAlt" :size="20" />
        </button>
      </div>
    </li>
  </ul>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import type { ShoppingListRecipeRefOut } from "~/lib/api/types/household";
import type { RecipeSummary } from "~/lib/api/types/recipe";

const props = defineProps<{
  recipes: RecipeSummary[];
  /** The list's recipe references, for how many times each recipe is on it. */
  references: ShoppingListRecipeRefOut[];
  /** Offline: no links, no counter. */
  disabled?: boolean;
}>();

defineEmits<{
  (e: "less" | "more", recipeId: string): void;
}>();

const auth = useMealieAuth();
const route = useRoute();
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");

function recipeRoute(recipe: RecipeSummary) {
  return `/g/${groupSlug.value}/r/${recipe.slug}`;
}

/** Looked up by id, not by position: the recipe list and the references need not share an order. */
function quantityOf(recipeId: string) {
  return props.references.find(ref => ref.recipeId === recipeId)?.recipeQuantity ?? 1;
}
</script>

<style scoped>
.shop-recipes {
  margin: 0;
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.5);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  list-style: none;
}

.shop-recipes__row {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  min-height: 52px;
  padding: var(--ds-space) calc(var(--ds-space) * 0.5);
  border-bottom: 1px solid var(--ds-border);
}

.shop-recipes__row:last-child {
  border-bottom: 0;
}

.shop-recipes__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.shop-recipes__name {
  color: var(--ds-text);
  font-size: var(--ds-t-3);
  font-weight: 600;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.shop-recipes__name--link {
  border-radius: var(--ds-radius-ctl);
  text-decoration: none;
}

.shop-recipes__name--link:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}

/* A description can be paragraphs long: three lines here, the whole text on the recipe page. */
.shop-recipes__description {
  display: -webkit-box;
  overflow: hidden;
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  line-height: 1.35;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
}

.shop-recipes__count {
  display: flex;
  flex: none;
  align-items: center;
}

.shop-recipes__step {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  cursor: pointer;
}

.shop-recipes__step:disabled {
  color: var(--ds-text-2);
  cursor: default;
  opacity: 0.5;
}

.shop-recipes__quantity {
  min-width: 2ch;
  font-size: var(--ds-t-2);
  font-variant-numeric: tabular-nums;
  text-align: center;
}
</style>
