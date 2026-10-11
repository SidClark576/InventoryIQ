const MONEY = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" });

export function formatMoney(value: number): string {
  return MONEY.format(Number.isFinite(value) ? value : 0);
}

export function formatCompactMoney(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 10_000) return `$${(value / 1000).toFixed(1)}k`;
  return formatMoney(value);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}
