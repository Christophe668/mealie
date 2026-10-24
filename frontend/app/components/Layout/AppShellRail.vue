<template>
  <aside class="ds-rail">
    <NuxtLink :to="homeTo" class="ds-rail__brand ds-focus">
      {{ brandName }}
    </NuxtLink>

    <nav class="ds-rail__nav" :aria-label="$t('app-shell.main-navigation')">
      <NuxtLink
        v-for="item in items"
        :key="item.key"
        :to="item.to"
        class="ds-rail__link ds-focus"
        :aria-current="item.active ? 'page' : undefined"
      >
        <DsIcon :name="item.icon" :size="18" />
        {{ item.label }}
      </NuxtLink>
    </nav>

    <div class="ds-rail__bottom">
      <button
        v-if="announcementCount > 0"
        type="button"
        class="ds-rail__link ds-focus"
        @click="emit('open-announcements')"
      >
        <DsIcon name="bullhornVariant" :size="18" />
        {{ $t("app-shell.announcements") }}
        <span class="ds-rail__count">{{ announcementCount }}</span>
      </button>

      <NuxtLink
        v-for="item in secondaryItems"
        :key="item.key"
        :to="item.to"
        class="ds-rail__link ds-focus"
        :aria-current="item.active ? 'page' : undefined"
      >
        <DsIcon :name="item.icon" :size="18" />
        {{ item.label }}
      </NuxtLink>

      <div v-if="userName" class="ds-rail__user">
        <span class="ds-rail__avatar" aria-hidden="true">{{ userName.charAt(0) }}</span>
        <span class="ds-rail__name">{{ userName }}</span>
        <button
          type="button"
          class="ds-rail__logout ds-focus"
          :aria-label="$t('app-shell.log-out')"
          :title="$t('app-shell.log-out')"
          @click="emit('log-out')"
        >
          <DsIcon name="logout" :size="18" />
        </button>
      </div>
      <NuxtLink v-else to="/login" class="ds-rail__link ds-focus">
        <DsIcon name="user" :size="18" />
        {{ $t("app-shell.log-in") }}
      </NuxtLink>
    </div>
  </aside>
</template>

<script setup lang="ts">
import DsIcon from "~/components/Design/DsIcon.vue";
import type { AppShellNavItem } from "~/types/application-types";

defineProps<{
  brandName: string;
  homeTo: string;
  items: AppShellNavItem[];
  secondaryItems: AppShellNavItem[];
  userName?: string;
  announcementCount: number;
}>();

const emit = defineEmits<{
  (e: "open-announcements" | "log-out"): void;
}>();
</script>

<style scoped>
.ds-rail {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
  height: 100vh;
  padding: calc(var(--ds-space) * 3) calc(var(--ds-space) * 2);
  overflow-y: auto;
  border-right: 1px solid var(--ds-border);
  background: var(--ds-bg);
}

.ds-rail__brand {
  padding: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 2.5);
  color: var(--ds-text);
  font-size: var(--ds-t-4);
  font-weight: 800;
  font-variation-settings: "wdth" 90;
  letter-spacing: -0.01em;
  text-decoration: none;
}

.ds-rail__nav,
.ds-rail__bottom {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
}

.ds-rail__bottom {
  margin-top: auto;
}

.ds-rail__link {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  width: 100%;
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 1.5);
  border: 1px solid transparent;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  font: inherit;
  font-size: var(--ds-t-2);
  font-weight: 500;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

.ds-rail__link:hover {
  color: var(--ds-text);
}

/* Active state is ink and weight on a raised surface: the shell spends no saffron. */
.ds-rail__link[aria-current="page"] {
  border-color: var(--ds-border);
  background: var(--ds-surface);
  color: var(--ds-text);
  font-weight: 600;
}

.ds-rail__count {
  margin-left: auto;
  min-width: calc(var(--ds-space) * 2.5);
  padding: 0 calc(var(--ds-space) * 0.75);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-text);
  color: var(--ds-bg);
  font-size: var(--ds-t-1);
  text-align: center;
}

.ds-rail__user {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  margin-top: var(--ds-space);
  padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 0.5) 0 calc(var(--ds-space) * 1.25);
  border-top: 1px solid var(--ds-border);
}

.ds-rail__avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: calc(var(--ds-space) * 3.5);
  height: calc(var(--ds-space) * 3.5);
  border-radius: 50%;
  background: var(--ds-text);
  color: var(--ds-bg);
  font-size: var(--ds-t-1);
  font-weight: 700;
  text-transform: uppercase;
}

.ds-rail__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ds-rail__logout {
  display: grid;
  place-items: center;
  padding: calc(var(--ds-space) * 0.75);
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
}

.ds-rail__logout:hover {
  color: var(--ds-text);
}
</style>
