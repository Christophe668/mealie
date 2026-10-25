<template>
  <DsCard class="profile-member">
    <form class="profile-member__form" :aria-label="cardLabel" @submit.prevent="save">
      <div class="profile-member__head">
        <div class="profile-member__field profile-member__name">
          <span class="profile-member__label-row">
            <label :for="`${uid}-name`" class="profile-member__label">{{ $t("household-profile.name") }}</label>
            <DsChip v-if="isYou" class="profile-member__you">{{ $t("household-profile.you") }}</DsChip>
          </span>
          <input
            :id="`${uid}-name`"
            v-model="draft.name"
            type="text"
            class="profile-member__input profile-member__name-input"
            :maxlength="MAX_NAME_LENGTH"
            autocomplete="off"
            required
          >
        </div>
        <label class="profile-member__child">
          <input v-model="draft.isChild" type="checkbox" class="profile-member__checkbox">
          {{ $t("household-profile.child") }}
        </label>
      </div>

      <label class="profile-member__field profile-member__diet">
        <span class="profile-member__label">{{ $t("household-profile.diet") }}</span>
        <select v-model="draft.diet" class="profile-member__input">
          <option v-for="diet in DIETS" :key="diet" :value="diet">
            {{ $t(`household-profile.diets.${diet}`) }}
          </option>
        </select>
      </label>

      <div class="profile-member__lists">
        <ProfileChipInput
          v-for="list in MEMBER_LISTS"
          :key="list"
          v-model="draft[list]"
          :label="$t(`household-profile.lists.${list}`)"
          :tone="list === 'allergies' ? 'accent' : 'neutral'"
        />
      </div>

      <label class="profile-member__field">
        <span class="profile-member__label">{{ $t("household-profile.notes") }}</span>
        <textarea
          v-model="draft.notes"
          rows="2"
          class="profile-member__input profile-member__textarea"
          :maxlength="MAX_NOTES_LENGTH"
        />
      </label>

      <div class="profile-member__actions">
        <DsButton variant="line" :disabled="saving" @click="emit('remove')">
          {{ $t("household-profile.remove") }}
        </DsButton>
        <DsButton variant="dark" type="submit" :disabled="!canSave">
          {{ $t("household-profile.save") }}
        </DsButton>
      </div>
    </form>
  </DsCard>
</template>

<script setup lang="ts">
import { useId } from "vue";
import ProfileChipInput from "./ProfileChipInput.vue";
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import DsChip from "~/components/Design/DsChip.vue";
import type { MemberProfileOut } from "~/lib/api/types/household";
import {
  changedFields,
  DIETS,
  MAX_NAME_LENGTH,
  MAX_NOTES_LENGTH,
  MEMBER_LISTS,
  memberDraft,
  memberPayload,
  type MemberDraft,
} from "~/lib/household-profile/profile";

const props = defineProps<{
  /** A saved member, or the starting values of a new one (no `id`). */
  member: Partial<MemberProfileOut>;
  /** Linked to the signed-in user: shows the "You" badge. */
  isYou?: boolean;
  /**
   * Saves the card. A saved member gets only the changed fields, a new one gets everything. Resolves true on
   * success; it reports its own failure, the card only keeps what was typed.
   */
  saveMember: (data: Partial<ReturnType<typeof memberPayload>>) => Promise<boolean>;
}>();

const emit = defineEmits<{ (e: "remove"): void }>();

const i18n = useI18n();
const uid = useId();

const isNew = computed(() => !props.member.id);
const baseline = computed(() => memberDraft(props.member));
const draft = ref<MemberDraft>(memberDraft(props.member));

// A reload (or a save elsewhere) brings a new member object: take it unless something was typed here.
watch(() => props.member, (_now, before) => {
  if (JSON.stringify(draft.value) === JSON.stringify(memberDraft(before))) {
    draft.value = memberDraft(props.member);
  }
});

const changes = computed(() => changedFields(memberPayload(baseline.value), memberPayload(draft.value)));
const dirty = computed(() => isNew.value || Object.keys(changes.value).length > 0);

const saving = ref(false);
const canSave = computed(() => dirty.value && !saving.value && !!draft.value.name.trim());

const cardLabel = computed(() => draft.value.name.trim() || i18n.t("household-profile.new-person"));

async function save() {
  if (!canSave.value) {
    return;
  }
  saving.value = true;
  try {
    const ok = await props.saveMember(isNew.value ? memberPayload(draft.value) : changes.value);
    if (ok) {
      await nextTick();
      draft.value = memberDraft(props.member);
    }
  }
  finally {
    saving.value = false;
  }
}
</script>

<style scoped>
.profile-member__form {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.profile-member__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: calc(var(--ds-space) * 1.5) calc(var(--ds-space) * 2);
}

.profile-member__name {
  flex: 1 1 240px;
}

.profile-member__field {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 0.5);
  min-width: 0;
}

.profile-member__label-row {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  min-height: 24px;
}

.profile-member__label {
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  font-weight: 500;
}

.profile-member__input {
  width: 100%;
  min-height: 44px;
  padding: var(--ds-space) calc(var(--ds-space) * 1.25);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-bg);
  color: var(--ds-text);
  color-scheme: light;
  font: inherit;
  font-size: var(--ds-t-2);
  appearance: auto;
}

.profile-member__input:focus-visible {
  border-color: var(--ds-text);
  outline: 2px solid var(--ds-text);
  outline-offset: 1px;
}

:global(.v-theme--dark) .profile-member__input {
  color-scheme: dark;
}

.profile-member__name-input {
  font-size: var(--ds-t-3);
  font-weight: 600;
}

.profile-member__child {
  display: inline-flex;
  align-items: center;
  gap: var(--ds-space);
  min-height: 44px;
  color: var(--ds-text);
  font-size: var(--ds-t-2);
  font-weight: 500;
  cursor: pointer;
}

.profile-member__checkbox {
  width: 20px;
  height: 20px;
  margin: 0;
  accent-color: var(--ds-text);
  cursor: pointer;
}

.profile-member__diet {
  max-width: 320px;
}

.profile-member__lists {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: calc(var(--ds-space) * 2);
}

.profile-member__textarea {
  resize: vertical;
}

.profile-member__actions {
  display: flex;
  justify-content: space-between;
  gap: var(--ds-space);
}

@media (max-width: 599px) {
  .profile-member__lists {
    grid-template-columns: minmax(0, 1fr);
  }

  .profile-member__diet {
    max-width: none;
  }
}
</style>
