<template>
  <div class="ds-empty">
    <p class="ds-empty__title">
      {{ title }}
    </p>
    <p v-if="text" class="ds-empty__text ds-muted">
      {{ text }}
    </p>
    <DsButton
      v-if="action"
      class="ds-empty__action"
      variant="line"
      :to="action.to"
      @click="action.onClick?.()"
    >
      {{ action.label }}
    </DsButton>
  </div>
</template>

<script setup lang="ts">
import DsButton from "./DsButton.vue";

defineProps<{
  title: string;
  text?: string;
  /** Empty states say what to do next: give them a verb. */
  action?: { label: string; to?: string; onClick?: () => void };
}>();
</script>

<style scoped>
.ds-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 3);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.ds-empty__title {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.ds-empty__text {
  margin: 0;
  max-width: 70ch;
  font-size: var(--ds-t-2);
}

.ds-empty__action {
  margin-top: var(--ds-space);
}
</style>
