export function localTime(iso?: string | null, withSeconds = false) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString("en-GB", {
      hour: "2-digit", minute: "2-digit", ...(withSeconds ? { second: "2-digit" } : {}), timeZone: "Asia/Dubai",
    });
  } catch {
    return iso;
  }
}

export function minutesLeft(iso?: string | null) {
  if (!iso) return null;
  return Math.round((new Date(iso).getTime() - Date.now()) / 60000);
}

export const titleCase = (s?: string | null) =>
  (s ?? "").toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

/** Plain-language versions of technical outcomes (shown by default; details on expand). */
export function plain(code?: string | null, ctx: Record<string, string> = {}) {
  switch (code) {
    case "VERSION_MISMATCH":
    case "STALE":
      return `Another flight took Gate ${ctx.gate ?? "B07"}. The previous approval is no longer valid.`;
    case "ESCALATED":
      return `Batch ${ctx.batch ?? "3"} failed. Previous successful batches were preserved.`;
    case "INVALID":
      return "The engineer's sign-off could not be verified. Departure remains blocked.";
    case "ILLEGAL":
      return "Departure blocked — current crew not legally available.";
    default:
      return code ?? "";
  }
}
