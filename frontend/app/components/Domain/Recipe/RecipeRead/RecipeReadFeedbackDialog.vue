<template>
  <v-dialog v-model="open" max-width="560" scrollable :aria-label="$t('recipe-feedback.title')">
    <div class="read-feedback-dialog">
      <div class="read-feedback-dialog__head">
        <h2 class="read-feedback-dialog__title">
          {{ $t("recipe-feedback.title") }}
        </h2>
        <DsButton variant="ghost" @click="open = false">
          {{ $t("recipe-feedback.close") }}
        </DsButton>
      </div>
      <p v-if="loadFailed" class="read-feedback-dialog__empty">
        {{ $t("recipe-feedback.load-failed") }}
      </p>
      <ul v-else class="read-feedback-dialog__list" role="list">
        <RecipeReadFeedbackEntry v-for="entry in entries" :key="entry.id" :entry="entry">
          <template #actions>
            <DsButton variant="line" :disabled="deleting" @click="pending = entry">
              {{ $t("recipe-feedback.delete") }}
            </DsButton>
          </template>
        </RecipeReadFeedbackEntry>
      </ul>
    </div>
    <BaseDialog
      v-model="confirmOpen"
      :title="$t('recipe-feedback.delete-title')"
      color="error"
      :icon="$globals.icons.alertCircle"
      can-confirm
      @confirm="remove"
    >
      <v-card-text>
        {{ $t("recipe-feedback.delete-text") }}
      </v-card-text>
    </BaseDialog>
  </v-dialog>
</template>

<script setup lang="ts">
import RecipeReadFeedbackEntry from "./RecipeReadFeedbackEntry.vue";
import DsButton from "~/components/Design/DsButton.vue";
import { useUserApi } from "~/composables/api";
import { alert } from "~/composables/use-toast";
import type { RecipeFeedbackOut } from "~/lib/api/types/household";
import { newestFirst } from "~/lib/recipe/recipe-feedback";

const props = defineProps<{ recipeId: string }>();
const emit = defineEmits<{ (e: "changed"): void }>();
const open = defineModel<boolean>({ required: true });

const api = useUserApi();
const i18n = useI18n();
const entries = ref<RecipeFeedbackOut[]>([]);
const loadFailed = ref(false);
const deleting = ref(false);

/** The entry waiting for the delete confirmation. */
const pending = ref<RecipeFeedbackOut | null>(null);
const confirmOpen = computed({
  get: () => pending.value !== null,
  set: (value) => {
    if (!value) {
      pending.value = null;
    }
  },
});

async function load() {
  const { data } = await api.recipeFeedback.list(props.recipeId, 1, -1);
  loadFailed.value = !data;
  entries.value = newestFirst(data?.items ?? []);
}

watch(open, (value) => {
  if (value) {
    load();
  }
}, { immediate: true });

async function remove() {
  const entry = pending.value;
  pending.value = null;
  if (!entry || deleting.value) {
    return;
  }
  deleting.value = true;
  const { error } = await api.recipeFeedback.remove(entry.id);
  deleting.value = false;
  if (error) {
    alert.error(i18n.t("recipe-feedback.delete-failed"));
    return;
  }
  emit("changed");
  await load();
}
</script>

<style scoped>
.read-feedback-dialog {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2.5);
  max-height: 80vh;
  overflow-y: auto;
  padding: calc(var(--ds-space) * 3);
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  color: var(--ds-text);
  font-family: var(--ds-font);
}

.read-feedback-dialog__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ds-space);
}

.read-feedback-dialog__title {
  margin: 0;
  font-size: var(--ds-t-5);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

.read-feedback-dialog__empty {
  margin: 0;
  color: var(--ds-text-2);
}

.read-feedback-dialog__list {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}

.read-feedback-dialog__list > :deep(.read-feedback__entry) {
  padding: calc(var(--ds-space) * 1.5) 0;
  border-top: 1px solid var(--ds-border);
}

.read-feedback-dialog__list > :deep(.read-feedback__entry:first-child) {
  padding-top: 0;
  border-top: 0;
}
</style>
