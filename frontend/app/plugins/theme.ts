export interface ThemeConfig {
  lightPrimary: string;
  lightAccent: string;
  lightSecondary: string;
  lightSuccess: string;
  lightInfo: string;
  lightWarning: string;
  lightError: string;
  darkPrimary: string;
  darkAccent: string;
  darkSecondary: string;
  darkSuccess: string;
  darkInfo: string;
  darkWarning: string;
  darkError: string;
}

let __cachedTheme: ThemeConfig | undefined;

async function fetchTheme(): Promise<ThemeConfig | undefined> {
  const route = "/api/app/about/theme";

  try {
    const response = await fetch(route);
    const data = await response.json();
    return data as ThemeConfig;
  }
  catch {
    return undefined;
  }
}

export default defineNuxtPlugin(async (nuxtApp) => {
  nuxtApp.hook("vuetify:before-create", async ({ vuetifyOptions }) => {
    let theme = __cachedTheme;
    if (!theme) {
      theme = await fetchTheme();
      __cachedTheme = theme;
    }
    vuetifyOptions.theme = {
      defaultTheme: nuxtApp.$config.public.useDark ? "dark" : "light",
      variations: {
        colors: ["primary", "accent", "secondary", "success", "info", "warning", "error", "background"],
        lighten: 3,
        darken: 3,
      },
      themes: {
        light: {
          dark: false,
          // Defaults mirror mealie/core/settings/themes.py. Semantic colours are Mealie's stock
          // hues at 90% HSL saturation: success #43A047, info #1976D2, warning #FF6D00, error #EF5350.
          colors: {
            "primary": theme?.lightPrimary ?? "#F2B01E",
            // Always ink on the primary colour (spec: never light text on saffron), even when overridden.
            "on-primary": "#17201B",
            "accent": theme?.lightAccent ?? "#17201B",
            "secondary": theme?.lightSecondary ?? "#5B655F",
            "success": theme?.lightSuccess ?? "#489B4B",
            "info": theme?.lightInfo ?? "#2276C9",
            "warning": theme?.lightWarning ?? "#F26F0D",
            "error": theme?.lightError ?? "#E75B58",
            "background": "#F4F5F3",
            "surface": "#FFFFFF",
          },
        },
        dark: {
          dark: true,
          colors: {
            "primary": theme?.darkPrimary ?? "#F2B01E",
            "on-primary": "#17201B",
            "accent": theme?.darkAccent ?? "#ECEEEA",
            "secondary": theme?.darkSecondary ?? "#9AA49E",
            "success": theme?.darkSuccess ?? "#489B4B",
            "info": theme?.darkInfo ?? "#2276C9",
            "warning": theme?.darkWarning ?? "#F26F0D",
            "error": theme?.darkError ?? "#E75B58",
            "background": "#121714",
            "surface": "#1B211D",
          },
        },
      },
    };
  });
});
