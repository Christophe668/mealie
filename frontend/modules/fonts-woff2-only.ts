import { defineNuxtModule } from "nuxt/kit";

type FontFace = { src: Array<{ url?: string; format?: string }> };
type ResolveResult = { fonts: FontFace[] };
type InitializedProvider = { resolveFont: (family: string, options: unknown) => Promise<ResolveResult | undefined> };
type Provider = ((ctx: unknown) => Promise<InitializedProvider | undefined>) & { _name: string };
type ProviderFactory = (options?: unknown) => Provider;

/**
 * The Google provider also downloads static per-weight fallbacks for old browsers. For a font with
 * width/optical-size axes those statics are narrower instances (e.g. "SemiCondensed Regular"), and
 * because they are declared after the variable faces the browser picks them for exact weights.
 * Every supported browser reads woff2, so keep only the woff2 (variable) faces. Applies to every
 * Google family, which is fine: they all ship woff2.
 *
 * Verified against @nuxt/fonts 0.11.4 / unifont 0.4.1 (provider = factory(options) -> fn(ctx) with
 * `_name`). Newer @nuxt/fonts releases expose a font `formats` option; switch to it on upgrade and
 * delete this module. If the provider shape is not what we expect, it is passed through untouched.
 */
export default defineNuxtModule({
  meta: { name: "fonts-woff2-only" },
  setup(_options, nuxt) {
    nuxt.hook("fonts:providers", (providers) => {
      const google = providers.google;
      if (typeof google !== "function")
        return;
      const factory = google as unknown as ProviderFactory;
      providers.google = ((options?: unknown) => {
        const base = factory(options);
        if (typeof base !== "function")
          return base;
        const provider = async (ctx: unknown) => {
          const initialized = await base(ctx);
          if (!initialized || typeof initialized.resolveFont !== "function")
            return initialized;
          return {
            ...initialized,
            async resolveFont(family: string, resolveOptions: unknown) {
              const result = await initialized.resolveFont(family, resolveOptions);
              if (!result)
                return result;
              const woff2 = result.fonts.filter(font => font.src.some(src => src.format === "woff2"));
              return woff2.length ? { ...result, fonts: woff2 } : result;
            },
          };
        };
        return Object.assign(provider, { _name: base._name });
      }) as unknown as typeof google;
    });
  },
});
