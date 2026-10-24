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

  test("utility classes exist", () => {
    expect(declarations(typography, ".ds-display")).toMatchObject({ "font-weight": "800", "letter-spacing": "-0.03em" });
    expect(declarations(typography, ".ds-title")).toMatchObject({ "font-weight": "700", "letter-spacing": "-0.02em" });
    expect(declarations(typography, ".ds-muted").color).toBe("var(--ds-text-2)");
    for (const cls of [".ds-body", ".ds-focus:focus-visible"])
      expect(() => declarations(typography, cls)).not.toThrow();
  });
});
