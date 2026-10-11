// SPEC §20.9 — locale completeness: every en key exists in hi and mr with the same interpolation variables,
// and every static t("key") used in the source exists in en.json.
import { describe, expect, it } from "vitest";
import en from "../public/locales/en.json";
import hi from "../public/locales/hi.json";
import mr from "../public/locales/mr.json";

type Dict = Record<string, string>;
const vars = (s: string) => [...s.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();
const sources = import.meta.glob("./**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

describe.each([["hi", hi as Dict], ["mr", mr as Dict]])("%s locale", (_name, dict) => {
  it("has exactly the English keys", () => {
    expect(Object.keys(dict).sort()).toEqual(Object.keys(en as Dict).sort());
  });
  it("keeps the same interpolation variables for every key", () => {
    for (const [k, v] of Object.entries(en as Dict)) expect(vars(dict[k] ?? ""), k).toEqual(vars(v));
  });
  it("never leaves a value empty unless English is empty", () => {
    for (const [k, v] of Object.entries(en as Dict)) if (v) expect(dict[k], k).not.toBe("");
  });
});

describe("source strings", () => {
  it("every static t(\"key\") exists in en.json", () => {
    const missing: string[] = [];
    for (const [file, src] of Object.entries(sources)) {
      if (file.endsWith(".test.ts")) continue;
      for (const m of src.matchAll(/\bt\(\s*"([^"$`{}]+)"/g)) if (!(m[1] in (en as Dict))) missing.push(`${file}: ${m[1]}`);
      for (const m of src.matchAll(/\bkey:\s*"([a-z]+\.[A-Za-z.]+)"/g)) if (!(m[1] in (en as Dict))) missing.push(`${file}: ${m[1]}`);
    }
    expect(missing).toEqual([]);
  });

  it("digits stay Western Arabic in every language (§37)", () => {
    for (const dict of [hi, mr] as Dict[]) for (const [k, v] of Object.entries(dict)) expect(/[०-९]/.test(v), k).toBe(false);
  });
});
