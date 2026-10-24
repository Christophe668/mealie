<template>
  <v-icon
    class="ds-icon"
    :icon="icons[name]"
    :size="size"
    :aria-hidden="label ? undefined : 'true'"
    :aria-label="label"
    :role="label ? 'img' : undefined"
  />
</template>

<script setup lang="ts">
// Same @mdi/js path map that the globals plugin exposes as $globals.icons, imported directly so the
// primitive stays usable (and testable) outside a Nuxt app context.
import { icons } from "~/lib/icons";
import type { Icon } from "~/lib/icons/icon-type";

withDefaults(defineProps<{
  name: keyof Icon;
  size?: number | string;
  /** Accessible name; omit for decorative icons next to visible text. */
  label?: string;
}>(), {
  size: 20,
  label: undefined,
});
</script>

<style scoped>
.ds-icon {
  color: currentColor;
  flex: none;
}
</style>
