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

    <div class="ds-topbar__actions">
      <form
        v-if="showSearch"
        ref="form"
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

      <!-- The create menu, on every screen: on mobile it leaves the tab bar's width to the five tabs. -->
      <AppShellMenu
        v-if="addItems.length"
        class="ds-topbar__add"
        :items="addItems"
        :label="$t('app-shell.add')"
        :trigger-label="$t('app-shell.add')"
        trigger-class="ds-topbar__plus ds-focus"
        placement="bottom-end"
      >
        <template #trigger>
          <DsIcon name="createAlt" :size="22" />
        </template>
      </AppShellMenu>

      <!-- Mobile has no rail, so the account menu lives here. -->
      <AppShellMenu
        v-if="userItems.length"
        class="ds-mobile-only"
        :items="userItems"
        :label="$t('app-shell.account')"
        :trigger-label="$t('app-shell.account')"
        trigger-class="ds-topbar__icon ds-focus"
        placement="bottom-end"
      >
        <template #trigger>
          <DsIcon name="cog" :size="22" />
        </template>
      </AppShellMenu>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useId, useTemplateRef } from "vue";
import { useEventListener } from "@vueuse/core";
import AppShellMenu from "./AppShellMenu.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import type { AppShellMenuItem } from "~/types/application-types";

withDefaults(defineProps<{
  /** Shown on mobile only, where there is no rail to carry the brand. */
  brandName?: string;
  homeTo?: string;
  showSearch?: boolean;
  addItems?: AppShellMenuItem[];
  userItems?: AppShellMenuItem[];
}>(), {
  brandName: undefined,
  homeTo: "/",
  showSearch: true,
  addItems: () => [],
  userItems: () => [],
});

const emit = defineEmits<{
  (e: "search", query: string): void;
}>();

const inputId = useId();
const form = useTemplateRef<HTMLFormElement>("form");
const input = useTemplateRef<HTMLInputElement>("input");
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

function isOtherEditable(target: EventTarget | null) {
  if (!(target instanceof HTMLElement) || target === input.value) {
    return false;
  }
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

useEventListener(window, "keydown", (event: KeyboardEvent) => {
  if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey)) {
    return;
  }
  // Leave the shortcut alone where there is no visible field to focus (mobile) or the user is typing elsewhere.
  if (!form.value || getComputedStyle(form.value).display === "none" || isOtherEditable(event.target)) {
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

.ds-topbar__title {
  min-width: 0;
  font-size: var(--ds-t-6);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.02em;
  line-height: 1.15;
}

.ds-topbar__title:empty {
  display: none;
}

.ds-topbar__actions {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  margin-left: auto;
}

.ds-topbar__search {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.25);
  width: calc(var(--ds-space) * 40);
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

/* Ink, not saffron: the screen's accent belongs to its content. */
.ds-topbar__actions :deep(.ds-topbar__plus) {
  display: grid;
  place-items: center;
  width: calc(var(--ds-space) * 5.25);
  height: calc(var(--ds-space) * 5.25);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-text);
  color: var(--ds-bg);
  cursor: pointer;
}

.ds-topbar__actions :deep(.ds-topbar__icon) {
  display: grid;
  place-items: center;
  padding: var(--ds-space);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
}

@media (max-width: 1023px) {
  .ds-topbar {
    margin-bottom: calc(var(--ds-space) * 2);
  }

  /* The add menu hangs from the bar's right edge, not from the "+": the account icon sits to its right, and a
     menu ending at the "+" would run off the left of a phone. */
  .ds-topbar__actions {
    position: relative;
    gap: var(--ds-space);
  }

  .ds-topbar__actions :deep(.ds-topbar__add) {
    position: static;
  }

  .ds-topbar__actions :deep(.ds-topbar__plus) {
    width: calc(var(--ds-space) * 4.5);
    height: calc(var(--ds-space) * 4.5);
  }

  /* One line on mobile: a long title ellipsizes instead of crowding the brand. */
  .ds-topbar__title {
    overflow: hidden;
    font-size: var(--ds-t-5);
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
</style>
