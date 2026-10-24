<template>
  <div class="consent">
    <p class="consent__sr" role="status">
      {{ loading ? $t("general.loading") : "" }}
    </p>

    <div v-if="loading" class="consent__card consent__card--loading" aria-hidden="true">
      <span class="consent__skeleton consent__skeleton--title" />
      <span class="consent__skeleton" />
      <span class="consent__skeleton consent__skeleton--short" />
    </div>

    <DsCard v-else-if="request" class="consent__card">
      <div class="consent__head">
        <span class="consent__badge">
          <DsIcon name="lock" :size="22" />
        </span>
        <h1 class="ds-title">
          {{ $t("settings.mcp.authorize-title") }}
        </h1>
      </div>

      <p class="consent__text">
        <i18n-t keypath="settings.mcp.authorize-text">
          <template #client>
            <strong>{{ clientLabel }}</strong>
          </template>
        </i18n-t>
      </p>

      <template v-if="request.scopes.length">
        <p class="consent__lead">
          {{ $t("settings.mcp.authorize-scopes") }}
        </p>
        <ul class="consent__scopes" role="list">
          <li v-for="scope in request.scopes" :key="scope" class="consent__scope">
            <DsIcon name="check" :size="18" />
            {{ scopeLabel(scope) }}
          </li>
        </ul>
      </template>

      <p class="consent__redirect ds-muted">
        {{ $t("settings.mcp.authorize-redirect", { host: request.redirectHost }) }}
      </p>

      <div class="consent__actions">
        <DsButton variant="line" :disabled="submitting" @click="decide(false)">
          {{ $t("settings.mcp.deny") }}
        </DsButton>
        <DsButton icon="check" :disabled="submitting" :aria-busy="submitting ? 'true' : undefined" @click="decide(true)">
          {{ $t("settings.mcp.approve") }}
        </DsButton>
      </div>
    </DsCard>

    <DsCard v-else class="consent__card">
      <h1 class="ds-title">
        {{ $t("settings.mcp.authorize-title") }}
      </h1>
      <p class="consent__expired" role="alert">
        <DsIcon name="alertCircle" :size="20" />
        <span>{{ $t("settings.mcp.expired") }}</span>
      </p>
      <div class="consent__actions consent__actions--start">
        <DsButton variant="dark" icon="home" to="/">
          {{ $t("settings.mcp.back-home") }}
        </DsButton>
      </div>
    </DsCard>
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
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

<style scoped>
.consent {
  display: flex;
  justify-content: center;
  padding: calc(var(--ds-space) * 6) calc(var(--ds-space) * 2);
}

.consent__card {
  width: 100%;
  max-width: 560px;
}

.consent__card :deep(.ds-card__body),
.consent__card--loading {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
  padding: calc(var(--ds-space) * 4);
}

.consent__card--loading {
  background: var(--ds-surface);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.consent__head {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
}

.consent__badge {
  display: grid;
  flex: none;
  place-items: center;
  width: calc(var(--ds-space) * 5);
  height: calc(var(--ds-space) * 5);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-text);
  color: var(--ds-bg);
}

.consent__text {
  font-size: var(--ds-t-3);
  line-height: 1.5;
}

.consent__lead {
  margin-bottom: calc(var(--ds-space) * -1) !important;
  font-weight: 600;
}

.consent__scopes {
  display: flex;
  flex-direction: column;
  padding: 0;
  list-style: none;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.consent__scope {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.25);
  padding: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 2);
  font-size: var(--ds-t-2);
}

.consent__scope + .consent__scope {
  border-top: 1px solid var(--ds-border);
}

.consent__redirect {
  font-size: var(--ds-t-1);
}

.consent__expired {
  display: flex;
  gap: calc(var(--ds-space) * 1.25);
  padding: calc(var(--ds-space) * 2);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-bg);
  line-height: 1.5;
}

.consent__expired :deep(.ds-icon) {
  margin-top: 2px;
  color: rgb(var(--v-theme-warning));
}

.consent__actions {
  display: flex;
  justify-content: space-between;
  gap: var(--ds-space);
  margin-top: var(--ds-space);
}

.consent__actions--start {
  justify-content: flex-start;
}

.consent__skeleton {
  display: block;
  height: 1rem;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-border);
}

.consent__skeleton--title {
  width: 60%;
  height: 1.75rem;
}

.consent__skeleton--short {
  width: 40%;
}

.consent__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (max-width: 599px) {
  .consent {
    padding: calc(var(--ds-space) * 2);
  }

  .consent__card :deep(.ds-card__body) {
    padding: calc(var(--ds-space) * 2.5);
  }
}
</style>
