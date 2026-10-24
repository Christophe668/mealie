<template>
  <div class="ds-section-title">
    <h2 class="ds-section-title__text">
      {{ title }}
    </h2>
    <NuxtLink
      v-if="action"
      :to="action.to"
      class="ds-section-title__action ds-focus"
    >
      {{ action.label }}
    </NuxtLink>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  action?: { label: string; to: string };
}>();
</script>

<style scoped>
.ds-section-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 2);
  margin: calc(var(--ds-space) * 4.5) 0 calc(var(--ds-space) * 1.75);
}

.ds-section-title__text {
  margin: 0;
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

.ds-section-title__action {
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  font-weight: 500;
  text-decoration: none;
}

.ds-section-title__action:hover {
  color: var(--ds-text);
  text-decoration: underline;
}
</style>
