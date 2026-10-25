<template>
  <div class="household-profile">
    <p class="household-profile__intro ds-muted">
      {{ $t("household-profile.intro") }}
    </p>
    <!-- Polite announcements: loading, then nothing once the profiles are on screen. -->
    <p class="household-profile__sr" role="status">
      {{ loading && !loaded ? $t("household-profile.loading") : "" }}
    </p>
    <p v-if="failed" class="household-profile__hint" role="alert">
      <span class="household-profile__hint-title">{{ $t("household-profile.load-failed") }}</span>
      <button type="button" class="household-profile__retry ds-focus" @click="refresh">
        {{ $t("household-profile.try-again") }}
      </button>
    </p>

    <template v-if="loaded">
      <section aria-labelledby="who-eats-here">
        <DsSectionTitle id="who-eats-here" :title="$t('household-profile.who-eats-here')" />

        <div v-if="empty" class="household-profile__empty">
          <p class="household-profile__empty-title">
            {{ $t("household-profile.empty-title") }}
          </p>
          <p class="household-profile__empty-text ds-muted">
            {{ $t("household-profile.empty-text") }}
          </p>
          <div class="household-profile__actions">
            <DsButton variant="dark" :disabled="!currentUser" @click="addYourself">
              {{ $t("household-profile.add-yourself") }}
            </DsButton>
            <DsButton variant="line" @click="addPerson">
              {{ $t("household-profile.add-a-person") }}
            </DsButton>
          </div>
        </div>

        <template v-else>
          <ul class="household-profile__members" role="list">
            <li v-for="member in members" :key="member.id">
              <ProfileMemberCard
                :member="member"
                :is-you="isYou(member.userId)"
                :save-member="data => saveExisting(member.id, data)"
                @remove="pending = member"
              />
            </li>
            <li v-for="card in newCards" :key="card.key">
              <ProfileMemberCard
                :member="card.member"
                :is-you="isYou(card.member.userId)"
                :save-member="data => saveNew(card.key, data)"
                @remove="dropNew(card.key)"
              />
            </li>
          </ul>
          <div ref="listActions" class="household-profile__actions">
            <DsButton variant="line" icon="createAlt" @click="addPerson">
              {{ $t("household-profile.add-a-person") }}
            </DsButton>
            <DsButton v-if="canAddYourself" variant="line" @click="addYourself">
              {{ $t("household-profile.add-yourself") }}
            </DsButton>
          </div>
        </template>
      </section>

      <section aria-labelledby="how-we-cook">
        <DsSectionTitle id="how-we-cook" :title="$t('household-profile.how-we-cook')" />
        <ProfileHabitsCard
          :preferences="preferences"
          :first-day-of-week="firstDayOfWeek"
          :save-preferences="async changes => !!(await savePreferences(changes))"
        />
      </section>
    </template>

    <BaseDialog
      v-model="confirmOpen"
      :title="$t('household-profile.remove-title', { name: pendingName })"
      color="error"
      :icon="$globals.icons.alertCircle"
      can-confirm
      @confirm="confirmRemove"
    >
      <v-card-text>
        {{ $t("household-profile.remove-text", { name: pendingName }) }}
      </v-card-text>
    </BaseDialog>
  </div>
</template>

<script setup lang="ts">
import { useTemplateRef } from "vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsSectionTitle from "~/components/Design/DsSectionTitle.vue";
import ProfileHabitsCard from "~/components/Domain/Household/Profile/ProfileHabitsCard.vue";
import ProfileMemberCard from "~/components/Domain/Household/Profile/ProfileMemberCard.vue";
import { useAppShellTitle } from "~/composables/use-app-shell-title";
import { useFocusReturn } from "~/composables/use-focus-return";
import { useHouseholdProfile } from "~/composables/use-household-profile";
import { useHouseholdSelf } from "~/composables/use-households";
import { useMealieAuth } from "~/composables/use-mealie-auth";
import type { MemberProfileCreate, MemberProfileOut, MemberProfileUpdate } from "~/lib/api/types/household";
import { cutToLength, MAX_NAME_LENGTH } from "~/lib/household-profile/profile";

definePageMeta({
  middleware: ["auth"],
});

const i18n = useI18n();
const auth = useMealieAuth();
const { household } = useHouseholdSelf();

useAppShellTitle(() => i18n.t("household-profile.title"));
useSeoMeta({ title: () => i18n.t("household-profile.title") });

const { members, preferences, loading, failed, loaded, refresh, createMember, updateMember, removeMember, savePreferences }
  = useHouseholdProfile();

const firstDayOfWeek = computed(() => household.value?.preferences?.firstDayOfWeek ?? 0);
const currentUser = computed(() => auth.user.value ?? null);

function isYou(userId: string | null | undefined) {
  return !!userId && userId === currentUser.value?.id;
}

// =====================================================
// New people: unsaved cards below the saved ones, until their Save goes through.

const newCards = ref<{ key: number; member: Partial<MemberProfileOut> }[]>([]);
let nextKey = 0;

const empty = computed(() => !members.value.length && !newCards.value.length);
const canAddYourself = computed(
  () => !!currentUser.value && ![...members.value, ...newCards.value.map(card => card.member)].some(m => isYou(m.userId)),
);

function addPerson() {
  newCards.value.push({ key: nextKey++, member: {} });
}

/** A card with the signed-in user's name, linked to them. */
function addYourself() {
  const user = currentUser.value;
  if (!user) {
    return;
  }
  const name = cutToLength((user.fullName || user.username || "").trim(), MAX_NAME_LENGTH).trim();
  newCards.value.push({ key: nextKey++, member: { name, userId: user.id } });
}

function dropNew(key: number) {
  newCards.value = newCards.value.filter(card => card.key !== key);
}

async function saveNew(key: number, data: Partial<MemberProfileCreate>) {
  // New people go last: the list is ordered by position, then name.
  const position = Math.max(-1, ...members.value.map(m => m.position ?? 0)) + 1;
  const created = await createMember({ ...data, name: data.name ?? "", position });
  if (created) {
    dropNew(key);
  }
  return !!created;
}

async function saveExisting(id: string, changes: MemberProfileUpdate) {
  return !!(await updateMember(id, changes));
}

// =====================================================
// Remove, after the confirmation

const pending = ref<MemberProfileOut | null>(null);
const pendingName = computed(() => pending.value?.name ?? "");
const confirmOpen = computed({
  get: () => pending.value !== null,
  set: (value) => {
    if (!value) {
      pending.value = null;
    }
  },
});

// The dialog opens without an activator: give focus back to the Remove button pressed (cancel), or to
// "Add a person" when that member was removed.
const listActions = useTemplateRef<HTMLElement>("listActions");
useFocusReturn(confirmOpen, () => listActions.value?.querySelector("button"));

async function confirmRemove() {
  const member = pending.value;
  pending.value = null;
  if (member && (await removeMember(member.id))) {
    // Focus went back to that member's Remove button, which is gone now.
    await nextTick();
    if (!document.activeElement || document.activeElement === document.body) {
      listActions.value?.querySelector("button")?.focus();
    }
  }
}
</script>

<style scoped>
.household-profile {
  max-width: 820px;
}

.household-profile__intro {
  margin: 0;
  max-width: 70ch;
  font-size: var(--ds-t-2);
}

.household-profile__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.household-profile__hint {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--ds-space);
  margin: calc(var(--ds-space) * 2) 0;
  color: var(--ds-text-2);
  font-size: var(--ds-t-2);
}

.household-profile__hint-title {
  color: var(--ds-text);
  font-weight: 600;
}

.household-profile__retry {
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

.household-profile__members {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.household-profile__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--ds-space);
  margin-top: calc(var(--ds-space) * 2);
}

.household-profile__empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--ds-space);
  padding: calc(var(--ds-space) * 3);
  border: 1px dashed var(--ds-border);
  border-radius: var(--ds-radius-card);
}

.household-profile__empty .household-profile__actions {
  margin-top: var(--ds-space);
}

.household-profile__empty-title {
  margin: 0;
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.household-profile__empty-text {
  margin: 0;
  max-width: 70ch;
  font-size: var(--ds-t-2);
}
</style>
