import assert from "node:assert/strict";
import { describe, test } from "node:test";
import {
  deltaOf,
  groupByDay,
  historyFor,
  isWasteNote,
  matchesFilter,
  matchesSearch,
  timeAgo,
  type Transaction,
} from "../../../frontend/src/lib/activity.ts";

const rows: Transaction[] = [
  { itemID: "a", itemName: "Oat milk", changeType: "stock_out", quantityDelta: -2, notes: "Waste: 2", createdAt: "2026-10-11T15:00:00" },
  { itemID: "b", itemName: "Cups", changeType: "stock_in", quantityDelta: 12, notes: "Received 12", createdAt: "2026-10-11T09:00:00" },
  { itemID: "a", itemName: "Oat milk", changeType: "update", quantityDelta: 0, notes: "", createdAt: "2026-10-10T18:00:00" },
  { itemID: "c", itemName: "Lids", changeType: "stock_out", quantityBefore: "5", quantityAfter: "4", notes: "Damaged: 1", createdAt: "2026-10-03T08:00:00" },
];

describe("activity filters", () => {
  test("waste and damage match on the note prefix only", () => {
    assert.equal(isWasteNote("Waste: 2"), true);
    assert.equal(isWasteNote("damaged"), true);
    assert.equal(isWasteNote("Used 3"), false);
    assert.equal(isWasteNote(undefined), false);
  });

  test("maps change types onto the five filters", () => {
    const pick = (filter: Parameters<typeof matchesFilter>[1]) =>
      rows.filter((row) => matchesFilter(row, filter)).length;
    assert.deepEqual(
      [pick("all"), pick("in"), pick("out"), pick("waste"), pick("edits")],
      [4, 1, 2, 2, 1],
    );
  });

  test("searches item names and notes", () => {
    assert.equal(rows.filter((row) => matchesSearch(row, "received")).length, 1);
    assert.equal(rows.filter((row) => matchesSearch(row, "  ")).length, 4);
  });
});

describe("deltaOf", () => {
  test("uses quantityDelta, else after minus before", () => {
    assert.equal(deltaOf(rows[0]!), -2);
    assert.equal(deltaOf(rows[3]!), -1);
    assert.equal(deltaOf({}), 0);
  });
});

describe("groupByDay", () => {
  test("groups consecutive rows by local day with friendly labels", () => {
    const groups = groupByDay(rows, new Date("2026-10-11T20:00:00"));
    assert.deepEqual(groups.map((group) => [group.label, group.rows.length]).slice(0, 2), [
      ["Today", 2],
      ["Yesterday", 1],
    ]);
    assert.equal(groups.length, 3);
  });
});

describe("historyFor / timeAgo", () => {
  test("filters by itemID", () => {
    assert.equal(historyFor(rows, "a").length, 2);
  });

  test("formats relative time", () => {
    const now = new Date("2026-10-11T15:30:00");
    assert.equal(timeAgo("2026-10-11T15:00:00", now), "30m ago");
    assert.equal(timeAgo("2026-10-11T09:00:00", now), "7h ago");
    assert.equal(timeAgo("not a date", now), "");
  });
});
