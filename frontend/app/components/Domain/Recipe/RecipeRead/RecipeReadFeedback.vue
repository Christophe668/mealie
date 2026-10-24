<template>
  <!-- Stays mounted while the dialog is open, so deleting the last entry closes the dialog rather than tearing it down. -->
  <div v-if="entries.length || dialog">
    <section v-if="entries.length" class="read-feedback" :aria-labelledby="titleId">
      <div class="read-feedback__head">
        <h2 :id="titleId" class="read-feedback__title">
          {{ $t("recipe-feedback.title") }}
        </h2>
        <DsButton variant="ghost" class="read-feedback__see-all" @click="dialog = true">
          {{ $t("recipe-feedback.see-all") }}
        </DsButton>
      </div>
      <ul class="read-feedback__list" role="list">
        <RecipeReadFeedbackEntry v-for="entry in entries" :key="entry.id" :entry="entry" />
      </ul>
    </section>
    <RecipeReadFeedbackDialog v-model="dialog" :recipe-id="recipeId" @changed="load" />
  </div>
</template>

<script setup lang="ts">
import { useId } from "vue";
import RecipeReadFeedbackDialog from "./RecipeReadFeedbackDialog.vue";
import RecipeReadFeedbackEntry from "./RecipeReadFeedbackEntry.vue";
import DsButton from "~/components/Design/DsButton.vue";
import { useUserApi } from "~/composables/api";
import { useFocusReturn } from "~/composables/use-focus-return";
import type { RecipeFeedbackOut } from "~/lib/api/types/household";
import { newestFirst } from "~/lib/recipe/recipe-feedback";

const SHOWN = 3;

const props = defineProps<{
  recipeId: string;
  /** Feedback belongs to the household, so only its signed-in members see it. */
  signedIn: boolean;
  /** Where focus goes when the dialog closes and "See all" is gone with the last entry (the page title). */
  focusFallbackId?: string;
}>();

const titleId = useId();
const api = useUserApi();
const entries = ref<RecipeFeedbackOut[]>([]);
const dialog = ref(false);

// Back to "See all" on close; to the fallback when the block went away with the last entry.
useFocusReturn(dialog, () => (props.focusFallbackId ? document.getElementById(props.focusFallbackId) : null));

// A response for a recipe the page has already moved on from is dropped.
let seq = 0;

/** Loads on its own after the page renders; any failure simply leaves the block hidden. */
async function load() {
  const stamp = ++seq;
  if (!props.signedIn || !props.recipeId) {
    entries.value = [];
    return;
  }
  let items: RecipeFeedbackOut[] = [];
  try {
    const { data } = await api.recipeFeedback.list(props.recipeId, 1, SHOWN);
    items = data?.items ?? [];
  }
  catch {
    items = [];
  }
  if (stamp !== seq) {
    return;
  }
  entries.value = newestFirst(items).slice(0, SHOWN);
  // Nothing left to list (the last entry was deleted): close the dialog too.
  if (!entries.value.length) {
    dialog.value = false;
  }
}

watch(() => [props.recipeId, props.signedIn], load, { immediate: true });
</script>

<style scoped>
.read-feedback__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--ds-space);
  margin-bottom: calc(var(--ds-space) * 1.5);
}

.read-feedback__title {
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.read-feedback__head :deep(.read-feedback__see-all) {
  color: var(--ds-text-2);
}

.read-feedback__list {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
  margin: 0;
  padding: 0;
  list-style: none;
}
</style>
