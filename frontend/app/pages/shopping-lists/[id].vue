<template>
  <div class="shop-page">
    <div class="shop-page__bar">
      <NuxtLink to="/shopping-lists?disableRedirect=true" class="shop-page__back ds-focus">
        <DsIcon name="chevronLeft" :size="20" />
        {{ $t("shop.all-lists") }}
      </NuxtLink>
      <!-- The screen's one saffron element: how much is left to buy. -->
      <span v-if="shoppingList && open > 0" class="shop-page__badge">
        {{ $t("shop.to-buy", { count: open }) }}
      </span>
      <AppShellMenu
        v-if="shoppingList"
        class="shop-page__more"
        :items="moreItems"
        :label="$t('shop.list-actions')"
        :trigger-label="$t('shop.list-actions')"
        trigger-class="shop-page__icon-btn ds-focus"
        placement="bottom-end"
      >
        <template #trigger>
          <DsIcon name="dotsVertical" :size="22" />
        </template>
      </AppShellMenu>
    </div>

    <!-- Polite announcements: loading, then the open count after every tick, un-tick or add. -->
    <p class="shop-page__sr" role="status">
      {{ liveStatus }}
    </p>
    <p v-if="isOffline" class="shop-page__hint" role="status">
      {{ $t("shop.offline") }}
    </p>
    <p v-if="failed" class="shop-page__hint shop-page__hint--error" role="alert">
      <span class="shop-page__hint-title">{{ $t("shop.load-failed") }}</span>
      <button type="button" class="shop-page__retry ds-focus" @click="retry">
        {{ $t("shop.try-again") }}
      </button>
    </p>

    <ShopList
      v-if="shoppingList"
      :list="shoppingList"
      :by-label="byLabel"
      :putting="putting"
      @toggle="toggle"
      @edit="openEditor"
      @add="add"
      @clear-bought="openDeleteChecked"
      @put-away="putAway"
    />

    <!-- Recipes whose ingredients are on the list: upstream's controls to add or take a recipe off again. -->
    <section v-if="shoppingList && recipeList.length" class="shop-page__recipes">
      <DsSectionTitle :title="$t('shop.recipes-on-list')" />
      <RecipeList :recipes="recipeList" show-description :disabled="isOffline">
        <template
          v-for="(recipe, index) in recipeList"
          #[`actions-${recipe.id}`]
          :key="'item-actions-decrease' + recipe.id"
        >
          <v-list-item-action>
            <v-btn
              icon
              flat
              class="bg-transparent"
              :disabled="isOffline"
              :aria-label="$t('shop.recipe-less', { recipe: recipe.name })"
              @click.prevent="removeRecipeReferenceToList(recipe.id!)"
            >
              <v-icon>{{ $globals.icons.minus }}</v-icon>
            </v-btn>
          </v-list-item-action>
          <div class="pl-3">
            {{ shoppingList.recipeReferences?.[index]?.recipeQuantity }}
          </div>
          <v-list-item-action>
            <v-btn
              icon
              flat
              class="bg-transparent"
              :disabled="isOffline"
              :aria-label="$t('shop.recipe-more', { recipe: recipe.name })"
              @click.prevent="addRecipeReferenceToList(recipe.id!)"
            >
              <v-icon>{{ $globals.icons.createAlt }}</v-icon>
            </v-btn>
          </v-list-item-action>
        </template>
      </RecipeList>
    </section>

    <KeepScreenOn v-if="keepAwake" />

    <!-- Item editor: upstream's editor on a copy, so a background refresh never overwrites typing. -->
    <v-dialog v-model="editor.open" max-width="560" :aria-label="$t('shop.edit-dialog')">
      <ShoppingListItemEditor
        v-if="editor.item"
        v-model="editor.item"
        :labels="allLabels || []"
        :units="allUnits || []"
        :foods="allFoods || []"
        @save="saveEditor"
        @cancel="editor.open = false"
        @delete="deleteEditor"
      />
    </v-dialog>

    <BaseDialog
      v-model="state.checkAllDialog"
      bottom-sheet
      :title="$t('general.confirm')"
      :icon="$globals.icons.checkboxMultipleMarkedOutline"
      can-confirm
      @confirm="checkAll"
    >
      <v-card-text>
        {{ $t('shopping-list.are-you-sure-you-want-to-check-all-items') }}
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-model="state.uncheckAllDialog"
      bottom-sheet
      :title="$t('general.confirm')"
      :icon="$globals.icons.checkboxMultipleBlankOutline"
      can-confirm
      @confirm="uncheckAll"
    >
      <v-card-text>
        {{ $t('shopping-list.are-you-sure-you-want-to-uncheck-all-items') }}
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-model="state.deleteCheckedDialog"
      bottom-sheet
      :title="$t('general.confirm')"
      :icon="$globals.icons.alertCircle"
      can-confirm
      @confirm="deleteChecked"
    >
      <v-card-text>
        {{ $t('shopping-list.are-you-sure-you-want-to-delete-checked-items') }}
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-model="reorderLabelsDialog"
      :icon="$globals.icons.tagArrowUp"
      :title="$t('shopping-list.reorder-labels')"
      :submit-icon="$globals.icons.save"
      :submit-text="$t('general.save')"
      can-submit
      @submit="saveLabelOrder"
      @close="cancelLabelOrder"
    >
      <v-card height="fit-content" max-height="70vh" style="overflow-y: auto;">
        <VueDraggable
          v-if="localLabels"
          v-model="localLabels"
          handle=".handle"
          :delay="250"
          :delay-on-touch-only="true"
          class="my-2"
          @update:model-value="updateLabelOrder"
        >
          <div v-for="(labelSetting, index) in localLabels" :key="labelSetting.id">
            <MultiPurposeLabelSection v-model="localLabels[index]" use-color />
          </div>
        </VueDraggable>
      </v-card>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { VueDraggable } from "vue-draggable-plus";
import DsIcon from "~/components/Design/DsIcon.vue";
import DsSectionTitle from "~/components/Design/DsSectionTitle.vue";
import ShopList from "~/components/Domain/Shop/ShopList.vue";
import RecipeList from "~/components/Domain/Recipe/RecipeList.vue";
import MultiPurposeLabelSection from "~/components/Domain/ShoppingList/MultiPurposeLabelSection.vue";
import ShoppingListItemEditor from "~/components/Domain/ShoppingList/ShoppingListItemEditor.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import { useUserApi } from "~/composables/api";
import { useShoppingListPage } from "~/composables/shopping-list-page/use-shopping-list-page";
import { resolveFood } from "~/composables/shopping-list-page/use-shopping-list-item-editor";
import { useLabelStore, useUnitStore, useFoodStore } from "~/composables/store";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { openCount, toByLabel } from "~/composables/use-shop";
import { alert, alertUnreportedError } from "~/composables/use-toast";
import { useUserExperiencePreferences } from "~/composables/use-users/preferences";
import { useWakeLock } from "~/composables/use-wake-lock";
import type { ShoppingListItemOut } from "~/lib/api/types/household";
import type { AppShellMenuItem } from "~/types/application-types";

definePageMeta({
  middleware: ["auth"],
});

const i18n = useI18n();
const route = useRoute();
const router = useRouter();
const id = route.params.id as string;
const api = useUserApi();

// The upstream composable stays the single source of truth for items, label grouping and the offline queue.
const shoppingListPage = useShoppingListPage(id);
const { store: allLabels } = useLabelStore();
const { store: allUnits } = useUnitStore();
const { store: allFoods } = useFoodStore();

const {
  shoppingList,
  state,
  loadingCounter,
  isOffline,
  itemsByLabel,
  recipeList,
  createListItemData,
  createListItem,
  saveListItem,
  deleteListItem,
  checkAll,
  uncheckAll,
  deleteChecked,
  openCheckAll,
  openUncheckAll,
  openDeleteChecked,
  copyListItems,
  reorderLabelsDialog,
  localLabels,
  toggleReorderLabelsDialog,
  saveLabelOrder,
  cancelLabelOrder,
  updateLabelOrder,
  removeRecipeReferenceToList,
  addRecipeReferenceToList,
  refresh,
  hasQueuedChanges,
} = shoppingListPage;

const byLabel = computed(() => toByLabel(itemsByLabel.value, shoppingList.value));
const open = computed(() => openCount(shoppingList.value));

useAppShellTitle(() => shoppingList.value?.name || i18n.t("shop.lists-title"));
useSeoMeta({ title: () => shoppingList.value?.name || i18n.t("shopping-list.shopping-list") });

// =====================================================
// Loading and failure. The composable swallows fetch errors and leaves the list null, so a fetch that
// finishes (the counter drops back to 0) without a list is a failed load.

const settled = ref(false);
watch(loadingCounter, (count, previous) => {
  if (count === 0 && previous > 0) {
    settled.value = true;
  }
});
const loading = computed(() => !shoppingList.value && !settled.value);
const failed = computed(() => !shoppingList.value && settled.value);

const liveStatus = computed(() => {
  if (loading.value) {
    return i18n.t("shop.loading");
  }
  if (!shoppingList.value) {
    return "";
  }
  return open.value ? i18n.t("shop.to-buy", { count: open.value }) : i18n.t("shop.nothing-to-buy");
});

function retry() {
  settled.value = false;
  refresh();
}

// =====================================================
// Items

/** Optimistic, through the composable, as upstream does; ticking off offers an undo. */
function toggle(item: ShoppingListItemOut) {
  const updated = { ...item, checked: !item.checked };
  saveListItem(updated);
  if (updated.checked) {
    alert.info(
      i18n.t("shop.item-bought", { item: item.food?.name || item.note || i18n.t("recipe.ingredient") }),
      undefined,
      {
        timeout: 4000,
        action: {
          message: i18n.t("general.undo"),
          // Flip only `checked` on the item as it is now, so an edit made since the tick survives the undo.
          onClick: () => {
            const current = shoppingList.value?.listItems?.find(i => i.id === item.id);
            if (current?.checked) {
              saveListItem({ ...current, checked: false });
            }
          },
        },
      },
    );
  }
}

/**
 * Same resolution as upstream's quick add: an exact food match becomes that food (and takes its label),
 * anything else is kept verbatim as a note. Upstream does not parse quantities from the text.
 */
function add(text: string) {
  const food = resolveFood(text, allFoods.value || []);
  const draft = createListItemData.value;
  draft.food = food;
  draft.foodId = food?.id;
  draft.label = food?.label;
  draft.labelId = food?.labelId;
  draft.note = food ? "" : text;
  draft.quantity ||= 0;
  createListItem();
}

const editor = reactive({ open: false, item: null as ShoppingListItemOut | null, source: null as ShoppingListItemOut | null });

function openEditor(item: ShoppingListItemOut) {
  editor.source = item;
  editor.item = { ...item };
  editor.open = true;
}

function saveEditor() {
  if (editor.item) {
    saveListItem(editor.item);
  }
  editor.open = false;
}

function deleteEditor() {
  if (editor.source) {
    deleteListItem(editor.source);
  }
  editor.open = false;
}

// =====================================================
// Put away: every bought item goes into the pantry and off the list, then the list reloads.

const putting = ref(false);

async function putAway() {
  if (putting.value) {
    return;
  }
  putting.value = true;
  try {
    // A tick is only queued locally until the next refresh or poll; send the queue first so the server
    // sees what is on screen as bought.
    await refresh();
    if (hasQueuedChanges.value) {
      // The flush could not reach the server; putting away now would move a stale set of items.
      alert.error(i18n.t("shop.put-away-unsynced"));
      return;
    }
    const { data, error } = await api.householdPantry.putAway(id, null);
    if (!data) {
      // The list is left as it is; nothing was moved.
      alertUnreportedError(error, i18n.t("shop.put-away-failed"));
      return;
    }
    const count = data.created.length + data.merged.length;
    alert.info(i18n.t("shop.put-away-done", { count }, count), undefined, {
      timeout: 6000,
      action: { message: i18n.t("shop.open-pantry"), onClick: () => router.push("/household/pantry") },
    });
    // Stay busy until the reloaded list no longer shows the items, so a second press cannot repeat it.
    await refresh();
  }
  finally {
    putting.value = false;
  }
}

// =====================================================
// List actions

const preferences = useUserExperiencePreferences();
const wakeLockSupported = import.meta.client && "wakeLock" in navigator;
const keepAwake = computed(() => wakeLockSupported && preferences.value.lockScreen);

/** Holds a screen wake lock while mounted (the same lock cook mode uses). */
const KeepScreenOn = defineComponent({
  name: "KeepScreenOn",
  setup() {
    useWakeLock();
    return () => null;
  },
});

const moreItems = computed<AppShellMenuItem[]>(() => [
  { key: "check-all", label: i18n.t("shop.mark-all-bought"), icon: "checkboxMultipleMarkedOutline", onSelect: openCheckAll },
  { key: "uncheck-all", label: i18n.t("shop.mark-all-not-bought"), icon: "checkboxMultipleBlankOutline", onSelect: openUncheckAll },
  { key: "copy-text", label: i18n.t("shop.copy-text"), icon: "contentCopy", onSelect: () => copyListItems("plain"), dividerBefore: true },
  { key: "copy-markdown", label: i18n.t("shop.copy-markdown"), icon: "contentCopy", onSelect: () => copyListItems("markdown") },
  { key: "reorder", label: i18n.t("shop.reorder-aisles"), icon: "tagArrowUp", onSelect: toggleReorderLabelsDialog, dividerBefore: true },
  { key: "labels", label: i18n.t("shop.manage-labels"), icon: "tags", onSelect: () => router.push("/group/data/labels") },
  ...(wakeLockSupported
    ? [{
        key: "awake",
        label: i18n.t("shop.keep-awake"),
        icon: "weatherSunny" as const,
        checked: preferences.value.lockScreen,
        dividerBefore: true,
        onSelect: () => (preferences.value.lockScreen = !preferences.value.lockScreen),
      }]
    : []),
]);
</script>

<style scoped>
.shop-page {
  max-width: 760px;
}

.shop-page__bar {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  margin-bottom: calc(var(--ds-space) * 2);
}

.shop-page__back {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.5);
  min-height: 44px;
  margin-left: calc(var(--ds-space) * -0.5);
  padding: 0 calc(var(--ds-space) * 0.5);
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
  text-decoration: none;
}

.shop-page__back:hover {
  color: var(--ds-text);
}

.shop-page__badge {
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.25);
  border-radius: 999px;
  background: var(--ds-accent);
  color: var(--ds-accent-text);
  font-size: var(--ds-t-2);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.shop-page__more {
  margin-left: auto;
}

.shop-page :deep(.shop-page__icon-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}

.shop-page__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.shop-page__hint {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--ds-space);
  margin: 0 0 calc(var(--ds-space) * 2);
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.shop-page__hint-title {
  color: var(--ds-text);
  font-weight: 600;
}

.shop-page__retry {
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.shop-page__recipes {
  margin-top: calc(var(--ds-space) * 2);
}

/* Upstream RecipeList, kept as is; only its sheets move onto the tokens (hairline, no shadow). */
.shop-page__recipes :deep(.v-list) {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space);
  padding: 0;
  background: transparent;
}

.shop-page__recipes :deep(.v-sheet) {
  margin: 0 !important;
  overflow: hidden;
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  box-shadow: none;
  color: var(--ds-text);
}
</style>
