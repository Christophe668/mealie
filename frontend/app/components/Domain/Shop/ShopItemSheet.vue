<template>
  <DsSheet v-model="open" :title="title" :busy="busy" :fallback="focusFallback">
    <template #header>
      <header class="shop-sheet__header">
        <h2 class="shop-sheet__title">
          {{ title }}
        </h2>
        <p v-if="forText" class="shop-sheet__for">
          {{ forText }}
        </p>
        <!-- Whether the pantry already holds it, so "Already in the pantry" or "Put away" is an informed choice. -->
        <p v-if="item" class="shop-sheet__pantry" :class="{ 'shop-sheet__pantry--in': !!match }" role="status">
          <DsIcon :name="match ? 'checkboxMarkedCircle' : 'fridgeOutline'" :size="18" />
          <span>{{ pantryStatus }}</span>
        </p>
      </header>
    </template>

    <template v-if="item">
      <button type="button" class="ds-sheet__action" :disabled="busy" @click="emit('toggle')">
        <DsIcon :name="item.checked ? 'undo' : 'cartCheck'" />
        <span class="shop-sheet__label">{{ $t(item.checked ? "shop.mark-not-bought" : "shop.mark-bought") }}</span>
      </button>

      <!-- The two pantry actions wait for the pantry's answer: it decides the wording and whether a place is asked. -->
      <button type="button" class="ds-sheet__action" :disabled="busy || match === undefined" @click="emit('put-away', location)">
        <DsIcon name="fridgeOutline" />
        <span>
          <span class="shop-sheet__label">{{ $t("shop.put-away-one") }}</span>
          <span class="ds-sheet__hint">{{ putAwayHint }}</span>
        </span>
      </button>
      <!-- Not in the pantry yet: one place for either action. -->
      <div v-if="match === null" class="shop-sheet__places">
        <DsPlaceChips v-model="location" />
      </div>
      <button type="button" class="ds-sheet__action" :disabled="busy || match === undefined" @click="emit('already-have', location)">
        <DsIcon name="checkboxMarkedCircle" />
        <span>
          <span class="shop-sheet__label">{{ $t("shop.already-have") }}</span>
          <span class="ds-sheet__hint">{{ $t("shop.already-have-hint") }}</span>
        </span>
      </button>

      <button type="button" class="ds-sheet__action" :disabled="busy" @click="emit('edit')">
        <DsIcon name="edit" />
        <span class="shop-sheet__label">{{ $t("shop.edit-quantity-note") }}</span>
      </button>
      <button type="button" class="ds-sheet__action ds-sheet__action--danger" :disabled="busy" @click="emit('remove')">
        <DsIcon name="delete" />
        <span class="shop-sheet__label">{{ $t("shop.remove") }}</span>
      </button>
    </template>
  </DsSheet>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import DsPlaceChips from "~/components/Design/DsPlaceChips.vue";
import DsSheet from "~/components/Design/DsSheet.vue";
import type { PantryItemOut, PantryLocation, ShoppingListItemOut } from "~/lib/api/types/household";
import { DEFAULT_PANTRY_LOCATION } from "~/lib/pantry/freshness";

const props = withDefaults(defineProps<{
  item: ShoppingListItemOut | null;
  /** The pantry row that already holds the item; null when none, undefined while the pantry is being asked. */
  match: PantryItemOut | null | undefined;
  /** Where put away would file it (from its label); preselects the place. */
  guessedLocation: PantryLocation;
  /** An action is saving: the buttons wait and the sheet stays open. */
  busy: boolean;
  /** "For Roast chicken", from `itemForText`; empty when it comes from no recipe. */
  forText?: string;
  /** Where focus goes on close when the action took the item's row (and the button that opened the sheet) away. */
  focusFallback?: () => HTMLElement | null | undefined;
}>(), { forText: "", focusFallback: undefined });

const emit = defineEmits<{
  "toggle": [];
  "put-away": [location: PantryLocation];
  "already-have": [location: PantryLocation];
  "edit": [];
  "remove": [];
}>();

const open = defineModel<boolean>({ default: false });

const i18n = useI18n();

const title = computed(() => props.item?.display || props.item?.food?.name || props.item?.note || i18n.t("recipe.ingredient"));

const putAwayHint = computed(() => {
  if (!props.match) {
    return i18n.t("shop.put-away-one-hint");
  }
  const place = props.match.location ?? DEFAULT_PANTRY_LOCATION;
  // "the other" reads badly: a row with no particular place is just in the pantry.
  return place === "other"
    ? i18n.t("shop.put-away-into-pantry")
    : i18n.t("shop.put-away-into", { place: i18n.t(`pantry.location.${place}`).toLocaleLowerCase(i18n.locale.value) });
});

/** "Checking the pantry…", "Not in the pantry" or "In the pantry · 2 kg · Fridge". */
const pantryStatus = computed(() => {
  const match = props.match;
  if (match === undefined) {
    return i18n.t("shop.pantry-checking");
  }
  if (match === null) {
    return i18n.t("shop.pantry-not-in");
  }
  const unit = match.unit ? (match.unit.useAbbreviation && match.unit.abbreviation) || match.unit.name : "";
  const amount = match.quantity ? [match.quantity, unit].filter(Boolean).join(" ") : "";
  const place = match.location && match.location !== "other" ? i18n.t(`pantry.location.${match.location}`) : "";
  return [i18n.t("shop.pantry-in"), amount, place].filter(Boolean).join(" · ");
});

const location = ref<PantryLocation>(props.guessedLocation);

// Each opening, and each item, starts from the guess (a poll that relabels the open item keeps the choice).
watch(
  () => [open.value, props.item?.id] as const,
  ([isOpen]) => {
    if (isOpen) {
      location.value = props.guessedLocation;
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.shop-sheet__header {
  margin-bottom: calc(var(--ds-space) * 1.5);
}

.shop-sheet__title {
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.shop-sheet__for {
  margin: 2px 0 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.shop-sheet__pantry {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.75);
  margin: calc(var(--ds-space) * 1) 0 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.shop-sheet__pantry--in {
  color: var(--ds-text);
  font-weight: 600;
}

.shop-sheet__label {
  display: block;
}

.shop-sheet__places {
  padding: 0 0 calc(var(--ds-space) * 1.5);
}
</style>
