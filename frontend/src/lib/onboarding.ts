import type { InventoryItem, OrgSwitchResponse } from "@/api";
import { REGION_CURRENCY } from "./format.ts";

/** Signup creates every store as "My Inventory" (Authentication.mjs, migrate_orgs.py); only its owner is asked to name it. */
export const DEFAULT_STORE_NAME = "My Inventory";

export function needsOnboarding(org: OrgSwitchResponse): boolean {
  return org.role === "owner" && org.name === DEFAULT_STORE_NAME && !org.onboardedAt;
}

export const STORE_TYPES = [
  { value: "sari-sari", label: "Sari-sari store" },
  { value: "grocery", label: "Grocery" },
  { value: "pharmacy", label: "Pharmacy" },
  { value: "hardware", label: "Hardware" },
  { value: "other", label: "Other" },
] as const;

const regionName = new Intl.DisplayNames(["en"], { type: "region" });

/** Countries with a known currency, by display name; PH first. */
export const COUNTRIES = Object.entries(REGION_CURRENCY)
  .map(([code, currency]) => ({ code, currency, label: regionName.of(code) ?? code }))
  .sort((a, b) => (a.code === "PH" ? -1 : b.code === "PH" ? 1 : a.label.localeCompare(b.label)));

/** Runs `add` one item at a time (no burst against quota/throttling), keeps going past failures, returns the failed items. */
export async function addInOrder<T>(
  items: readonly T[],
  add: (item: T) => Promise<unknown>,
  onProgress: (n: number) => void,
): Promise<T[]> {
  const failed: T[] = [];
  for (const [idx, item] of items.entries()) {
    onProgress(idx + 1);
    try {
      await add(item);
    } catch {
      failed.push(item);
    }
  }
  return failed;
}

/** `null` = the items load failed. Never offer starter items when unsure. */
export function skipStarterItems(existing: readonly InventoryItem[] | null): boolean {
  return existing === null || existing.length > 0;
}

/** existing: active items found before onboarding; null when the load failed. */
export function doneText(added: number, existing: number | null): string {
  if (existing === null) return "Find your items in Stock.";
  if (existing > 0) return `You already have ${existing} ${existing === 1 ? "item" : "items"}. Find them in Stock.`;
  return added ? `Added ${added} items. Count them and set prices in Stock.` : "Add items from Stock whenever you're ready.";
}
