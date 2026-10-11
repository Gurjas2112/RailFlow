// Integer minutes since 00:00 ⇄ HH:MM. Times are always 24-hour and never translated (§37).
export const hhmm = (m: number | null | undefined): string => {
  if (m === null || m === undefined || Number.isNaN(m)) return "—";
  const x = Math.max(0, Math.min(1439, Math.floor(m)));
  return `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
};

export const toMin = (s: string): number | null => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return null;
  const h = Number(m[1]), mi = Number(m[2]);
  return h <= 23 && mi <= 59 ? h * 60 + mi : null;
};

export const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
