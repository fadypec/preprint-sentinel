/**
 * Sanitize user input for PostgreSQL to_tsquery.
 * Strips characters that would break query parsing, joins terms with &.
 */
export function buildSearchQuery(raw: string): string {
  const cleaned = raw
    .replace(/[^\w\s-]/g, "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (cleaned.length === 0) return "";
  return cleaned.map((term) => `${term}:*`).join(" & ");
}
