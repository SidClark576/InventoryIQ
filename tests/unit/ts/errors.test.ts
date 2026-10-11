import assert from "node:assert/strict";
import { test } from "node:test";
import { errorText } from "../../../frontend/src/lib/errors.ts";

test("errorText uses the Error message, else the fallback", () => {
  assert.equal(errorText(new Error("Boom"), "Fallback"), "Boom");
  assert.equal(errorText(new Error(""), "Fallback"), "Fallback");
  assert.equal(errorText("not an error", "Fallback"), "Fallback");
  assert.equal(errorText(null), "");
});
