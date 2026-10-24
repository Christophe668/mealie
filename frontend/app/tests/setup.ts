import { config } from "@vue/test-utils";
import { createI18n } from "vue-i18n";

function loadEnLocales() {
  /* eslint-disable @typescript-eslint/no-require-imports */
  return {
    ...require("../lang/messages/en-US.json"),
    // app/lang/locales/*.ts merge these in at runtime; do the same here so unit names resolve
    "unit-names": require("../../../mealie/repos/seed/resources/units/locales/en-US.json"),
  } as Record<string, string>;
  /* eslint-enable @typescript-eslint/no-require-imports */
}

const i18n = createI18n({
  locale: "en-US",
  messages: {
    "en-US": loadEnLocales(),
  },
});

config.global.plugins = [...(config.global.plugins ?? []), i18n];

export { i18n };

// Node 25+ ships its own global localStorage/sessionStorage, which shadows jsdom's and has no methods
// unless Node runs with --localstorage-file. Give tests a working in-memory Storage instead.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }

  clear() {
    this.store.clear();
  }

  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number) {
    return [...this.store.keys()][index] ?? null;
  }

  removeItem(key: string) {
    this.store.delete(key);
  }

  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  if (typeof globalThis[name]?.clear !== "function") {
    Object.defineProperty(globalThis, name, { value: new MemoryStorage(), configurable: true, writable: true });
  }
}
