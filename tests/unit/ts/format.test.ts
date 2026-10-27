import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { currencyFor, formatCompactMoney, formatMoney } from "../../../frontend/src/lib/format.ts";

describe("currencyFor", () => {
  test("Manila time zone means pesos whatever the language", () => {
    assert.equal(currencyFor("en-US", "Asia/Manila"), "PHP");
  });
  test("falls back to the locale region", () => {
    assert.equal(currencyFor("en-US", "America/New_York"), "USD");
    assert.equal(currencyFor("de-DE", "Europe/Berlin"), "EUR");
    assert.equal(currencyFor("fil", "UTC"), "PHP");
  });
  test("unknown locale and zone fall back to USD", () => {
    assert.equal(currencyFor("xx", "Etc/Unknown"), "USD");
    assert.equal(currencyFor("not a locale!", "UTC"), "USD");
  });
});

describe("formatMoney", () => {
  test("prints the currency symbol", () => {
    assert.match(formatMoney(1234.5, "PHP"), /₱1,234\.50|1\.234,50\s₱/);
    assert.match(formatCompactMoney(12345, "PHP"), /₱12\.3K|12,3\s*K\s₱/);
  });
  test("non-finite values print as zero", () => {
    assert.match(formatMoney(Number.NaN, "USD"), /0\.00|0,00/);
  });
});
