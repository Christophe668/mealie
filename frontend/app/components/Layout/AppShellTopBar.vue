<template>
  <header class="ds-topbar">
    <NuxtLink
      v-if="brandName"
      :to="homeTo"
      class="ds-topbar__brand ds-mobile-only ds-focus"
    >
      {{ brandName }}
    </NuxtLink>
    <div class="ds-topbar__title">
      <slot name="title" />
    </div>

    <form
      v-if="showSearch"
      role="search"
      class="ds-topbar__search ds-desktop-only"
      @submit.prevent="submit"
    >
      <label :for="inputId" class="ds-topbar__label">{{ $t("app-shell.search-recipes") }}</label>
      <DsIcon name="search" :size="18" />
      <input
        :id="inputId"
        ref="input"
        v-model="query"
        type="search"
        class="ds-topbar__input"
        :placeholder="$t('app-shell.search-recipes')"
        aria-keyshortcuts="Meta+K Control+K"
        enterkeyhint="search"
        autocomplete="off"
      >
      <kbd class="ds-topbar__kbd" :title="$t('app-shell.search-shortcut-hint', { shortcut: shortcutLabel })">{{ shortcutLabel }}</kbd>
    </form>

    <NuxtLink
      v-if="settingsTo"
      :to="settingsTo"
      class="ds-topbar__settings ds-mobile-only ds-focus"
      :aria-label="$t('app-shell.settings')"
    >
      <DsIcon name="cog" :size="22" />
    </NuxtLink>
  </header>
</template>

<script setup lang="ts">
import { useId } from "vue";
import { useEventListener } from "@vueuse/core";
import DsIcon from "~/components/Design/DsIcon.vue";

const props = withDefaults(defineProps<{
  /** Shown on mobile only, where there is no rail to carry the brand. */
  brandName?: string;
  homeTo?: string;
  showSearch?: boolean;
  /** Mobile has no rail, so the top bar carries the way to settings there. */
  settingsTo?: string;
}>(), {
  brandName: undefined,
  homeTo: "/",
  showSearch: true,
  settingsTo: undefined,
});

const emit = defineEmits<{
  (e: "search", query: string): void;
}>();

const inputId = useId();
const input = ref<HTMLInputElement | null>(null);
const query = ref("");

const isApple = ref(false);
onMounted(() => {
  isApple.value = /Mac|iPhone|iPad/.test(navigator.userAgent);
});
const shortcutLabel = computed(() => (isApple.value ? "⌘K" : "Ctrl K"));

function submit() {
  const value = query.value.trim();
  if (value) {
    emit("search", value);
  }
}

function focus() {
  input.value?.focus();
  input.value?.select();
}

useEventListener(window, "keydown", (event: KeyboardEvent) => {
  if (!props.showSearch || event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey)) {
    return;
  }
  event.preventDefault();
  focus();
});

defineExpose({ focus });
</script>

<style scoped>
.ds-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 3);
  min-height: calc(var(--ds-space) * 5);
  margin-bottom: calc(var(--ds-space) * 3);
}

.ds-topbar__brand {
  flex: none;
  color: var(--ds-text);
  font-size: var(--ds-t-4);
  font-weight: 800;
  font-variation-settings: "wdth" 90;
  letter-spacing: -0.01em;
  text-decoration: none;
}

.ds-topbar__title:empty {
  display: none;
}

.ds-topbar__title {
  min-width: 0;
  font-size: var(--ds-t-6);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

.ds-topbar__search {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.25);
  flex: none;
  width: calc(var(--ds-space) * 40);
  margin-left: auto;
  padding: var(--ds-space) calc(var(--ds-space) * 1.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text-2);
}

.ds-topbar__search:focus-within {
  border-color: var(--ds-text);
}

.ds-topbar__label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.ds-topbar__input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-size: var(--ds-t-2);
}

.ds-topbar__input::placeholder {
  color: var(--ds-text-2);
  opacity: 1;
}

.ds-topbar__input::-webkit-search-cancel-button {
  display: none;
}

.ds-topbar__kbd {
  padding: 0 calc(var(--ds-space) * 0.75);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text-2);
  font: inherit;
  font-size: var(--ds-t-1);
  white-space: nowrap;
}

.ds-topbar__settings {
  display: grid;
  place-items: center;
  margin-left: auto;
  padding: var(--ds-space);
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text-2);
}

@media (max-width: 1023px) {
  .ds-topbar {
    margin-bottom: calc(var(--ds-space) * 2);
  }

  .ds-topbar__brand {
    flex: none;
    color: var(--ds-text);
    font-size: var(--ds-t-4);
    font-weight: 800;
    font-variation-settings: "wdth" 90;
    letter-spacing: -0.01em;
    text-decoration: none;
  }

  .ds-topbar__title:empty {
    display: none;
  }

  .ds-topbar__title {
    font-size: var(--ds-t-5);
  }
}
</style>
