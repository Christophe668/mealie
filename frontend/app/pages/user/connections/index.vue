<template>
  <div class="links">
    <BaseDialog
      v-model="revokeDialog"
      :title="$t('settings.mcp.revoke')"
      :icon="$globals.icons.alertCircle"
      color="error"
      can-confirm
      @confirm="revokeConnection"
    >
      <v-card-text>
        {{ $t("settings.mcp.revoke-confirm", { client: revokeTarget ? connectionLabel(revokeTarget) : "" }) }}
      </v-card-text>
    </BaseDialog>

    <p class="links__intro ds-body ds-muted">
      {{ $t("settings.mcp.description") }}
    </p>

    <DsCard class="links__howto">
      <h2 class="links__h2">
        {{ $t("settings.mcp.how-to") }}
      </h2>
      <label :for="urlId" class="links__label">{{ $t("settings.mcp.server-url") }}</label>
      <div class="links__url">
        <input
          :id="urlId"
          :value="mcpUrl"
          readonly
          class="links__url-input ds-focus"
          @focus="($event.target as HTMLInputElement).select()"
        >
        <DsButton variant="line" icon="contentCopy" @click="copyText(mcpUrl)">
          {{ $t("general.copy") }}
        </DsButton>
      </div>
      <ol class="links__steps">
        <li>{{ $t("settings.mcp.how-to-step-1") }}</li>
        <li>{{ $t("settings.mcp.how-to-step-2") }}</li>
        <li>{{ $t("settings.mcp.how-to-step-3") }}</li>
      </ol>
    </DsCard>

    <section class="links__list" :aria-busy="loading ? 'true' : undefined">
      <p class="links__sr" role="status">
        {{ loading ? $t("general.loading") : "" }}
      </p>
      <div v-if="loading" class="links__skeleton" aria-hidden="true">
        <span class="links__bar links__bar--title" />
        <span class="links__bar" />
        <span class="links__bar links__bar--short" />
      </div>
      <DsEmpty
        v-else-if="!connections.length"
        :title="$t('settings.mcp.no-connections')"
      />
      <ul v-else class="links__rows" role="list">
        <li v-for="connection in connections" :key="connection.grantId">
          <DsCard class="links__row">
            <div class="links__row-main">
              <h3 class="links__client">
                {{ connectionLabel(connection) }}
              </h3>
              <div class="links__scopes" :aria-label="$t('settings.mcp.scopes')" role="group">
                <DsChip v-for="scope in connection.scopes" :key="scope">
                  {{ scopeLabel(scope) }}
                </DsChip>
              </div>
              <dl class="links__facts">
                <div>
                  <dt>{{ $t("settings.mcp.created") }}</dt>
                  <dd>{{ formatDate(connection.createdAt) }}</dd>
                </div>
                <div>
                  <dt>{{ $t("settings.mcp.last-used") }}</dt>
                  <dd>{{ connection.lastUsedAt ? formatDate(connection.lastUsedAt) : $t("settings.mcp.never-used") }}</dd>
                </div>
              </dl>
            </div>
            <DsButton
              variant="line"
              icon="delete"
              class="links__revoke"
              :aria-label="`${$t('settings.mcp.revoke')} ${connectionLabel(connection)}`"
              @click="confirmRevoke(connection)"
            >
              {{ $t("settings.mcp.revoke") }}
            </DsButton>
          </DsCard>
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import DsChip from "~/components/Design/DsChip.vue";
import DsEmpty from "~/components/Design/DsEmpty.vue";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useUserApi } from "~/composables/api";
import { useCopy } from "~/composables/use-copy";
import { MCP_SCOPE_I18N_KEYS, type McpConnection } from "~/lib/api/user/mcp-connections";

definePageMeta({
  middleware: ["auth"],
});

const i18n = useI18n();
const api = useUserApi();
const { copyText } = useCopy();

useSeoMeta({
  title: i18n.t("settings.mcp.title"),
});
useAppShellTitle(() => i18n.t("settings.mcp.title"));

const urlId = useId();

const mcpUrl = computed(() => (import.meta.client ? `${window.location.origin}/mcp` : "/mcp"));

const loading = ref(true);
const connections = ref<McpConnection[]>([]);
const revokeDialog = ref(false);
const revokeTarget = ref<McpConnection | null>(null);

function scopeLabel(scope: string) {
  const key = MCP_SCOPE_I18N_KEYS[scope];
  return key ? i18n.t(key) : scope;
}

function connectionLabel(connection: McpConnection) {
  return connection.clientName || connection.clientId;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString(i18n.locale.value);
}

async function refresh() {
  const { data } = await api.mcpConnections.getConnections();
  connections.value = data ?? [];
  loading.value = false;
}

function confirmRevoke(connection: McpConnection) {
  revokeTarget.value = connection;
  revokeDialog.value = true;
}

async function revokeConnection() {
  if (!revokeTarget.value) {
    return;
  }
  await api.mcpConnections.revoke(revokeTarget.value.grantId);
  revokeTarget.value = null;
  await refresh();
}

onMounted(refresh);
</script>

<style scoped>
.links {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
  max-width: 820px;
}

.links__howto :deep(.ds-card__body) {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.5);
}

.links__h2 {
  font-size: var(--ds-t-4);
  font-weight: 700;
  font-variation-settings: "wdth" 92;
  letter-spacing: -0.015em;
}

.links__label {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}

.links__url {
  display: flex;
  gap: var(--ds-space);
  margin-top: calc(var(--ds-space) * -1);
}

.links__url-input {
  flex: 1;
  min-width: 0;
  padding: calc(var(--ds-space) * 1.25) calc(var(--ds-space) * 1.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
  color: var(--ds-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: var(--ds-t-2);
}

.links__steps {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space);
  padding-left: calc(var(--ds-space) * 2.5);
  font-size: var(--ds-t-2);
  line-height: 1.5;
  max-width: 70ch;
}

.links__rows {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.5);
  padding: 0;
  list-style: none;
}

.links__row :deep(.ds-card__body) {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: calc(var(--ds-space) * 2);
}

.links__row-main {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space);
  min-width: 0;
}

.links__client {
  font-size: var(--ds-t-3);
  font-weight: 700;
}

.links__scopes {
  display: flex;
  flex-wrap: wrap;
  gap: calc(var(--ds-space) * 0.75);
}

.links__facts {
  display: flex;
  flex-wrap: wrap;
  gap: calc(var(--ds-space) * 0.5) calc(var(--ds-space) * 3);
  margin: 0;
  font-size: var(--ds-t-2);
}

.links__facts dt {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
}

.links__facts dd {
  margin: 0;
}

.links__revoke {
  flex: none;
}

.links__skeleton {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 1.5);
  padding: calc(var(--ds-space) * 2.25) calc(var(--ds-space) * 2.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-surface);
}

.links__bar {
  display: block;
  width: 70%;
  height: 0.875rem;
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-border);
}

.links__bar--title {
  width: 35%;
  height: 1.125rem;
}

.links__bar--short {
  width: 45%;
}

.links__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

@media (max-width: 599px) {
  .links__url {
    flex-direction: column;
  }

  .links__row :deep(.ds-card__body) {
    flex-direction: column;
  }
}
</style>
