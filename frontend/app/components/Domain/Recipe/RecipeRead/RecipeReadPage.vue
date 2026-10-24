<template>
  <article class="read" :aria-labelledby="titleId">
    <div class="read__layout d-print-none">
      <aside ref="aside" class="read__aside" :style="asideStyle">
        <RecipeReadHero class="read__hero" :name="recipe.name || ''" :image-url="imageUrl" />
        <RecipeReadFacts
          v-model:scale="scale"
          class="read__facts"
          :recipe="recipe"
          :cook-to="cookTo"
          :last-made="lastMade"
        />
        <RecipeReadIngredients
          v-if="recipe.recipeIngredient.length"
          class="read__ingredients"
          :ingredients="recipe.recipeIngredient"
          :scale="scale"
          :recipe-slug="recipe.slug"
          :collapsible="isMobile"
        />
      </aside>

      <div class="read__main">
        <header class="read__header">
          <h1 :id="titleId" class="read__title ds-display">
            {{ recipe.name }}
          </h1>
          <SafeMarkdown v-if="recipe.description" class="read__description ds-body ds-muted" :source="recipe.description" />
        </header>

        <RecipeReadActions
          class="read__actions"
          :logged-in="isOwnGroup"
          :can-edit="canEditRecipe"
          :can-delete="canDelete"
          @edit="emit('edit')"
          @plan="planDialog = true"
          @list="openShoppingListDialog"
          @share="share"
          @print="print"
          @delete="deleteDialog = true"
        />

        <RecipeReadSteps class="read__steps" :steps="recipe.recipeInstructions" />

        <section v-if="notes.length" class="read__notes read__block" :aria-labelledby="`${titleId}-notes`">
          <h2 :id="`${titleId}-notes`" class="read__block-title">
            {{ $t("recipe-read.notes") }}
          </h2>
          <div v-for="(note, index) in notes" :key="index" class="read__note">
            <h3 v-if="note.title" class="read__note-title">
              {{ note.title }}
            </h3>
            <SafeMarkdown class="ds-body" :source="note.text" />
          </div>
        </section>

        <div v-if="organizers.length" class="read__organizers read__block">
          <section v-for="org in organizers" :key="org.key" class="read__organizer" :aria-labelledby="`${titleId}-${org.key}`">
            <h2 :id="`${titleId}-${org.key}`" class="read__organizer-title">
              {{ org.label }}
            </h2>
            <ul class="read__chips">
              <li v-for="item in org.items" :key="item.id">
                <NuxtLink :to="item.to" class="read__chip-link ds-focus">
                  <DsChip>{{ item.name }}</DsChip>
                </NuxtLink>
              </li>
            </ul>
          </section>
        </div>

        <RecipePageComments
          v-if="!disableComments"
          v-model="recipe"
          class="read__comments read__block"
        />
      </div>

      <!-- Mobile's one accent. Last in the flow so it stays pinned above the tab bar while you read. -->
      <div v-if="cookTo" class="read__cook-bar ds-mobile-only">
        <DsButton size="lg" block :to="cookTo">
          {{ $t("recipe-read.start-cooking") }}
        </DsButton>
      </div>
    </div>

    <MealPlanAddRecipeDialog
      v-if="isOwnGroup"
      v-model="planDialog"
      :recipe-id="recipe.id"
      :recipe-scale="scale"
    />
    <RecipeDialogAddToShoppingList
      v-if="isOwnGroup && shoppingLists"
      v-model="shoppingListDialog"
      :recipes="[{ ...recipe, scale }]"
      :shopping-lists="shoppingLists"
      @list-created="addShoppingList"
    />
    <RecipeDialogShare v-if="isOwnGroup" v-model="shareDialog" :recipe-id="recipe.id" :name="recipe.name" />
    <BaseDialog
      v-model="deleteDialog"
      bottom-sheet
      :title="$t('recipe-read.delete-title')"
      color="error"
      :icon="$globals.icons.alertCircle"
      can-confirm
      @confirm="deleteRecipe"
    >
      <v-card-text>
        {{ isAdminAndNotOwner ? $t("recipe.admin-delete-confirmation") : $t("recipe.delete-confirmation") }}
      </v-card-text>
    </BaseDialog>
    <RecipePrintContainer :recipe="recipe" :scale="scale" />
  </article>
</template>

<script setup lang="ts">
import { useId, useTemplateRef } from "vue";
import { useClipboard, useElementSize, useMediaQuery, useShare, useWindowSize } from "@vueuse/core";
import RecipeReadActions from "./RecipeReadActions.vue";
import RecipeReadFacts from "./RecipeReadFacts.vue";
import RecipeReadHero from "./RecipeReadHero.vue";
import RecipeReadIngredients from "./RecipeReadIngredients.vue";
import RecipeReadSteps from "./RecipeReadSteps.vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsChip from "~/components/Design/DsChip.vue";
import SafeMarkdown from "~/components/global/SafeMarkdown.vue";
import MealPlanAddRecipeDialog from "~/components/Domain/Mealplan/MealPlanAddRecipeDialog.vue";
import RecipeDialogAddToShoppingList from "~/components/Domain/Recipe/RecipeDialogAddToShoppingList.vue";
import RecipeDialogShare from "~/components/Domain/Recipe/RecipeDialogShare.vue";
import RecipePrintContainer from "~/components/Domain/Recipe/RecipePrintContainer.vue";
import RecipePageComments from "~/components/Domain/Recipe/RecipePage/RecipePageParts/RecipePageComments.vue";
import { useStaticRoutes, useUserApi } from "~/composables/api";
import { useRecipePermissions } from "~/composables/recipes";
import { useAddToShoppingListDialog } from "~/composables/shopping-list-page/use-add-to-shopping-list-dialog";
import { useGroupSelf } from "~/composables/use-groups";
import { useHouseholdSelf } from "~/composables/use-households";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { alert } from "~/composables/use-toast";
import type { HouseholdSummary } from "~/lib/api/types/household";
import type { NoUndefinedField } from "~/lib/api/types/non-generated";
import type { Recipe } from "~/lib/api/types/recipe";
import { isRecipeFullyPublic } from "~/lib/recipe/recipe-visibility";

const recipe = defineModel<NoUndefinedField<Recipe>>({ required: true });
const emit = defineEmits<{ (e: "edit"): void }>();

const i18n = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useMealieAuth();
const api = useUserApi();
const { isOwnGroup } = useLoggedInState();
const { household } = useHouseholdSelf();
const { group, actions: groupActions } = useGroupSelf();
const { recipeImage } = useStaticRoutes();

const titleId = useId();
const isMobile = useMediaQuery("(max-width: 1023px)");

/*
 * Sticky left column. When it is taller than the viewport, a fixed 24 px top would hide its end until the
 * page ends, so the offset goes negative: the column scrolls with the page and pins once its bottom shows.
 */
const STICKY_GAP = 24;
const { height: asideHeight } = useElementSize(useTemplateRef<HTMLElement>("aside"), undefined, { box: "border-box" });
const { height: windowHeight } = useWindowSize();
const asideStyle = computed(() => ({
  top: `${Math.min(STICKY_GAP, windowHeight.value - asideHeight.value - STICKY_GAP)}px`,
}));

const groupSlug = computed(() => (route.params.groupSlug as string) || auth.user.value?.groupSlug || "");
const cookTo = computed(() => (groupSlug.value && recipe.value.slug ? `/g/${groupSlug.value}/r/${recipe.value.slug}/cook` : ""));
const imageUrl = computed(() => (recipe.value.id && recipe.value.image ? recipeImage(recipe.value.id, recipe.value.image) : ""));

// Opened from a meal plan entry, the recipe starts at that entry's scale.
const initialScale = Number.parseFloat(String(route.query.scale ?? ""));
const scale = ref(initialScale > 0 && Number.isFinite(initialScale) ? initialScale : 1);

/* Permissions: the recipe may belong to another household in the group. */
const recipeHousehold = ref<HouseholdSummary | undefined>();
watch(
  [() => recipe.value.householdId, () => household.value?.id],
  async ([householdId]) => {
    if (!isOwnGroup.value || !householdId) {
      recipeHousehold.value = undefined;
      return;
    }
    if (householdId === household.value?.id) {
      recipeHousehold.value = household.value ?? undefined;
      return;
    }
    if (householdId === recipeHousehold.value?.id) {
      return;
    }
    const { data } = await api.households.getOne(householdId);
    recipeHousehold.value = data ?? undefined;
  },
  { immediate: true },
);
const { canEditRecipe } = useRecipePermissions(recipe.value, recipeHousehold, auth.user.value);
const canDelete = computed(() => {
  const user = auth.user.value;
  return isOwnGroup.value && !!user && (!!user.admin || user.id === recipe.value.userId);
});
const isAdminAndNotOwner = computed(() => !!auth.user.value?.admin && auth.user.value.id !== recipe.value.userId);

const disableComments = computed(
  () => !!(household.value?.preferences?.recipeDisableComments || recipe.value.settings?.disableComments),
);

/* Last made: per household, so only signed-in members of the group have one. */
const lastMade = ref<string | null>(null);
watch(
  () => recipe.value.slug,
  async (slug) => {
    lastMade.value = null;
    if (!isOwnGroup.value || !slug) {
      return;
    }
    const { data } = await api.households.getCurrentUserHouseholdRecipe(slug);
    if (slug === recipe.value.slug) {
      lastMade.value = data?.lastMade ?? null;
    }
  },
  { immediate: true },
);

const notes = computed(() => recipe.value.notes.filter(note => note.title?.trim() || note.text?.trim()));

const organizers = computed(() => {
  const base = `/g/${groupSlug.value}/recipes`;
  return [
    { key: "categories", label: i18n.t("recipe-read.categories"), items: recipe.value.recipeCategory },
    { key: "tags", label: i18n.t("recipe-read.tags"), items: recipe.value.tags },
    { key: "tools", label: i18n.t("recipe-read.tools"), items: recipe.value.tools },
  ]
    .filter(group => group.items.length)
    .map(group => ({
      key: group.key,
      label: group.label,
      items: group.items
        .filter(item => item.id)
        .map(item => ({ id: item.id as string, name: item.name, to: `${base}?${group.key}=${item.id}` })),
    }));
});

/* Actions: the same dialogs and calls the upstream recipe page uses. */
const planDialog = ref(false);
const shareDialog = ref(false);
const deleteDialog = ref(false);
const { open: shoppingListDialog, shoppingLists, getShoppingLists, addShoppingList } = useAddToShoppingListDialog();

async function openShoppingListDialog() {
  await getShoppingLists();
  shoppingListDialog.value = true;
}

const { share: nativeShare, isSupported: shareSupported } = useShare();
const { copy, copied, isSupported: clipboardSupported } = useClipboard({ legacy: true });

async function share() {
  if (!group.value) {
    await groupActions.refresh();
  }
  // A fully public recipe shares its plain link; anything else needs a share token, which the dialog makes.
  if (!isRecipeFullyPublic(recipe.value, group.value, recipeHousehold.value)) {
    shareDialog.value = true;
    return;
  }
  const url = `${window.location.origin}/g/${groupSlug.value}/r/${recipe.value.slug}`;
  if (shareSupported.value) {
    await nativeShare({ title: recipe.value.name || "", url });
    return;
  }
  if (!clipboardSupported.value) {
    alert.error(i18n.t("general.clipboard-not-supported"));
    return;
  }
  await copy(url);
  alert[copied.value ? "success" : "error"](
    i18n.t(copied.value ? "recipe-share.recipe-link-copied-message" : "general.clipboard-copy-failure"),
  );
}

function print() {
  window.print();
}

async function deleteRecipe() {
  const { data } = await api.recipes.deleteOne(recipe.value.slug);
  if (data?.slug) {
    router.push(`/g/${groupSlug.value}`);
  }
}
</script>

<style scoped>
.read__layout {
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  gap: calc(var(--ds-space) * 5);
  align-items: start;
}

/* The shell's top bar scrolls away, so the column's 24 px offset (set inline) never overlaps it. */
.read__aside {
  position: sticky;
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
}

.read__main {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
}

.read__title {
  margin: 0;
  overflow-wrap: anywhere;
}

.read__description {
  margin-top: calc(var(--ds-space) * 1.5);
}

.read__description :deep(p) {
  margin: 0;
}

.read__block {
  margin-top: calc(var(--ds-space) * 2);
}

.read__block-title {
  margin: 0 0 calc(var(--ds-space) * 1.5);
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.read__note + .read__note {
  margin-top: calc(var(--ds-space) * 2);
}

.read__note-title {
  margin: 0 0 calc(var(--ds-space) * 0.5);
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.read__note :deep(p) {
  margin: 0;
}

.read__organizers {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.read__organizer-title {
  margin: 0 0 var(--ds-space);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
}

.read__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin: 0;
  padding: 0;
  list-style: none;
}

.read__chip-link {
  display: inline-flex;
  border-radius: var(--ds-radius-ctl);
  text-decoration: none;
}

.read__chip-link:hover :deep(.ds-chip) {
  border-color: var(--ds-text-2);
  color: var(--ds-text);
}

@media (max-width: 1023px) {
  /* One column; the two desktop columns dissolve so their parts can interleave. */
  .read__layout {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: calc(var(--ds-space) * 2.5);
  }

  .read__aside,
  .read__main {
    display: contents;
  }

  .read__hero {
    order: 1;
  }
  .read__header {
    order: 2;
  }
  .read__facts {
    order: 3;
  }
  .read__actions {
    order: 4;
  }
  .read__ingredients {
    order: 5;
  }
  .read__steps {
    order: 6;
  }
  .read__notes {
    order: 7;
  }
  .read__organizers {
    order: 8;
  }
  .read__comments {
    order: 9;
  }
  .read__cook-bar {
    order: 10;
  }

  .read__title {
    font-size: var(--ds-t-6);
  }

  .read__block {
    margin-top: 0;
  }

  /* Sits 12 px above the floating tab bar (12 px inset + its ~70 px height). */
  .read__cook-bar {
    position: sticky;
    bottom: calc(var(--ds-space) * 12 + env(safe-area-inset-bottom));
    z-index: 2;
  }

  .read__cook-bar :deep(.ds-btn) {
    box-shadow: var(--ds-shadow-float);
  }
}
</style>
