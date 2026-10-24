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

/**
 * Colours the backend reports when no THEME_* env var is set (mealie/core/settings/themes.py).
 * They are Mealie's stock palette, not a choice made by the admin, so they must not override the
 * design-system defaults below. Any other value from the API is a deliberate override and wins.
 */
const STOCK_THEME: Partial<ThemeConfig> = {
  lightPrimary: "#E58325",
  lightAccent: "#007A99",
  lightSecondary: "#973542",
  darkPrimary: "#E58325",
  darkAccent: "#007A99",
  darkSecondary: "#973542",
};

function themeColor(theme: ThemeConfig | undefined, key: keyof ThemeConfig, fallback: string): string {
  const value = theme?.[key];
  if (!value || value.toUpperCase() === STOCK_THEME[key]?.toUpperCase())
    return fallback;
  return value;
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
          colors: {
            "primary": themeColor(theme, "lightPrimary", "#F2B01E"),
            "on-primary": "#17201B",
            "accent": themeColor(theme, "lightAccent", "#17201B"),
            "secondary": themeColor(theme, "lightSecondary", "#5B655F"),
            "success": themeColor(theme, "lightSuccess", "#43A047"),
            "info": themeColor(theme, "lightInfo", "#1976d2"),
            "warning": themeColor(theme, "lightWarning", "#FF6D00"),
            "error": themeColor(theme, "lightError", "#EF5350"),
            "background": "#F4F5F3",
            "surface": "#FFFFFF",
          },
        },
        dark: {
          dark: true,
          colors: {
            "primary": themeColor(theme, "darkPrimary", "#F2B01E"),
            "on-primary": "#17201B",
            "accent": themeColor(theme, "darkAccent", "#ECEEEA"),
            "secondary": themeColor(theme, "darkSecondary", "#9AA49E"),
            "success": themeColor(theme, "darkSuccess", "#43A047"),
            "info": themeColor(theme, "darkInfo", "#1976d2"),
            "warning": themeColor(theme, "darkWarning", "#FF6D00"),
            "error": themeColor(theme, "darkError", "#EF5350"),
            "background": "#121714",
            "surface": "#1B211D",
          },
        },
      },
    };
  });
});
