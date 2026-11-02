import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, mock, test } from "node:test";
import { createQuantityQueue } from "../../../frontend/src/lib/quantity-queue.ts";

const settle = () => new Promise((resolve) => setImmediate(resolve));

describe("createQuantityQueue", () => {
  beforeEach(() => mock.timers.enable({ apis: ["setTimeout"] }));
  afterEach(() => mock.timers.reset());

  test("taps on one item merge into one save after the last tap", async () => {
    const saves: number[] = [];
    const queue = createQuantityQueue(() => {}, 1000);
    const save = async (delta: number) => (saves.push(delta), true);
    queue.tap("a", -1, "step", save);
    mock.timers.tick(900);
    queue.tap("a", -1, "step", save);
    queue.tap("a", -1, "step", save);
    assert.equal(queue.unsent("a"), -3);
    mock.timers.tick(999);
    assert.deepEqual(saves, []);
    mock.timers.tick(1);
    await settle();
    assert.deepEqual(saves, [-3]);
    assert.equal(queue.unsent("a"), 0);
    assert.equal(queue.isPending("a"), false);
  });

  test("a tap with another reason saves the open batch first", async () => {
    const saves: string[] = [];
    const queue = createQuantityQueue(() => {}, 1000);
    queue.tap("a", -2, "Waste", async (d) => (saves.push(`Waste ${d}`), true));
    queue.tap("a", 1, "step", async (d) => (saves.push(`step ${d}`), true));
    await settle();
    assert.deepEqual(saves, ["Waste -2"]);
    mock.timers.tick(1000);
    await settle();
    assert.deepEqual(saves, ["Waste -2", "step 1"]);
  });

  test("the item stays pending while its save is in flight (reloads keep the cached row)", async () => {
    let finish: (ok: boolean) => void = () => {};
    const queue = createQuantityQueue(() => {}, 1000);
    queue.tap("a", 1, "step", () => new Promise<boolean>((resolve) => (finish = resolve)));
    mock.timers.tick(1000);
    await settle();
    assert.equal(queue.isPending("a"), true);
    finish(true);
    await settle();
    assert.equal(queue.isPending("a"), false);
  });

  test("a failed save drops the taps that have not been sent", async () => {
    const saves: number[] = [];
    let fail: (ok: boolean) => void = () => {};
    const queue = createQuantityQueue(() => {}, 1000);
    queue.tap("a", -1, "step", () => new Promise<boolean>((resolve) => (fail = resolve)));
    mock.timers.tick(1000);
    await settle();
    queue.tap("a", -1, "Waste", async (d) => (saves.push(d), true));
    queue.tap("a", -1, "step", async (d) => (saves.push(d), true)); // flushes the Waste batch behind the in-flight save
    fail(false);
    await settle();
    mock.timers.tick(1000);
    await settle();
    assert.deepEqual(saves, []);
    assert.equal(queue.unsent("a"), 0);
    assert.equal(queue.isPending("a"), false);
  });

  test("cancel then run: pending taps are dropped and the run waits for the in-flight save", async () => {
    const order: string[] = [];
    let finish: (ok: boolean) => void = () => {};
    const queue = createQuantityQueue(() => {}, 1000);
    queue.tap("a", 1, "step", () => new Promise<boolean>((resolve) => (finish = resolve)).then((ok) => (order.push("first"), ok)));
    mock.timers.tick(1000);
    await settle();
    queue.tap("a", 1, "step", async () => (order.push("tap"), true));
    queue.cancel("a");
    void queue.run("a", async () => order.push("undo"));
    finish(true);
    await settle();
    mock.timers.tick(1000);
    await settle();
    assert.deepEqual(order, ["first", "undo"]);
  });

  test("replace drops unsent taps and keeps the item pending until its task is done (Undo keeps the server row)", async () => {
    const saves: number[] = [];
    const pendingSeen: boolean[] = [];
    const queue = createQuantityQueue((id) => pendingSeen.push(queue.isPending(id)), 1000);
    queue.tap("a", -1, "step", async (d) => (saves.push(d), true));
    let ran = false;
    void queue.replace("a", async () => {
      ran = true;
      assert.equal(queue.isPending("a"), true);
    });
    assert.equal(queue.unsent("a"), 0);
    assert.ok(pendingSeen.every(Boolean), "the store forgets the server row whenever onChange sees not-pending");
    await settle();
    mock.timers.tick(1000);
    await settle();
    assert.equal(ran, true);
    assert.deepEqual(saves, []);
    assert.equal(queue.isPending("a"), false);
    assert.equal(pendingSeen.at(-1), false);
  });

  test("tappedSince tells a reload which items were touched after it started, even once their save settled", async () => {
    const queue = createQuantityQueue(() => {}, 1000);
    queue.tap("old", 1, "step", async () => true);
    const mark = queue.mark();
    queue.tap("a", 1, "step", async () => true);
    void queue.replace("b", async () => {});
    mock.timers.tick(1000);
    await settle();
    assert.equal(queue.isPending("a"), false);
    assert.deepEqual(["old", "a", "b", "none"].map((id) => queue.tappedSince(id, mark)), [false, true, true, false]);
  });

  test("onChange reports each id whose pending state may have changed", async () => {
    const seen: string[] = [];
    const queue = createQuantityQueue((id) => seen.push(id), 1000);
    queue.tap("a", 1, "step", async () => true);
    mock.timers.tick(1000);
    await settle();
    assert.ok(seen.length >= 2 && seen.every((id) => id === "a"));
  });
});
