<template>
  <CookMode
    v-if="recipe"
    :recipe="recipe"
    :back-to="backTo"
    :scale="scale"
    :group-slug="groupSlug"
    :logged-in="isOwnGroup"
  />
  <div v-else class="ds-cook cook-page">
    <p class="cook-page__status" role="status">
      <template v-if="notFound">
        <span>{{ $t("recipe-read.not-found") }}</span>
        <NuxtLink :to="`/g/${groupSlug}/recipes`" class="cook-page__link ds-focus">
          {{ $t("recipe-read.browse-recipes") }}
        </NuxtLink>
      </template>
      <span v-else class="ds-muted">{{ $t("recipe-read.loading") }}</span>
    </p>
  </div>
</template>

<script setup lang="ts">
import CookMode from "~/components/Domain/Cook/CookMode.vue";
import { usePublicExploreApi } from "~/composables/api/api-client";
import { useRecipe } from "~/composables/recipes";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useAsyncKey } from "~/composables/use-utils";
import type { Recipe } from "~/lib/api/types/recipe";

// No shell: cook mode owns the whole screen.
definePageMeta({ layout: "blank" });

const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();
const route = useRoute();
const slug = route.params.slug as string;
const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");

const title = ref("");
useSeoMeta({ title });

// The read page's scale rides along, and goes back with you.
const queryScale = Number.parseFloat(String(route.query.scale ?? ""));
const scale = queryScale > 0 && Number.isFinite(queryScale) ? queryScale : 1;
const backTo = computed(() => `/g/${groupSlug.value}/r/${slug}${scale !== 1 ? `?scale=${scale}` : ""}`);

/* Same loading rule as the read page: members read through their API, anyone else through the public one. */
const recipe = ref<Recipe | null>(null);
const notFound = ref(false);

function loadRecipe() {
  const { recipe: data, loading } = useRecipe(slug);
  watch(data, (value) => {
    recipe.value = value;
  });
  watch(loading, (now, before) => {
    notFound.value = before && !now && !data.value;
  });
}

async function loadPublicRecipe() {
  const api = usePublicExploreApi(groupSlug.value);
  const { data } = await useAsyncData(useAsyncKey(), async () => {
    const { data } = await api.explore.recipes.getOne(slug);
    return data;
  });
  recipe.value = data.value;
  notFound.value = !data.value;
}

if (isOwnGroup.value) {
  loadRecipe();
}
else {
  onMounted(loadPublicRecipe);
}

watch(recipe, (value) => {
  if (value?.name) {
    title.value = value.name;
  }
});
</script>

<style scoped>
.cook-page {
  display: flex;
  min-height: 100vh;
  min-height: 100dvh;
  align-items: center;
  justify-content: center;
  padding: calc(var(--ds-space) * 4);
}

.cook-page__status {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: calc(var(--ds-space) * 1.5);
  margin: 0;
  font-size: var(--ds-t-3);
}

.cook-page__link {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
