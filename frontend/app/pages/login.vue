<template>
  <div class="login">
    <p v-if="reverseProxyLoggingIn" class="login__wait" role="status">
      <span class="login__spinner" aria-hidden="true" />
      {{ $t("general.loading") }}
    </p>
    <div v-else class="login__column">
      <div class="login__brand">
        <img
          v-if="$appInfo.brandingLogoUrl"
          :src="$appInfo.brandingLogoUrl"
          alt=""
          class="login__logo"
        >
        <DsIcon v-else name="primary" :size="36" />
        <span class="ds-display login__name">{{ $appInfo.brandingName || "Mealie" }}</span>
      </div>

      <section v-if="isFirstLogin" class="login__first" role="note">
        <DsIcon name="information" :size="20" class="login__first-icon" />
        <div class="login__first-body">
          <p>{{ $t('user.it-looks-like-this-is-your-first-time-logging-in') }}</p>
          <p class="login__cred">
            <span><strong>{{ $t('user.username') }}:</strong> changeme@example.com</span>
            <button
              type="button"
              class="login__copy ds-focus"
              :aria-label="`${$t('general.copy')} ${$t('user.username')}`"
              @click="copyText('changeme@example.com')"
            >
              <DsIcon name="contentCopy" :size="16" />
            </button>
          </p>
          <p class="login__cred">
            <span><strong>{{ $t('user.password') }}:</strong> MyPassword</span>
            <button
              type="button"
              class="login__copy ds-focus"
              :aria-label="`${$t('general.copy')} ${$t('user.password')}`"
              @click="copyText('MyPassword')"
            >
              <DsIcon name="contentCopy" :size="16" />
            </button>
          </p>
          <p class="ds-muted">
            {{ $t('user.dont-want-to-see-this-anymore-be-sure-to-change-your-email') }}
          </p>
        </div>
      </section>

      <DsCard class="login__card">
        <h1 class="ds-title login__title">
          {{ $t('user.sign-in') }}
        </h1>
        <form class="login__form" @submit.prevent="authenticate">
          <template v-if="$appInfo.allowPasswordLogin">
            <v-text-field
              id="username"
              v-model="form.email"
              :prepend-inner-icon="$globals.icons.email"
              autofocus
              autocomplete="username"
              name="username"
              :label="$t('user.email-or-username')"
              type="text"
              hide-details="auto"
            />
            <v-text-field
              id="password"
              v-model="form.password"
              :prepend-inner-icon="$globals.icons.lock"
              :append-inner-icon="passwordIcon"
              autocomplete="current-password"
              name="password"
              :label="$t('user.password')"
              :type="inputType"
              hide-details="auto"
              @click:append-inner="togglePasswordShow"
            />
            <label class="login__remember">
              <input v-model="form.remember" type="checkbox" class="login__remember-box ds-focus">
              {{ $t('user.remember-me') }}
            </label>
            <DsButton
              type="submit"
              size="lg"
              block
              :disabled="loggingIn || oidcLoggingIn"
              :aria-busy="loggingIn ? 'true' : undefined"
            >
              {{ $t("user.login") }}
            </DsButton>
          </template>

          <p v-if="$appInfo.enableOidc && $appInfo.allowPasswordLogin" class="login__or ds-muted">
            {{ $t("user.or") }}
          </p>
          <DsButton
            v-if="$appInfo.enableOidc"
            :variant="$appInfo.allowPasswordLogin ? 'line' : 'primary'"
            size="lg"
            block
            :disabled="oidcLoggingIn"
            :aria-busy="oidcLoggingIn ? 'true' : undefined"
            @click="() => oidcAuthenticate()"
          >
            {{ $t("user.login-oidc") }} {{ $appInfo.oidcProviderName }}
          </DsButton>
        </form>

        <div class="login__links">
          <NuxtLink
            v-if="$appInfo.allowSignup && $appInfo.allowPasswordLogin"
            to="/register"
            class="login__link ds-focus"
          >
            {{ $t("user.register") }}
          </NuxtLink>
          <span v-else class="ds-muted">{{ $t("user.invite-only") }}</span>
          <NuxtLink
            v-if="$appInfo.allowPasswordLogin"
            to="/forgot-password"
            class="login__link ds-focus"
          >
            {{ $t("user.reset-password") }}
          </NuxtLink>
        </div>
      </DsCard>

      <nav class="login__about" :aria-label="$t('about.about')">
        <a
          v-for="link in aboutLinks"
          :key="link.href"
          :href="link.href"
          target="_blank"
          rel="noopener"
          class="login__about-link ds-focus"
        >
          <DsIcon :name="link.icon" :size="16" />
          {{ link.text }}
        </a>
      </nav>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSessionStorage, whenever } from "@vueuse/core";
import DsButton from "~/components/Design/DsButton.vue";
import DsCard from "~/components/Design/DsCard.vue";
import DsIcon from "~/components/Design/DsIcon.vue";
import { useCopy } from "~/composables/use-copy";
import type { Icon } from "~/lib/icons/icon-type";
import { useLoggedInState } from "~/composables/use-logged-in-state";
import { usePasswordField } from "~/composables/use-passwords";
import { alert } from "~/composables/use-toast";
import { useAsyncKey } from "~/composables/use-utils";
import { isSafeRedirectTarget } from "~/lib/validators/redirect";
import type { AppStartupInfo } from "~/lib/api/types/admin";
import { useUserActivityPreferences } from "~/composables/use-users/preferences";

definePageMeta({
  layout: "blank",
});
const { copyText } = useCopy();

const router = useRouter();
const route = useRoute();
const i18n = useI18n();
const auth = useMealieAuth();
const { $appInfo, $axios } = useNuxtApp();
const { loggedIn } = useLoggedInState();
const groupSlug = computed(() => auth.user.value?.groupSlug);
const isDemo = ref(false);
const isFirstLogin = ref(false);
const activityPreferences = useUserActivityPreferences();
const { getDefaultActivityRoute } = useDefaultActivity();

// Survives the page reload that happens during OIDC redirect
const pendingShareRedirect = useSessionStorage<string | null>("pwa_share_redirect", null);

useSeoMeta({
  title: i18n.t("user.login"),
});

const aboutLinks = computed<{ text: string; icon: keyof Icon; href: string }[]>(() => [
  { text: i18n.t("about.sponsor"), icon: "heart", href: "https://github.com/sponsors/hay-kot" },
  { text: i18n.t("about.github"), icon: "github", href: "https://github.com/mealie-recipes/mealie" },
  { text: i18n.t("about.docs"), icon: "folderOutline", href: "https://docs.mealie.io/" },
]);

const form = reactive({
  email: "",
  password: "",
  // Defaults on: this is a self-hosted app people mostly reach from their own devices, and an
  // unticked box now ends the session when the browser closes.
  // Ideally this is off by default, but we've trained users for years to ignore this checkbox,
  // so turning it off would cause a headache for the majority of users.
  // Maybe we can revisit this in the future.
  remember: true,
});

useAsyncData(useAsyncKey(), async () => {
  const data = await $axios.get<AppStartupInfo>("/api/app/about/startup-info");
  isDemo.value = data.data.isDemo;
  isFirstLogin.value = data.data.isFirstLogin;

  if (data.data.isFirstLogin) {
    form.email = "changeme@example.com";
    form.password = "MyPassword";
  }
});

whenever(
  () => loggedIn.value && groupSlug.value,
  () => {
    // First-login setup always takes priority
    if (!isDemo.value && isFirstLogin.value && auth.user.value?.admin) {
      router.push("/admin/setup");
      return;
    }

    // After login, honour a pending PWA share redirect.
    // The redirect param can arrive via the URL query string (password login)
    // or via sessionStorage (OIDC login, where the OIDC provider reload clears
    // the query string).
    const redirectFromQuery = route.query.redirect as string | undefined;
    const redirectTarget = redirectFromQuery ?? pendingShareRedirect.value;
    if (isSafeRedirectTarget(redirectTarget)) {
      pendingShareRedirect.value = null;
      router.push(redirectTarget);
      return;
    }

    const defaultActivityRoute = getDefaultActivityRoute(
      activityPreferences.value.defaultActivity,
      groupSlug.value,
    );
    if (defaultActivityRoute) {
      router.push(defaultActivityRoute);
    }
    else {
      router.push(`/g/${groupSlug.value || ""}`);
    }
  },
  { immediate: true },
);

const loggingIn = ref(false);
const oidcLoggingIn = ref(false);
const reverseProxyLoggingIn = ref($appInfo.enableReverseProxyAuth && !isDirectLogin());

const { passwordIcon, inputType, togglePasswordShow } = usePasswordField();

whenever(
  () => $appInfo.enableOidc && $appInfo.oidcRedirect && !isCallback() && !isDirectLogin() /* && !auth.check().valid */,
  () => oidcAuthenticate(),
  { immediate: true },
);

onBeforeMount(async () => {
  if (isCallback()) {
    await oidcAuthenticate(true);
    // Failed callback redirects to ?direct=1 without reloading, so clear the spinner ourselves
    reverseProxyLoggingIn.value = false;
    return;
  }

  if ($appInfo.enableReverseProxyAuth && !isDirectLogin() && !loggedIn.value) {
    try {
      await auth.reverseProxySignIn();
    }
    catch {
      // Header missing/invalid - fall back to the regular login form
    }
  }
  reverseProxyLoggingIn.value = false;
});

function isCallback() {
  const params = new URLSearchParams(window.location.search);
  return params.has("code") || params.has("error");
}

function isDirectLogin() {
  const params = new URLSearchParams(window.location.search);
  return params.has("direct") && params.get("direct") === "1";
}

async function oidcAuthenticate(callback = false) {
  if (callback) {
    oidcLoggingIn.value = true;
    try {
      await auth.oauthSignIn();
    }
    catch (error) {
      await router.replace("/login?direct=1");
      alertOnError(error);
    }
    oidcLoggingIn.value = false;
  }
  else {
    // Save any pending PWA share redirect before leaving for the OIDC provider.
    // The OIDC callback reloads the page, which clears the query string, so we
    // persist the target in sessionStorage and restore it after login.
    const redirectTarget = route.query.redirect as string | undefined;
    if (isSafeRedirectTarget(redirectTarget)) {
      pendingShareRedirect.value = redirectTarget;
    }
    navigateTo("/api/auth/oauth", { external: true }); // start the redirect process
  }
}

async function authenticate() {
  if (form.email.length === 0 || form.password.length === 0) {
    alert.error(i18n.t("user.please-enter-your-email-and-password"));
    return;
  }

  loggingIn.value = true;
  const formData = new FormData();
  formData.append("username", form.email);
  formData.append("password", form.password);
  formData.append("remember_me", String(form.remember));

  try {
    await auth.signIn(formData);
  }
  catch (error) {
    console.log(error);
    alertOnError(error);
  }
  loggingIn.value = false;
}

function alertOnError(error: any) {
  // TODO Check if error is an AxiosError, but isAxiosError is not working right now
  // See https://github.com/nuxt-community/axios-module/issues/550
  // Import $axios from useContext()
  // if ($axios.isAxiosError(error) && error.response?.status === 401) {
  if (error.response?.status === 401) {
    alert.error(i18n.t("user.invalid-credentials"));
  }
  else if (error.response?.status === 423) {
    alert.error(i18n.t("user.account-locked-please-try-again-later"));
  }
  else {
    alert.error(i18n.t("events.something-went-wrong"));
  }
}
</script>

<style scoped>
.login {
  display: flex;
  justify-content: center;
  min-height: 100vh;
  padding: calc(var(--ds-space) * 8) calc(var(--ds-space) * 2) calc(var(--ds-space) * 4);
  background: var(--ds-bg);
  color: var(--ds-text);
}

.login__column {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 3);
  width: 100%;
  max-width: 440px;
}

.login__brand {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
}

.login__logo {
  width: 40px;
  height: 40px;
  object-fit: contain;
}

.login__name {
  font-size: var(--ds-t-7);
}

.login__first {
  display: flex;
  gap: calc(var(--ds-space) * 1.5);
  padding: calc(var(--ds-space) * 2) calc(var(--ds-space) * 2.5);
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-card);
  background: var(--ds-bg);
  font-size: var(--ds-t-2);
  line-height: 1.5;
}

.login__first-icon {
  margin-top: 2px;
  color: var(--ds-text-2);
}

.login__first-body {
  display: flex;
  flex-direction: column;
  gap: var(--ds-space);
  min-width: 0;
}

.login__cred {
  display: flex;
  align-items: center;
  gap: var(--ds-space);
  overflow-wrap: anywhere;
}

.login__copy {
  display: grid;
  flex: none;
  place-items: center;
  width: calc(var(--ds-space) * 4);
  height: calc(var(--ds-space) * 4);
  padding: 0;
  border: 1px solid var(--ds-border);
  border-radius: var(--ds-radius-ctl);
  background: var(--ds-surface);
  color: var(--ds-text);
  cursor: pointer;
}

.login__card :deep(.ds-card__body) {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2.5);
  padding: calc(var(--ds-space) * 3.5);
}

.login__form {
  display: flex;
  flex-direction: column;
  gap: calc(var(--ds-space) * 2);
}

.login__remember {
  display: inline-flex;
  align-items: center;
  gap: var(--ds-space);
  font-size: var(--ds-t-2);
  cursor: pointer;
}

.login__remember-box {
  width: 18px;
  height: 18px;
  accent-color: var(--ds-text);
}

.login__or {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  font-size: var(--ds-t-1);
}

.login__or::before,
.login__or::after {
  content: "";
  flex: 1;
  border-top: 1px solid var(--ds-border);
}

.login__links {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--ds-space) calc(var(--ds-space) * 2);
  padding-top: calc(var(--ds-space) * 2);
  border-top: 1px solid var(--ds-border);
  font-size: var(--ds-t-2);
}

.login__link {
  color: var(--ds-text);
  font-weight: 500;
  text-decoration: underline;
  text-underline-offset: 3px;
}

.login__about {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--ds-space) calc(var(--ds-space) * 2.5);
}

.login__about-link {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--ds-space) * 0.75);
  color: var(--ds-text-2);
  font-size: var(--ds-t-1);
  text-decoration: none;
}

.login__about-link:hover {
  color: var(--ds-text);
}

.login__wait {
  display: flex;
  align-items: center;
  gap: calc(var(--ds-space) * 1.5);
  align-self: center;
  color: var(--ds-text-2);
}

.login__spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--ds-border);
  border-top-color: var(--ds-text);
  border-radius: 50%;
  animation: login-spin 800ms linear infinite;
}

@keyframes login-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .login__spinner {
    animation: none;
    border-top-color: var(--ds-text-2);
  }
}

/* Fix password manager autofill detection - Vuetify uses opacity:0 during animation */
:deep(.v-field__input) {
  opacity: 1 !important;
}

@media (max-width: 599px) {
  .login {
    padding-top: calc(var(--ds-space) * 4);
  }

  .login__card :deep(.ds-card__body) {
    padding: calc(var(--ds-space) * 2.5);
  }
}
</style>

<!-- Legacy global classes kept as they were: AppLogo and other upstream components rely on them once this page has loaded. -->
<style lang="css">
.max-button {
  width: 300px;
}

.icon-white {
  fill: white;
}

.icon-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  position: relative;
  margin-top: 3.5rem;
}

.icon-divider {
  width: 100%;
  margin-bottom: -3.5rem;
}

.icon-avatar {
  border-color: rgba(0, 0, 0, 0.12);
  border: 2px;
}

.bg-off-white {
  background: #f5f8fa;
}

.absolute {
  position: absolute;
}

.div-width {
  max-width: 75%;
}

.bg-white {
  background-color: #fff;
}
</style>
