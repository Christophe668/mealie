<template>
  <v-dialog v-model="open" max-width="520" :aria-label="title">
    <form v-if="draft" class="pantry-dialog" @submit.prevent="save">
      <h2 class="pantry-dialog__title">
        {{ title }}
      </h2>

      <label class="pantry-dialog__field">
        <span class="pantry-dialog__label">{{ $t("pantry.name") }}</span>
        <input v-model="draft.name" type="text" class="pantry-dialog__input" required autocomplete="off">
      </label>

      <label class="pantry-dialog__field">
        <span class="pantry-dialog__label">{{ $t("pantry.where") }}</span>
        <select v-model="draft.location" class="pantry-dialog__input">
          <option v-for="location in PANTRY_LOCATIONS" :key="location" :value="location">
            {{ $t(`pantry.location.${location}`) }}
          </option>
        </select>
      </label>

      <div class="pantry-dialog__row">
        <label class="pantry-dialog__field">
          <span class="pantry-dialog__label">{{ $t("pantry.quantity") }}</span>
          <input
            v-model="quantity"
            type="number"
            min="0"
            step="any"
            inputmode="decimal"
            class="pantry-dialog__input"
          >
        </label>
        <label class="pantry-dialog__field">
          <span class="pantry-dialog__label">{{ $t("pantry.unit") }}</span>
          <select v-model="draft.unitId" class="pantry-dialog__input">
            <option :value="null">{{ $t("pantry.no-unit") }}</option>
            <option v-for="unit in sortedUnits" :key="unit.id" :value="unit.id">
              {{ unit.name }}
            </option>
          </select>
        </label>
      </div>

      <div class="pantry-dialog__row pantry-dialog__row--dates">
        <label class="pantry-dialog__field">
          <span class="pantry-dialog__label">{{ $t("pantry.bought-on") }}</span>
          <input v-model="boughtOn" type="date" class="pantry-dialog__input">
        </label>
        <label class="pantry-dialog__field">
          <span class="pantry-dialog__label">{{ $t("pantry.opened-on") }}</span>
          <input v-model="openedOn" type="date" class="pantry-dialog__input">
        </label>
        <label class="pantry-dialog__field">
          <span class="pantry-dialog__label">{{ $t("pantry.use-by-date") }}</span>
          <input v-model="useBy" type="date" class="pantry-dialog__input">
        </label>
      </div>

      <label class="pantry-dialog__field">
        <span class="pantry-dialog__label">{{ $t("pantry.note") }}</span>
        <textarea v-model="note" rows="2" class="pantry-dialog__input pantry-dialog__textarea" />
      </label>

      <div class="pantry-dialog__actions">
        <DsButton variant="line" @click="open = false">
          {{ $t("pantry.cancel") }}
        </DsButton>
        <DsButton variant="dark" type="submit" :disabled="saving || !draft.name.trim()">
          {{ $t("pantry.save") }}
        </DsButton>
      </div>
    </form>
  </v-dialog>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import { toPantryUpdate } from "~/composables/use-pantry";
import { PANTRY_LOCATIONS } from "~/lib/pantry/freshness";
import type { PantryItemOut, PantryItemUpdate } from "~/lib/api/types/household";
import type { IngredientUnit } from "~/lib/api/types/recipe";

const props = defineProps<{
  /** The item being edited; the dialog works on a copy so a background reload never overwrites typing. */
  item: PantryItemOut | null;
  units: IngredientUnit[];
  /** Saves the item; resolves true on success. It reports its own failure, the dialog only stays open. */
  saveItem: (id: string, data: PantryItemUpdate) => Promise<boolean>;
}>();

const open = defineModel<boolean>({ default: false });
const i18n = useI18n();

const draft = ref<PantryItemUpdate | null>(null);
watch(
  () => [open.value, props.item] as const,
  ([isOpen, item]) => {
    if (isOpen && item) {
      draft.value = toPantryUpdate(item);
    }
  },
  { immediate: true },
);

const title = computed(() => i18n.t("pantry.edit-dialog", { name: props.item?.name ?? "" }));
const sortedUnits = computed(() => [...props.units].sort((a, b) => a.name.localeCompare(b.name, i18n.locale.value)));

/** An emptied input means "no value", never an empty string, for the optional fields. */
function nullable<K extends "boughtOn" | "openedOn" | "useBy" | "note">(key: K) {
  return computed({
    get: () => draft.value?.[key] ?? "",
    set: (value: string) => {
      if (draft.value) {
        draft.value[key] = value.trim() ? value : null;
      }
    },
  });
}
const boughtOn = nullable("boughtOn");
const openedOn = nullable("openedOn");
const useBy = nullable("useBy");
const note = nullable("note");

const quantity = computed({
  get: () => draft.value?.quantity ?? "",
  set: (value: string | number) => {
    if (draft.value) {
      draft.value.quantity = value === "" || value === null ? null : Number(value);
    }
  },
});

const saving = ref(false);

/** Closes only once the save went through; a failed save keeps the dialog and what was typed in it. */
async function save() {
  if (saving.value || !props.item || !draft.value || !draft.value.name.trim()) {
    return;
  }
  saving.value = true;
  try {
    if (await props.saveItem(props.item.id, { ...draft.value, name: draft.value.name.trim() })) {
      open.value = false;
    }
  }
  finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.pantry-dialog {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
  padding: calc(var(--ds-space) * 3);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  color: var(--ds-text);
  font-family: var(--ds-font);
}

.pantry-dialog__title {
  margin: 0;
  font-size: var(--ds-t-5);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

.pantry-dialog__row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: calc(var(--ds-space) * 1.5);
}

.pantry-dialog__row--dates {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.pantry-dialog__field {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
  min-width: 0;
}

.pantry-dialog__label {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}

.pantry-dialog__input {
  width: 100%;
  min-height: 44px;
  padding: var(--ds-space) calc(var(--ds-space) * 1.25);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
  color: var(--ds-text);
  color-scheme: light;
  font: inherit;
  font-size: var(--ds-t-2);
  appearance: auto;
}

.pantry-dialog__input:focus-visible {
  border-color: var(--ds-text);
  outline: 2px solid var(--ds-text);
  outline-offset: 1px;
}

:global(.v-theme--dark) .pantry-dialog__input {
  /* Native date pickers and select arrows follow the theme. */
  color-scheme: dark;
}

.pantry-dialog__textarea {
  resize: vertical;
}

.pantry-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--ds-space);
  margin-top: var(--ds-space);
}

@media (max-width: 599px) {
  .pantry-dialog {
    padding: calc(var(--ds-space) * 2);
  }

  .pantry-dialog__row--dates {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
