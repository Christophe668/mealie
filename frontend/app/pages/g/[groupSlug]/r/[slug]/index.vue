<template>
  <div>
    <template v-if="recipe">
      <!-- Editing (and the ingredient parser) stays in the upstream page with all its editors. -->
      <RecipePage
        v-if="upstream"
        v-model="recipe"
      />
      <RecipeReadPage
        v-else
        v-model="recipe"
        @edit="enterEditor()"
      />
    </template>
    <p v-else class="recipe-status" role="status">
      <template v-if="notFound">
        <span class="recipe-status__title">{{ $t("recipe-read.not-found") }}</span>
        <NuxtLink :to="`/g/${route.params.groupSlug}/recipes`" class="recipe-status__link ds-focus">
          {{ $t("recipe-read.browse-recipes") }}
        </NuxtLink>
      </template>
      <span v-else class="ds-muted">{{ $t("recipe-read.loading") }}</span>
    </p>
  </div>
</template>

<script setup lang="ts">
import { whenever } from "@vueuse/core";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useAsyncKey } from "~/composables/use-utils";
import RecipePage from "~/components/Domain/Recipe/RecipePage/RecipePage.vue";
import RecipeReadPage from "~/components/Domain/Recipe/RecipeRead/RecipeReadPage.vue";
import { usePublicExploreApi } from "~/composables/api/api-client";
import { useRecipe } from "~/composables/recipes";
import { PageMode, usePageState } from "~/composables/recipe-page/shared-state";
import type { Recipe } from "~/lib/api/types/recipe";

const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();
const route = useRoute();
const title = ref(route.meta?.title as string || "");
useSeoMeta({ title });

const router = useRouter();
const slug = route.params.slug as string;

const recipe = ref<Recipe | null>(null);
/** A finished load that brought nothing back. */
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
  const groupSlug = computed(() => route.params.groupSlug as string || auth.user.value?.groupSlug || "");
  const api = usePublicExploreApi(groupSlug.value);
  const { data } = await useAsyncData(useAsyncKey(), async () => {
    const { data, error } = await api.explore.recipes.getOne(slug);
    if (error) {
      console.error("error loading recipe -> ", error);
      router.push({ path: `/g/${groupSlug.value}`, query: { redirect: route.fullPath } });
    }

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

/*
 * Read view vs upstream editor. RecipePage keeps its mode in the shared page state and clears that state
 * when it unmounts, so each editing session takes a fresh handle: set EDIT (or parsing) before RecipePage
 * mounts, and come back to the read view once RecipePage leaves both.
 */
const editorState = shallowRef<ReturnType<typeof usePageState> | null>(null);
const upstream = computed(() => !!editorState.value && (editorState.value.isEditMode.value || editorState.value.isParsing.value));

function enterEditor({ parse = false } = {}) {
  const state = usePageState(slug);
  if (parse) {
    state.toggleIsParsing(true);
  }
  else {
    state.setMode(PageMode.EDIT);
  }
  editorState.value = state;
}

watch(upstream, (value) => {
  if (value) {
    return;
  }
  editorState.value = null;
  // RecipePage unmounts before its own watcher can drop ?edit / ?parse. Skipped after a rename, where
  // RecipePage is already navigating to the new slug.
  const { edit, parse, ...query } = route.query;
  if ((edit || parse) && recipe.value?.slug === slug) {
    router.replace({ query });
  }
});

// Deep links from the create flow and the recipe card menus.
whenever(
  () => recipe.value,
  () => {
    if (!isOwnGroup.value) {
      return;
    }
    if (route.query.edit === "true") {
      enterEditor();
    }
    else if (route.query.parse === "true") {
      enterEditor({ parse: true });
    }
  },
  { once: true },
);

whenever(
  () => recipe.value,
  () => {
    if (recipe.value && recipe.value.name) {
      title.value = recipe.value.name;
    }
  },
);
</script>

<style scoped>
.recipe-status {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: calc(var(--ds-space) * 1.5);
  margin: calc(var(--ds-space) * 2) 0;
  font-size: var(--ds-t-3);
}

.recipe-status__title {
  font-weight: 600;
}

.recipe-status__link {
  color: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
