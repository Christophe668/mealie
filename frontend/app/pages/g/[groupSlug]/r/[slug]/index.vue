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
    <p v-else-if="loadFailed" class="recipe-load" role="status">
      <span class="recipe-load__title">{{ $t("recipe-read.load-failed") }}</span>
      <button type="button" class="recipe-load__retry ds-focus" @click="loadRecipe()">
        {{ $t("recipe-read.try-again") }}
      </button>
    </p>
    <p v-else class="recipe-load ds-muted" role="status">
      {{ $t("recipe-read.loading") }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { whenever } from "@vueuse/core";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useAsyncKey } from "~/composables/use-utils";
import RecipePage from "~/components/Domain/Recipe/RecipePage/RecipePage.vue";
import RecipeReadPage from "~/components/Domain/Recipe/RecipeRead/RecipeReadPage.vue";
import { usePublicExploreApi, useUserApi } from "~/composables/api/api-client";
import { PageMode, usePageState } from "~/composables/recipe-page/shared-state";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe } from "~/lib/api/types/recipe";

const auth = useMealieAuth();
const { isOwnGroup } = useLoggedInState();
const route = useRoute();
const title = ref(route.meta?.title as string || "");
useSeoMeta({ title });

const router = useRouter();
const slug = route.params.slug as string;

const recipe = ref<NoUndefinedField<Recipe> | null>(null);
const loadFailed = ref(false);
const userApi = useUserApi();

async function loadRecipe() {
  loadFailed.value = false;
  const { data } = await userApi.recipes.getOne(slug);
  if (data) {
    recipe.value = data as NoUndefinedField<Recipe>;
  }
  else {
    loadFailed.value = true;
  }
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
  recipe.value = data.value as NoUndefinedField<Recipe> | null;
}

if (isOwnGroup.value) {
  onMounted(loadRecipe);
}
else {
  onMounted(loadPublicRecipe);
}

/*
 * Read view vs upstream editor. RecipePage keeps its mode in the shared page state and clears that
 * state when it unmounts, so each editing session takes a fresh handle on it: set EDIT (or parsing)
 * before RecipePage mounts, and come back to the read view once RecipePage leaves both.
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
  // RecipePage would drop ?edit / ?parse itself, but it unmounts before its watcher runs. Skipped after a
  // rename, where RecipePage is already navigating to the new slug.
  const { edit, parse, ...query } = route.query;
  if ((edit || parse) && recipe.value?.slug === slug) {
    router.replace({ query });
  }
});

// Deep links from the create flow and the recipe card menus: ?edit=true / ?parse=true.
whenever(
  () => recipe.value,
  () => {
    if (editorState.value || !isOwnGroup.value) {
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
.recipe-load {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  margin: calc(var(--ds-space) * 2) 0;
  font-size: var(--ds-t-3);
}

.recipe-load__title {
  font-weight: 600;
}

.recipe-load__retry {
  padding: calc(var(--ds-space) * 0.75) calc(var(--ds-space) * 1.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  font: inherit;
  cursor: pointer;
}
</style>
