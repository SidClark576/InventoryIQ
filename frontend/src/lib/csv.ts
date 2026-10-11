// Text starting with these is run as a formula by Excel/Sheets; a leading ' keeps it as text.
const FORMULA_START = /^[=+\-@\t\r]/;

function escapeCell(value: unknown): string {
  const raw = value === null || value === undefined ? "" : String(value);
  const text = typeof value === "string" && FORMULA_START.test(raw) ? `'${raw}` : raw;
  return `"${text.replace(/"/g, '""')}"`;
}

export function toCsv(headers: readonly string[], rows: readonly (readonly unknown[])[]): string {
  return [headers.join(","), ...rows.map((row) => row.map(escapeCell).join(","))].join("\n");
}

/** Splits one CSV line, honouring double-quoted cells and "" escapes. */
function splitLine(line: string): string[] {
  const cells: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quoted && ch === '"' && line[i + 1] === '"') {
      cell += '"';
      i += 1;
    } else if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      cells.push(cell.trim());
      cell = "";
    } else {
      cell += ch;
    }
  }
  return [...cells, cell.trim()];
}

/** Header row becomes keys; blank lines are skipped. */
export function parseCsv(text: string): Record<string, string>[] {
  const lines = text.replace(/\r/g, "").split("\n").filter((line) => line.trim() !== "");
  const [headerLine, ...body] = lines;
  if (!headerLine) return [];
  const header = splitLine(headerLine);
  return body.map((line) => {
    const values = splitLine(line);
    return Object.fromEntries(header.map((key, index) => [key, values[index] ?? ""]));
  });
}
