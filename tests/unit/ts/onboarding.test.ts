import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { activeCurrency } from "../../../frontend/src/lib/format.ts";
import { addInOrder, needsOnboarding } from "../../../frontend/src/lib/onboarding.ts";
import { DEEP_LINK_DIALOGS, dialogFromParams } from "../../../frontend/src/screens/stock/stock-view.ts";

describe("needsOnboarding", () => {
  test("only an owner of the default-named, never-onboarded store", () => {
    assert.equal(needsOnboarding({ orgID: "o", role: "owner", name: "My Inventory" }), true);
    assert.equal(needsOnboarding({ orgID: "o", role: "editor", name: "My Inventory" }), false);
    assert.equal(needsOnboarding({ orgID: "o", role: "owner", name: "SC3 Store" }), false);
    assert.equal(needsOnboarding({ orgID: "o", role: "owner", name: "My Inventory", onboardedAt: "2026-10-28" }), false);
  });
});

describe("activeCurrency", () => {
  test("no session (legacy, no org) keeps the device guess", () => {
    assert.match(activeCurrency(), /^[A-Z]{3}$/);
  });
  test("the store's currency wins over the device guess", () => {
    const store = new Map([["currentCurrency", "JPY"]]);
    Object.assign(globalThis, { sessionStorage: { getItem: (k: string) => store.get(k) ?? null } });
    try {
      assert.equal(activeCurrency(), "JPY");
    } finally {
      Reflect.deleteProperty(globalThis, "sessionStorage");
    }
  });
});

describe("addInOrder", () => {
  test("adds one at a time, reports progress, keeps going past failures and returns them", async () => {
    let running = 0;
    const progress: number[] = [];
    const failed = await addInOrder(
      ["a", "b", "c"],
      async (item) => {
        running += 1;
        assert.equal(running, 1, "never more than one add in flight");
        await new Promise((resolve) => setTimeout(resolve, 1));
        running -= 1;
        if (item === "b") throw new Error("throttled");
      },
      (n) => progress.push(n),
    );
    assert.deepEqual(failed, ["b"]);
    assert.deepEqual(progress, [1, 2, 3]);
  });
});

describe("dialogFromParams", () => {
  test("opens scan or import from the onboarding deep links only", () => {
    assert.equal(dialogFromParams(new URLSearchParams("scan=1")), "scan");
    assert.equal(dialogFromParams(new URLSearchParams("import=1&q=x")), "import");
    assert.equal(dialogFromParams(new URLSearchParams("scan=0&new=1")), null);
    assert.deepEqual([...DEEP_LINK_DIALOGS], ["scan", "import"]);
  });
});
