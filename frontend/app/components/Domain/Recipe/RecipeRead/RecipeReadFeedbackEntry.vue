<template>
  <li class="read-feedback__entry">
    <div class="read-feedback__body">
      <p class="read-feedback__verdict">
        {{ $t(verdictLabelKey(entry.verdict)) }}
      </p>
      <p class="read-feedback__meta">
        <span class="read-feedback__when">{{ when }}</span>
        <DsChip v-if="effort">
          {{ $t(effortLabelKey(effort)) }}
        </DsChip>
      </p>
      <p v-if="entry.note?.trim()" class="read-feedback__note">
        {{ entry.note }}
      </p>
    </div>
    <slot name="actions" />
  </li>
</template>

<script setup lang="ts">
import DsChip from "~/components/Design/DsChip.vue";
import type { RecipeFeedbackOut } from "~/lib/api/types/household";
import { effortLabelKey, feedbackWhenLine, isFeedbackEffort, verdictLabelKey } from "~/lib/recipe/recipe-feedback";

const props = defineProps<{ entry: RecipeFeedbackOut }>();

const i18n = useI18n();
const effort = computed(() => (isFeedbackEffort(props.entry.effort) ? props.entry.effort : null));
const when = computed(() => feedbackWhenLine(props.entry, new Date(), i18n.t, i18n.locale.value));
</script>

<style scoped>
.read-feedback__entry {
  display: flex;
  align-items: flex-start;
  gap: calc(var(--ds-space) * 1.5);
}

.read-feedback__body {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
}

.read-feedback__verdict {
  margin: 0;
  color: var(--ds-text);
  font-size: var(--ds-t-3);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.01em;
  line-height: 1.3;
}

.read-feedback__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--ds-space);
  margin: 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.read-feedback__note {
  margin: 0;
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  line-height: 1.55;
  overflow-wrap: anywhere;
  white-space: pre-line;
}
</style>
