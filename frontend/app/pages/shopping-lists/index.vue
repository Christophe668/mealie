<template>
  <div class="shop-lists">
    <div class="shop-lists__bar">
      <label class="shop-lists__all">
        <input v-model="preferences.viewAllLists" type="checkbox" class="shop-lists__all-box ds-focus">
        {{ $t("shop.show-all-lists") }}
      </label>
      <DsButton variant="dark" icon="createAlt" @click="state.createDialog = true">
        {{ $t("shop.new-list") }}
      </DsButton>
    </div>

    <p class="shop-lists__sr" role="status">
      {{ loading ? $t("general.loading") : "" }}
    </p>

    <p v-if="failed" class="shop-lists__hint">
      <span class="shop-lists__hint-title">{{ $t("shop.lists-load-failed") }}</span>
      <button type="button" class="shop-lists__retry ds-focus" @click="refresh()">
        {{ $t("shop.try-again") }}
      </button>
    </p>

    <DsEmpty
      v-else-if="ready && !choices.length"
      :title="$t('shop.no-lists')"
      :text="$t('shop.no-lists-hint')"
      :action="{ label: $t('shop.create-list'), onClick: () => (state.createDialog = true) }"
    />

    <ul v-if="ready && choices.length" class="shop-lists__grid" role="list">
      <li v-for="list in choices" :key="list.id">
        <DsCard interactive class="shop-lists__card">
          <div class="shop-lists__card-body">
            <!-- The name is the link; its ::after stretches over the card so the whole card opens the list. -->
            <NuxtLink :to="`/shopping-lists/${list.id}`" class="shop-lists__name ds-focus">
              {{ list.name || $t("shop.untitled") }}
            </NuxtLink>
            <p class="shop-lists__open">
              {{ openByList[list.id] ? $t("shop.to-buy", { count: openByList[list.id] }) : $t("shop.nothing-open") }}
            </p>
            <p v-if="list.updatedAt" class="shop-lists__updated ds-muted">
              {{ $t("shop.updated", { when: updatedAgo(list.updatedAt, now, $i18n.locale) }) }}
            </p>
          </div>
          <AppShellMenu
            class="shop-lists__more"
            :items="listMenu(list)"
            :label="$t('shop.actions-for', { name: list.name || $t('shop.untitled') })"
            :trigger-label="$t('shop.actions-for', { name: list.name || $t('shop.untitled') })"
            trigger-class="shop-lists__icon-btn ds-focus"
            placement="bottom-end"
          >
            <template #trigger>
              <DsIcon name="dotsVertical" :size="20" />
            </template>
          </AppShellMenu>
        </DsCard>
      </li>
    </ul>

    <BaseDialog
      v-model="state.createDialog"
      bottom-sheet
      :title="$t('shopping-list.create-shopping-list')"
      :icon="$globals.icons.formatListCheck"
      can-submit
      :submit-disabled="!isCreateNameValid"
      @submit="createOne"
    >
      <v-card-text>
        <v-text-field
          v-model.trim="state.createName"
          autofocus
          :label="$t('shopping-list.new-list')"
        />
      </v-card-text>
    </BaseDialog>

    <BaseDialog
      v-model="state.ownerDialog"
      bottom-sheet
      :icon="$globals.icons.admin"
      :title="$t('user.edit-user')"
      can-confirm
      @confirm="updateOwner"
    >
      <v-container>
        <v-form>
          <v-select
            v-model="updateUserId"
            :items="allUsers"
            item-title="fullName"
            item-value="id"
            :label="$t('general.owner')"
            :prepend-icon="$globals.icons.user"
          />
        </v-form>
      </v-container>
    </BaseDialog>

    <BaseDialog
      v-model="state.deleteDialog"
      bottom-sheet
      :title="$t('general.confirm')"
      :icon="$globals.icons.alertCircle"
      color="error"
      can-confirm
      @confirm="deleteOne"
    >
      <v-card-text>{{ $t('shopping-list.are-you-sure-you-want-to-delete-this-item') }}</v-card-text>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import DsEmpty from "~/components/Design/DsEmpty.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import AppShellMenu from "~/components/Layout/AppShellMenu.vue";
import { useUserApi } from "~/composables/api";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { updatedAgo } from "~/composables/use-shop";
import { useShoppingListPreferences } from "~/composables/use-users/preferences";
import type { ShoppingListSummary } from "~/lib/api/types/household";
import type { UserOut } from "~/lib/api/types/user";
import type { AppShellMenuItem } from "~/types/application-types";

definePageMeta({
  middleware: ["auth"],
});

const auth = useMealieAuth();
const i18n = useI18n();
const userApi = useUserApi();
const route = useRoute();

useAppShellTitle(() => i18n.t("shop.lists-title"));
useSeoMeta({ title: () => i18n.t("shop.lists-title") });

const preferences = useShoppingListPreferences();
const overrideDisableRedirect = ref(false);
const disableRedirect = computed(() => route.query.disableRedirect === "true" || overrideDisableRedirect.value);

const state = reactive({
  createName: "",
  createDialog: false,
  deleteDialog: false,
  deleteTarget: "",
  ownerDialog: false,
  ownerTarget: null as ShoppingListSummary | null,
});
const isCreateNameValid = computed(() => state.createName.trim().length > 0);

// =====================================================
// Lists, most recently updated first, with their open counts (one request for every open item).

const lists = ref<ShoppingListSummary[] | null>(null);
const openByList = ref<Record<string, number>>({});
const loading = ref(true);
const failed = ref(false);
const ready = ref(false);
const now = ref(new Date());
let sequence = 0;

async function refresh() {
  const run = ++sequence;
  loading.value = true;
  failed.value = false;
  const [listsResponse, itemsResponse] = await Promise.all([
    userApi.shopping.lists.getAll(1, -1, { orderBy: "updated_at", orderDirection: "desc" }),
    userApi.shopping.items.getAll(1, -1, { queryFilter: "checked = false" }),
  ]);
  if (run !== sequence) {
    return;
  }
  loading.value = false;
  now.value = new Date();
  if (!listsResponse.data) {
    failed.value = true;
    return;
  }
  lists.value = listsResponse.data.items as ShoppingListSummary[];
  // Counts are a nicety: if they fail, the cards still open their lists.
  const counts: Record<string, number> = {};
  itemsResponse.data?.items.forEach((item) => {
    counts[item.shoppingListId] = (counts[item.shoppingListId] ?? 0) + 1;
  });
  openByList.value = counts;
}

onMounted(refresh);

const choices = computed(() =>
  (lists.value ?? []).filter(list => preferences.value.viewAllLists || list.userId === auth.user.value?.id),
);

// Must run before the redirect watcher, otherwise the redirect fires before it is disabled.
watch(
  () => preferences.value.viewAllLists,
  () => {
    overrideDisableRedirect.value = true;
  },
);

// One list and no explicit visit to the index: go straight to it, as upstream does.
watch(lists, () => {
  if (!disableRedirect.value && choices.value.length === 1) {
    navigateTo(`/shopping-lists/${choices.value[0]!.id}`);
  }
  else {
    ready.value = true;
  }
});

async function createOne() {
  if (!isCreateNameValid.value) return;
  const { data } = await userApi.shopping.lists.createOne({ name: state.createName.trim() });
  if (data) {
    state.createName = "";
    overrideDisableRedirect.value = true;
    refresh();
  }
}

function listMenu(list: ShoppingListSummary): AppShellMenuItem[] {
  return [
    { key: "owner", label: i18n.t("shop.change-owner"), icon: "user", onSelect: () => openOwner(list) },
    { key: "delete", label: i18n.t("shop.delete-list"), icon: "delete", onSelect: () => openDelete(list.id) },
  ];
}

// =====================================================
// Owner

const allUsers = ref<UserOut[]>([]);
const updateUserId = ref<string | undefined>();

async function openOwner(list: ShoppingListSummary) {
  state.ownerTarget = list;
  const { data } = await userApi.households.fetchMembers();
  if (data) {
    allUsers.value = data.items.sort((a, b) => ((a.fullName || "") < (b.fullName || "") ? -1 : 1));
  }
  updateUserId.value = list.userId;
  state.ownerDialog = true;
}

async function updateOwner() {
  if (!state.ownerTarget || !updateUserId.value || state.ownerTarget.userId === updateUserId.value) {
    return;
  }
  // Fetch the full list so the move does not drop its items.
  const { data: fullList } = await userApi.shopping.lists.getOne(state.ownerTarget.id);
  if (!fullList) {
    return;
  }
  const { data } = await userApi.shopping.lists.updateOne(state.ownerTarget.id, { ...fullList, userId: updateUserId.value });
  if (data) {
    refresh();
  }
}

// =====================================================
// Delete

function openDelete(id: string) {
  state.deleteTarget = id;
  state.deleteDialog = true;
}

async function deleteOne() {
  const { data } = await userApi.shopping.lists.deleteOne(state.deleteTarget);
  if (data) {
    refresh();
  }
}
</script>

<style scoped>
.shop-lists {
  max-width: 960px;
}

.shop-lists__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 1.5);
  margin-bottom: calc(var(--ds-space) * 2.5);
}

.shop-lists__all {
  display: inline-flex;
  align-items: center;
  gap: var(--ds-space);
  min-height: 44px;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
  cursor: pointer;
}

.shop-lists__all-box {
  width: 20px;
  height: 20px;
  margin: 0;
  accent-color: var(--ds-text);
}

.shop-lists__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.shop-lists__hint {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--ds-space);
  margin: 0 0 calc(var(--ds-space) * 2);
  font-size: var(--ds-t-2);
}

.shop-lists__hint-title {
  font-weight: 600;
}

.shop-lists__retry {
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text);
  font: inherit;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.shop-lists__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: calc(var(--ds-space) * 2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.shop-lists__card {
  position: relative;
  height: 100%;
  /* DsCard clips its media; nothing to clip here, and the actions menu must overflow the card. */
  overflow: visible;
}

.shop-lists__card-body {
  padding-right: calc(var(--ds-space) * 5);
}

.shop-lists__name {
  display: block;
  border-radius: var(--ds-radius-ctl);
  color: var(--ds-text);
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
  line-height: 1.2;
  text-decoration: none;
  overflow-wrap: anywhere;
}

.shop-lists__name::after {
  content: "";
  position: absolute;
  inset: 0;
}

.shop-lists__open {
  margin: calc(var(--ds-space) * 1.25) 0 0;
  font-size: var(--ds-t-3);
  font-weight: 500;
}

.shop-lists__updated {
  margin: calc(var(--ds-space) * 0.25) 0 0;
  font-size: var(--ds-t-2);
}

.shop-lists__more {
  position: absolute;
  top: var(--ds-space);
  right: var(--ds-space);
  z-index: 1;
}

.shop-lists :deep(.shop-lists__icon-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: var(--ds-radius-ctl);
  background: none;
  color: var(--ds-text-2);
  cursor: pointer;
}

.shop-lists :deep(.shop-lists__icon-btn:hover) {
  color: var(--ds-text);
}
</style>
