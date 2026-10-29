import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const read = (name: string) => readFileSync(join(here, name), "utf8");

/** Returns the declarations of the first rule whose selector list contains `selector`. */
function declarations(css: string, selector: string): Record<string, string> {
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g);
  for (const [, selectors, body] of rules) {
    if (!selectors!.split(",").map(s => s.trim()).includes(selector))
      continue;
    return Object.fromEntries(
      body!.split(";")
        .map(d => d.trim())
        .filter(Boolean)
        .map((d) => {
          const i = d.indexOf(":");
          // Hex colours are compared lowercase: the CSS formatter normalises them.
          return [d.slice(0, i).trim(), d.slice(i + 1).trim().replace(/#[0-9a-f]{3,8}\b/gi, h => h.toLowerCase())];
        }),
    );
  }
  throw new Error(`No rule for selector ${selector}`);
}

describe("design tokens", () => {
  const tokens = read("tokens.css");

  test("light palette on :root", () => {
    const root = declarations(tokens, ":root");
    expect(root).toMatchObject({
      "--ds-bg": "#f4f5f3",
      "--ds-surface": "#ffffff",
      "--ds-border": "#dfe3df",
      "--ds-text-2": "#5b655f",
      "--ds-text": "#17201b",
      "--ds-accent": "#f2b01e",
      "--ds-accent-text": "#17201b",
    });
  });

  test("light palette also applies to light subtrees", () => {
    expect(declarations(tokens, ".v-theme--light")).toEqual(declarations(tokens, ":root"));
  });

  test("dark palette on .v-theme--dark", () => {
    const dark = declarations(tokens, ".v-theme--dark");
    expect(dark).toMatchObject({
      "--ds-bg": "#121714",
      "--ds-surface": "#1b211d",
      "--ds-border": "#2a322d",
      "--ds-text-2": "#9aa49e",
      "--ds-text": "#eceeea",
      "--ds-accent": "#f2b01e",
      "--ds-accent-text": "#17201b",
    });
  });

  test("cook mode shares the dark palette whatever the theme", () => {
    expect(declarations(tokens, ".ds-cook")).toEqual(declarations(tokens, ".v-theme--dark"));
  });

  test("pantry status tokens in both modes, never the accent", () => {
    expect(declarations(tokens, ":root")).toMatchObject({
      "--ds-have": "#2f7a4f",
      "--ds-have-surface": "#e5f1e9",
      "--ds-missing": "#a9432f",
      "--ds-missing-surface": "#f8e6e1",
      "--ds-soon": "#8f5d0e",
      "--ds-soon-surface": "#fbefd6",
      "--ds-soon-bar": "#d49a2a",
    });
    const dark = declarations(tokens, ".v-theme--dark");
    for (const key of ["have", "have-surface", "missing", "missing-surface", "soon", "soon-surface", "soon-bar"]) {
      expect(dark[`--ds-${key}`]).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  test.each([":root", ".v-theme--dark"])("status text meets AA contrast on its surface (%s)", (selector) => {
    const luminance = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => {
        const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    const decl = declarations(tokens, selector);
    for (const status of ["have", "missing", "soon"]) {
      const [hi, lo] = [luminance(decl[`--ds-${status}`]!), luminance(decl[`--ds-${status}-surface`]!)].sort((a, b) => b - a);
      expect((hi! + 0.05) / (lo! + 0.05), status).toBeGreaterThanOrEqual(4.5);
    }
  });

  test("a scrim for each mode", () => {
    expect(declarations(tokens, ":root")["--ds-scrim"]).toBe("rgb(23 32 27 / 40%)");
    expect(declarations(tokens, ".v-theme--dark")["--ds-scrim"]).toBe("rgb(0 0 0 / 55%)");
  });

  test("shape, depth, font, spacing and type scale", () => {
    const root = declarations(tokens, ":root");
    expect(root).toMatchObject({
      "--ds-radius-ctl": "6px",
      "--ds-radius-card": "12px",
      "--ds-radius-hero": "20px",
      "--ds-shadow-float": "0 8px 24px rgb(23 32 27 / 8%)",
      "--ds-font": "\"Bricolage Grotesque\", system-ui, sans-serif",
      "--ds-space": "8px",
    });
    const scale = ["0.8125", "0.9375", "1.0625", "1.25", "1.5", "2", "2.75", "3.5"];
    scale.forEach((size, i) => expect(root[`--ds-t-${i + 1}`]).toBe(`${size}rem`));
  });
});

describe("typography", () => {
  const typography = read("typography.css");

  test("body uses the design font", () => {
    expect(declarations(typography, "body")["font-family"]).toBe("var(--ds-font)");
  });

  test("utility classes", () => {
    expect(declarations(typography, ".ds-display")).toMatchObject({
      "font-weight": "800",
      "font-variation-settings": "\"wdth\" 85",
      "letter-spacing": "-0.03em",
    });
    expect(declarations(typography, ".ds-title")).toMatchObject({
      "font-weight": "700",
      "font-variation-settings": "\"wdth\" 92",
      "letter-spacing": "-0.02em",
    });
    expect(declarations(typography, ".ds-body")).toMatchObject({
      "font-size": "var(--ds-t-3)",
      "font-weight": "400",
      "max-width": "70ch",
    });
    expect(declarations(typography, ".ds-muted").color).toBe("var(--ds-text-2)");
    expect(declarations(typography, ".ds-focus:focus-visible").outline).toBe("2px solid var(--ds-text)");
  });
});
