<template>
  <div class="read-hero" :class="{ 'read-hero--empty': showPlaceholder }">
    <img
      v-if="!showPlaceholder"
      :src="imageUrl"
      alt=""
      class="read-hero__img"
      @error="failed = true"
    >
    <span v-else class="read-hero__initial ds-display" aria-hidden="true">{{ initial }}</span>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  name: string;
  /** Empty when the recipe has no photo; the placeholder then shows the name's first letter. */
  imageUrl: string;
}>();

const failed = ref(false);
watch(() => props.imageUrl, () => (failed.value = false));

const showPlaceholder = computed(() => !props.imageUrl || failed.value);
const initial = computed(() => Array.from(props.name.trim())[0]?.toLocaleUpperCase() ?? "");
</script>

<style scoped>
.read-hero {
  display: grid;
  place-items: center;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: var(--ds-radius-hero);
  background: var(--ds-border);
}

.read-hero__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.read-hero__initial {
  color: var(--ds-text-2);
  font-size: calc(var(--ds-t-8) * 1.6);
  line-height: 1;
}

@media (max-width: 1023px) {
  /* Full-bleed on mobile: cancel the shell's 16 px gutter. */
  .read-hero {
    margin-inline: calc(var(--ds-space) * -2);
    border-radius: 0;
  }
}
</style>
