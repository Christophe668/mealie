<template>
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
    <RecipeReadFeedbackDialog v-model="dialog" :recipe-id="recipeId" @changed="load" />
  </section>
</template>

<script setup lang="ts">
import { useId } from "vue";
import RecipeReadFeedbackDialog from "./RecipeReadFeedbackDialog.vue";
import RecipeReadFeedbackEntry from "./RecipeReadFeedbackEntry.vue";
import DsButton from "~/components/Design/DsButton.vue";
import { useUserApi } from "~/composables/api";
import type { RecipeFeedbackOut } from "~/lib/api/types/household";
import { newestFirst } from "~/lib/recipe/recipe-feedback";

const SHOWN = 3;

const props = defineProps<{
  recipeId: string;
  /** Feedback belongs to the household, so only its signed-in members see it. */
  signedIn: boolean;
}>();

const titleId = useId();
const api = useUserApi();
const entries = ref<RecipeFeedbackOut[]>([]);
const dialog = ref(false);

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
  if (stamp === seq) {
    entries.value = newestFirst(items).slice(0, SHOWN);
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
