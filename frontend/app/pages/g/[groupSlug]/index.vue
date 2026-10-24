<template>
  <div v-if="!redirecting" class="home">
    <div class="home__top">
      <HomeTonightBoard
        :entry="tonight"
        :loading="loading"
        :group-slug="groupSlug"
        :last-made="tonightLastMade"
        :has-connection="hasConnection"
        :planner-to="plannerTo"
        :today="today"
        @swap="swapOpen = true"
      />
      <HomeSideCards
        :lunch="lunch"
        :open-list="openList"
        :loading="loading"
        :group-slug="groupSlug"
        :planner-to="plannerTo"
      />
    </div>

    <HomeWeekStrip
      :days="week"
      :today="today"
      :group-slug="groupSlug"
      :planner-to="plannerTo"
    />

    <HomeRecipeShelf
      :title="$t('home-today.make-again')"
      :recipes="makeAgain"
      :loading="loading"
      :group-slug="groupSlug"
      :fact="makeAgainFact"
      :empty-text="$t('home-today.make-again-empty')"
    />

    <HomeRecipeShelf
      :title="$t('home-today.recently-added')"
      :recipes="recent"
      :loading="loading"
      :group-slug="groupSlug"
      :fact="duration"
      :action="{ label: $t('home-today.see-all'), to: recipesPath }"
      :empty-text="$t('home-today.recently-added-empty')"
      :empty-action="{ label: $t('home-today.add-a-recipe'), to: `/g/${groupSlug}/r/create/url` }"
    />

    <GroupMealPlanEntryDialog
      v-model="swapOpen"
      :entry="tonight"
      :date="today"
      @create="saveEntry"
      @update="saveEntry"
    />
  </div>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import HomeRecipeShelf from "~/components/Domain/Home/HomeRecipeShelf.vue";
import HomeSideCards from "~/components/Domain/Home/HomeSideCards.vue";
import HomeTonightBoard from "~/components/Domain/Home/HomeTonightBoard.vue";
import HomeWeekStrip from "~/components/Domain/Home/HomeWeekStrip.vue";
import GroupMealPlanEntryDialog from "~/components/Domain/Household/GroupMealPlanEntryDialog.vue";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { useToday, useTodayFormat } from "~/composables/use-today";
import type { RecipeSummary } from "~/lib/api/types/recipe";

const PLANNER_PATH = "/household/mealplan/planner/view";
/** Query keys the recipe explorer understands; old links put them on the group index. */
const EXPLORER_QUERY_KEYS = [
  "search", "auto", "orderBy", "orderDirection",
  "categories", "tags", "tools", "foods", "households",
  "requireAllCategories", "requireAllTags", "requireAllTools", "requireAllFoods",
];

const route = useRoute();
const i18n = useI18n();
const { isOwnGroup } = useLoggedInState();

const groupSlug = computed(() => route.params.groupSlug as string);
const recipesPath = computed(() => `/g/${groupSlug.value}/recipes`);

// Home is the signed-in household's day. Visitors of a public group, and explorer links aimed at the
// old group index, go to the recipe explorer instead.
const redirecting = !isOwnGroup.value || Object.keys(route.query).some(key => EXPLORER_QUERY_KEYS.includes(key));
if (redirecting) {
  navigateTo({ path: recipesPath.value, query: route.query }, { replace: true });
}

const {
  today,
  tonight,
  tonightLastMade,
  lunch,
  week,
  weekStart,
  openList,
  makeAgain,
  recent,
  lastMade,
  hasConnection,
  loading,
  refresh,
  saveEntry,
} = useToday();
const { duration, lastMadeLabel } = useTodayFormat();

const plannerTo = computed(() => `${PLANNER_PATH}?start=${format(weekStart.value, "yyyy-MM-dd")}`);

function makeAgainFact(recipe: RecipeSummary) {
  return recipe.slug ? lastMadeLabel(lastMade.value[recipe.slug], today.value) : "";
}

const swapOpen = ref(false);

const dateTitle = computed(() =>
  // "Saturday 24 October" rather than the locale's comma-joined form.
  today.value
    .toLocaleDateString(i18n.locale.value, { weekday: "long", day: "numeric", month: "long" })
    .replace(/,/g, ""),
);
useAppShellTitle(dateTitle);
useSeoMeta({ title: () => i18n.t("app-shell.today") });

onMounted(() => {
  if (!redirecting) {
    refresh();
  }
});
</script>

<style scoped>
.home__top {
  display: grid;
  grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
  gap: calc(var(--ds-space) * 3);
  align-items: stretch;
}

@media (max-width: 1023px) {
  .home__top {
    grid-template-columns: minmax(0, 1fr);
    gap: calc(var(--ds-space) * 2);
  }
}
</style>
