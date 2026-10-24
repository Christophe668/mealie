<template>
  <span class="ds-chip" :class="`ds-chip--${tone}`">
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  /** accent = saffron; it spends the screen's single accent, so use sparingly. */
  tone?: "neutral" | "accent";
}>(), {
  tone: "neutral",
});
</script>

<style scoped>
.ds-chip {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.5);
  padding: calc(var(--ds-space) * 0.25) var(--ds-space);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  font-size: var(--ds-t-1);
  font-weight: 500;
  line-height: 1.4;
  white-space: nowrap;
}

.ds-chip--neutral {
  background: var(--ds-surface);
  color: var(--ds-text-2);
}

.ds-chip--accent {
  background: var(--ds-accent);
  border-color: transparent;
  color: var(--ds-accent-text);
}
</style>
