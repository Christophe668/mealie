<template>
  <component
    :is="to ? NuxtLinkComponent : 'div'"
    :to="to"
    class="ds-card"
    :class="{ 'ds-card--interactive': interactive || !!to, 'ds-focus': !!to }"
  >
    <div v-if="$slots.media" class="ds-card__media">
      <slot name="media" />
    </div>
    <div :class="{ 'ds-card__body': padded }">
      <slot />
    </div>
  </component>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  padded?: boolean;
  /** Hover affordance without navigation, e.g. when the parent handles the click. Implied by `to`. */
  interactive?: boolean;
  to?: string;
}>(), {
  padded: true,
  interactive: false,
  to: undefined,
});

const NuxtLinkComponent = resolveComponent("NuxtLink");
</script>

<style scoped>
.ds-card {
  display: block;
  overflow: hidden;
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  color: var(--ds-text);
  text-decoration: none;
}

.ds-card__media > :deep(img) {
  display: block;
  width: 100%;
  object-fit: cover;
}

.ds-card__body {
  padding: calc(var(--ds-space) * 2.25) calc(var(--ds-space) * 2.5);
}

.ds-card--interactive {
  cursor: pointer;
  transition: border-color 120ms ease;
}

.ds-card--interactive:hover {
  border-color: var(--ds-text-2);
}

@media (prefers-reduced-motion: reduce) {
  .ds-card--interactive {
    transition: none;
  }
}
</style>
