<template>
  <v-container class="narrow-container">
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

    <BasePageTitle divider>
      <template #header>
        <v-img
          width="100%"
          max-height="200px"
          max-width="200px"
          src="/svgs/manage-api-tokens.svg"
        />
      </template>
      <template #title>
        {{ $t("settings.mcp.title") }}
      </template>
      {{ $t("settings.mcp.description") }}
    </BasePageTitle>

    <section>
      <v-card
        class="mt-4 pa-4"
        variant="outlined"
      >
        <v-card-title class="px-0">
          {{ $t("settings.mcp.how-to") }}
        </v-card-title>
        <v-card-text class="px-0">
          <v-text-field
            :model-value="mcpUrl"
            :label="$t('settings.mcp.server-url')"
            readonly
            variant="outlined"
            density="comfortable"
          >
            <template #append-inner>
              <v-btn
                :icon="$globals.icons.contentCopy"
                :aria-label="$t('general.copy')"
                variant="text"
                size="small"
                @click="copyText(mcpUrl)"
              />
            </template>
          </v-text-field>
          <ol class="ml-5">
            <li>{{ $t("settings.mcp.how-to-step-1") }}</li>
            <li>{{ $t("settings.mcp.how-to-step-2") }}</li>
            <li>{{ $t("settings.mcp.how-to-step-3") }}</li>
          </ol>
        </v-card-text>
      </v-card>
    </section>

    <section class="mt-8">
      <div
        v-if="loading"
        class="d-flex justify-center my-6"
      >
        <v-progress-circular
          indeterminate
          color="primary"
        />
      </div>
      <p
        v-else-if="!connections.length"
        class="text-center text-medium-emphasis my-6"
      >
        {{ $t("settings.mcp.no-connections") }}
      </p>
      <v-table v-else>
        <thead>
          <tr>
            <th>{{ $t("settings.mcp.client") }}</th>
            <th>{{ $t("settings.mcp.scopes") }}</th>
            <th>{{ $t("settings.mcp.created") }}</th>
            <th>{{ $t("settings.mcp.last-used") }}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="connection in connections"
            :key="connection.grantId"
          >
            <td>{{ connectionLabel(connection) }}</td>
            <td>
              <v-chip
                v-for="scope in connection.scopes"
                :key="scope"
                size="small"
                class="ma-1"
              >
                {{ scopeLabel(scope) }}
              </v-chip>
            </td>
            <td>{{ formatDate(connection.createdAt) }}</td>
            <td>{{ connection.lastUsedAt ? formatDate(connection.lastUsedAt) : $t("settings.mcp.never-used") }}</td>
            <td class="text-right">
              <BaseButton
                delete
                small
                @click="confirmRevoke(connection)"
              >
                {{ $t("settings.mcp.revoke") }}
              </BaseButton>
            </td>
          </tr>
        </tbody>
      </v-table>
    </section>
  </v-container>
</template>

<script setup lang="ts">
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
