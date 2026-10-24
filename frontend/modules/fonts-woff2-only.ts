import { defineNuxtModule } from "nuxt/kit";

type FontFace = { src: Array<{ url?: string; format?: string }> };
type InitializedProvider = { resolveFont: (family: string, options: unknown) => Promise<{ fonts: FontFace[] } | undefined> };
type Provider = ((ctx: unknown) => Promise<InitializedProvider | undefined>) & { _name: string };
type ProviderFactory = (options?: unknown) => Provider;

/**
 * The Google provider also downloads static per-weight fallbacks for old browsers. For a font with
 * width/optical-size axes those statics are narrower instances (e.g. "SemiCondensed Regular"), and
 * because they are declared after the variable faces the browser picks them for exact weights.
 * Every supported browser reads woff2, so keep only the woff2 (variable) faces.
 */
export default defineNuxtModule({
  meta: { name: "fonts-woff2-only" },
  setup(_options, nuxt) {
    nuxt.hook("fonts:providers", (providers) => {
      const google = providers.google as ProviderFactory | undefined;
      if (!google)
        return;
      providers.google = ((options?: unknown) => {
        const base = google(options);
        const provider = async (ctx: unknown) => {
          const initialized = await base(ctx);
          if (!initialized)
            return initialized;
          return {
            ...initialized,
            async resolveFont(family: string, resolveOptions: unknown) {
              const result = await initialized.resolveFont(family, resolveOptions);
              return result && { ...result, fonts: result.fonts.filter(font => font.src.some(src => src.format === "woff2")) };
            },
          };
        };
        return Object.assign(provider, { _name: base._name });
      }) as unknown as (typeof providers)[string];
    });
  },
});
