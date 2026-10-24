<template>
  <v-container class="narrow-container">
    <div
      v-if="loading"
      class="d-flex justify-center mt-12"
    >
      <v-progress-circular
        indeterminate
        color="primary"
      />
    </div>

    <v-card
      v-else-if="request"
      class="mt-8 pa-4"
      flat
    >
      <v-card-title class="text-h5 px-0">
        <v-icon
          start
          color="primary"
        >
          {{ $globals.icons.lock }}
        </v-icon>
        {{ $t("settings.mcp.authorize-title") }}
      </v-card-title>
      <v-card-text class="px-0">
        <p class="text-body-1 mb-4">
          <i18n-t keypath="settings.mcp.authorize-text">
            <template #client>
              <strong>{{ clientLabel }}</strong>
            </template>
          </i18n-t>
        </p>
        <p
          v-if="request.scopes.length"
          class="mb-1"
        >
          {{ $t("settings.mcp.authorize-scopes") }}
        </p>
        <v-list density="compact">
          <v-list-item
            v-for="scope in request.scopes"
            :key="scope"
            :prepend-icon="$globals.icons.check"
            :title="scopeLabel(scope)"
          />
        </v-list>
        <p class="text-caption mt-4">
          {{ $t("settings.mcp.authorize-redirect", { host: request.redirectHost }) }}
        </p>
      </v-card-text>
      <v-card-actions class="px-0">
        <BaseButton
          cancel
          :disabled="submitting"
          @click="decide(false)"
        >
          {{ $t("settings.mcp.deny") }}
        </BaseButton>
        <v-spacer />
        <BaseButton
          :loading="submitting"
          :disabled="submitting"
          :icon="$globals.icons.check"
          @click="decide(true)"
        >
          {{ $t("settings.mcp.approve") }}
        </BaseButton>
      </v-card-actions>
    </v-card>

    <v-card
      v-else
      class="mt-8 pa-4"
      flat
    >
      <v-card-title class="text-h5 px-0">
        {{ $t("settings.mcp.authorize-title") }}
      </v-card-title>
      <v-card-text class="px-0">
        <v-alert
          type="warning"
          variant="tonal"
        >
          {{ $t("settings.mcp.expired") }}
        </v-alert>
      </v-card-text>
      <v-card-actions class="px-0">
        <BaseButton
          :icon="$globals.icons.home"
          to="/"
        >
          {{ $t("settings.mcp.back-home") }}
        </BaseButton>
      </v-card-actions>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { useUserApi } from "~/composables/api";
import { MCP_SCOPE_I18N_KEYS, type McpAuthorizeRequest } from "~/lib/api/user/mcp-connections";

definePageMeta({
  layout: "basic",
  // The auth middleware sends anonymous visitors to /login?redirect=<this page, with its query>,
  // and the login page sends them back here once signed in.
  middleware: ["auth"],
});

const i18n = useI18n();
const route = useRoute();
const api = useUserApi();

useSeoMeta({
  title: i18n.t("settings.mcp.authorize-title"),
});

const loading = ref(true);
const submitting = ref(false);
const request = ref<McpAuthorizeRequest | null>(null);

function scopeLabel(scope: string) {
  const key = MCP_SCOPE_I18N_KEYS[scope];
  return key ? i18n.t(key) : scope;
}

const clientLabel = computed(() => request.value?.clientName || request.value?.clientId || "");

onMounted(async () => {
  const requestId = route.query.request_id;
  if (typeof requestId === "string" && requestId) {
    const { data } = await api.mcpConnections.getAuthorizeRequest(requestId);
    request.value = data;
  }
  loading.value = false;
});

async function decide(approve: boolean) {
  if (!request.value || submitting.value) {
    return;
  }

  submitting.value = true;
  const { data, error } = await api.mcpConnections.decide(request.value.requestId, approve);
  if (data?.redirectUrl) {
    if (isWebUrl(data.redirectUrl)) {
      window.location.assign(data.redirectUrl);
      return;
    }
    // Never navigate to javascript:, data: or other schemes: they would run in the Mealie origin.
    request.value = null;
    submitting.value = false;
    return;
  }

  // A 404 means the request expired (or was already used) between page load and the click; a 400 means
  // the server refused the client's redirect URI. Any other failure leaves the page as is so the user can retry.
  const status = error?.response?.status;
  if (status === 404 || status === 400) {
    request.value = null;
  }
  submitting.value = false;
}

function isWebUrl(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return protocol === "https:" || protocol === "http:";
  }
  catch {
    return false;
  }
}
</script>
