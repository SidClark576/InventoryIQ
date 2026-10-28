import { getCurrentCurrency } from "../session.ts";

const EUR = ["DE", "FR", "ES", "IT", "NL", "BE", "AT", "IE", "PT", "FI", "GR"];
export const REGION_CURRENCY: Record<string, string> = {
  PH: "PHP", US: "USD", CA: "CAD", GB: "GBP", AU: "AUD", NZ: "NZD", SG: "SGD", MY: "MYR", ID: "IDR", TH: "THB",
  VN: "VND", JP: "JPY", KR: "KRW", IN: "INR", HK: "HKD", TW: "TWD", AE: "AED", SA: "SAR", MX: "MXN", BR: "BRL",
  ...Object.fromEntries(EUR.map((region) => [region, "EUR"])),
};

// ponytail: device-region guess, no IP lookup; the store's currency (activeCurrency) wins when set.
export function currencyFor(locale: string, timeZone: string): string {
  if (timeZone === "Asia/Manila") return "PHP";
  try {
    return REGION_CURRENCY[new Intl.Locale(locale).maximize().region ?? ""] ?? "USD";
  } catch {
    return "USD";
  }
}

const LOCALE = typeof navigator === "undefined" ? "en-US" : navigator.language;
const DEVICE_CURRENCY = currencyFor(LOCALE, Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC");

/** The signed-in store's currency; a legacy user with no org keeps the device guess. */
export function activeCurrency(): string {
  return (typeof sessionStorage === "undefined" ? "" : getCurrentCurrency()) || DEVICE_CURRENCY;
}

export function currencySymbol(currency = activeCurrency()): string {
  return new Intl.NumberFormat(LOCALE, { style: "currency", currency }).formatToParts(0).find((part) => part.type === "currency")?.value ?? currency;
}

export function formatMoney(value: number, currency = activeCurrency()): string {
  return new Intl.NumberFormat(LOCALE, { style: "currency", currency }).format(Number.isFinite(value) ? value : 0);
}

export function formatCompactMoney(value: number, currency = activeCurrency()): string {
  return new Intl.NumberFormat(LOCALE, { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(
    Number.isFinite(value) ? value : 0,
  );
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
