import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { canEditRole, inCurrentOrg } from "../../../frontend/src/lib/org-shell.ts";

describe("canEditRole", () => {
  test("viewers can't edit or delete", () => {
    assert.equal(canEditRole("viewer", 2), false);
  });
  test("editor, admin and owner can", () => {
    for (const role of ["editor", "admin", "owner"]) assert.equal(canEditRole(role, 1), true);
  });
  test("no role: legacy mode (no orgs) edits, a missing role inside orgs does not", () => {
    assert.equal(canEditRole(undefined, 0), true);
    assert.equal(canEditRole("", 0), true);
    assert.equal(canEditRole("", 1), false);
  });
});

describe("inCurrentOrg", () => {
  test("open while the org is unchanged", () => {
    assert.equal(inCurrentOrg({ value: "report", orgEpoch: 3 }, 3), "report");
  });
  test("an org switch closes it", () => {
    assert.equal(inCurrentOrg({ value: "report", orgEpoch: 3 }, 4), null);
  });
  test("nothing open stays closed", () => {
    assert.equal(inCurrentOrg(null, 0), null);
  });
});
