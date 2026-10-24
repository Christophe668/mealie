<template>
  <section :aria-label="title">
    <DsSectionTitle :title="title" :action="recipes.length ? action : undefined" />

    <ul v-if="loading" class="home-shelf" aria-hidden="true">
      <li v-for="n in 4" :key="n" class="home-shelf__skeleton" />
    </ul>

    <ul v-else-if="recipes.length" class="home-shelf">
      <li v-for="recipe in recipes" :key="recipe.id ?? recipe.slug">
        <DsCard :to="`/g/${groupSlug}/r/${recipe.slug}`" :padded="false" class="home-shelf__card">
          <template #media>
            <span class="home-shelf__media">
              <img
                v-if="recipe.id && recipe.image && !failed[recipe.id]"
                :src="recipeSmallImage(recipe.id, recipe.image)"
                alt=""
                loading="lazy"
                @error="failed[recipe.id] = true"
              >
              <DsIcon v-else name="silverwareForkKnife" :size="28" class="home-shelf__placeholder" />
            </span>
          </template>
          <span class="home-shelf__title">{{ recipe.name }}</span>
          <span v-if="fact(recipe)" class="home-shelf__fact ds-muted">{{ fact(recipe) }}</span>
        </DsCard>
      </li>
    </ul>

    <DsEmpty v-else :title="emptyText" :action="emptyAction" />
  </section>
</template>

<script setup lang="ts">
import DsCard from "~/components/Design/DsCard.vue";
import DsEmpty from "~/components/Design/DsEmpty.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import DsSectionTitle from "~/components/Design/DsSectionTitle.vue";
import { useStaticRoutes } from "~/composables/api";
import type { RecipeSummary } from "~/lib/api/types/recipe";

withDefaults(defineProps<{
  title: string;
  recipes: RecipeSummary[];
  loading: boolean;
  groupSlug: string;
  /** The card footer's single fact; return "" to show none. */
  fact?: (recipe: RecipeSummary) => string;
  action?: { label: string; to: string };
  emptyText: string;
  emptyAction?: { label: string; to: string };
}>(), {
  fact: () => "",
  action: undefined,
  emptyAction: undefined,
});

const { recipeSmallImage } = useStaticRoutes();
const failed = reactive<Record<string, boolean>>({});
</script>

<style scoped>
.home-shelf {
  display: grid;
  grid-auto-columns: 220px;
  grid-auto-flow: column;
  gap: calc(var(--ds-space) * 2);
  /* Room for the cards' focus ring inside the scroller's clip box, cancelled by the negative margin. */
  margin: calc(var(--ds-space) * -0.5);
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.25);
  overflow-x: auto;
  scroll-padding-inline: calc(var(--ds-space) * 0.5);
  list-style: none;
  scroll-snap-type: x proximity;
}

.home-shelf > li {
  display: flex;
  min-width: 0;
  scroll-snap-align: start;
}

.home-shelf__card {
  flex: 1;
}

.home-shelf__media {
  position: relative;
  display: grid;
  height: 130px;
  overflow: hidden;
  place-items: center;
  background: var(--ds-bg);
  color: var(--ds-text-2);
}

.home-shelf__media img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.home-shelf__placeholder {
  opacity: 0.6;
}

.home-shelf__title {
  display: -webkit-box;
  margin: calc(var(--ds-space) * 1.5) 0 calc(var(--ds-space) * 0.5);
  padding: 0 calc(var(--ds-space) * 1.75);
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-weight: 600;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.home-shelf__fact {
  display: block;
  padding: 0 calc(var(--ds-space) * 1.75) calc(var(--ds-space) * 1.75);
  font-size: var(--ds-t-1);
}

.home-shelf__title:last-child {
  margin-bottom: calc(var(--ds-space) * 1.75);
}

.home-shelf__skeleton {
  height: 200px;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
}

@media (max-width: 1023px) {
  .home-shelf {
    grid-auto-columns: 180px;
    margin-inline: calc(var(--ds-space) * -2);
    padding-inline: calc(var(--ds-space) * 2);
    scroll-padding-inline: calc(var(--ds-space) * 2);
    scrollbar-width: none;
  }
}
</style>
