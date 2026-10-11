import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Lang } from "../api/client";
import { useSim } from "../store/sim";

const MAX_MS = 60_000;                                  // the server refuses clips over 60 s (§41)

/** Radio row (§41): record (click to start, click to stop) or upload a clip → transcript lands in the text box,
 *  editable. Never parses. The clip can be played back, deleted and recorded again. */
export default function RadioInput() {
  const { t, i18n } = useTranslation();
  const set = useSim((s) => s.set);
  const run = useSim((s) => s.run);
  const busy = useSim((s) => s.busy);
  const sttPath = useSim((s) => s.sttPath);
  const health = useSim((s) => s.health);
  const [clip, setClip] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "starting" | "recording">("idle");
  const [secs, setSecs] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<number | null>(null);
  const cancelled = useRef(false);
  const canRecord = typeof window !== "undefined" && "MediaRecorder" in window && !!navigator.mediaDevices && window.isSecureContext;
  const stt = sttPath ?? health?.stt ?? null;

  function release() {
    stream.current?.getTracks().forEach((tr) => tr.stop());
    stream.current = null;
    rec.current = null;
    if (timer.current !== null) { window.clearInterval(timer.current); timer.current = null; }
  }

  function showClip(url: string | null) {
    setClip((old) => { if (old) URL.revokeObjectURL(old); return url; });
  }

  useEffect(() => () => { cancelled.current = true; rec.current?.state === "recording" && rec.current.stop(); release(); showClip(null); }, []);

  async function send(blob: Blob, name: string) {
    const r = await run("transcribe", () => api.transcribe(blob, name, (i18n.resolvedLanguage || "en") as Lang));
    if (!r) return;
    set("sttPath", r.stt_path);
    if (r.transcript) set("draftText", r.transcript);
    else set("notice", r.error === "too_long" ? t("radio.tooLong") : r.stt_path === "unavailable" ? t("radio.unavailable") : t("radio.nothingHeard"));
  }

  async function start() {
    if (state !== "idle") return;
    setState("starting");
    cancelled.current = false;
    try {
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (cancelled.current) { s.getTracks().forEach((tr) => tr.stop()); setState("idle"); return; }
      const type = ["audio/webm;codecs=opus", "audio/webm"].find((m) => MediaRecorder.isTypeSupported(m));
      const m = type ? new MediaRecorder(s, { mimeType: type }) : new MediaRecorder(s);
      stream.current = s;
      rec.current = m;
      chunks.current = [];
      m.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data); };
      m.onstop = () => {
        release();
        setState("idle");
        if (cancelled.current || !chunks.current.length) return;
        const blob = new Blob(chunks.current, { type: "audio/webm" });
        showClip(URL.createObjectURL(blob));
        void send(blob, "radio.webm");
      };
      m.start(250);
      setSecs(0);
      const t0 = Date.now();
      timer.current = window.setInterval(() => {
        const ms = Date.now() - t0;
        setSecs(Math.floor(ms / 1000));
        if (ms >= MAX_MS) stop();
      }, 250);
      setState("recording");
    } catch {
      release();
      setState("idle");
      set("notice", t("radio.noMic"));
    }
  }

  function stop() {
    if (rec.current?.state === "recording") rec.current.stop();          // onstop releases the mic and sends the clip
    else { cancelled.current = true; release(); setState("idle"); }
  }

  function remove() {
    showClip(null);
    set("sttPath", null);
  }

  const recording = state === "recording";
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">{t("radio.label")}</span>
        {canRecord && (
          <button type="button" className={`btn btn-sm ${recording ? "bg-conflict text-white" : "btn-ghost"}`}
            disabled={state === "starting" || busy === "transcribe"} aria-pressed={recording}
            onClick={() => (recording ? stop() : void start())}>
            {recording ? <>■ {t("radio.stop")} <span className="num">{secs}s</span></>
              : <>● {clip ? t("radio.again") : t("radio.record")}</>}
          </button>
        )}
        <label className={`btn btn-ghost btn-sm ${recording ? "pointer-events-none opacity-50" : "cursor-pointer"}`}>
          {t("radio.upload")}
          <input type="file" accept=".wav,.mp3,.webm,audio/*" className="sr-only" disabled={recording}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) { showClip(URL.createObjectURL(f)); void send(f, f.name); }
              e.target.value = "";
            }} />
        </label>
        <span className={`chip ${stt === "unavailable" ? "border-held/60 text-held" : ""}`}
          title={stt === "unavailable" ? t("radio.sttHelp") : undefined}>
          {t("chip.stt")} <span className="num text-ink">{busy === "transcribe" ? t("radio.transcribing") : stt ?? "—"}</span>
        </span>
      </div>
      {clip && (
        <div className="flex items-center gap-2">
          <audio controls src={clip} className="h-9 min-w-0 flex-1" />
          <button type="button" className="btn btn-ghost btn-sm" onClick={remove} disabled={recording}>{t("radio.delete")}</button>
        </div>
      )}
      {stt === "unavailable" && <p className="text-xs text-muted">{t("radio.sttHelp")}</p>}
    </div>
  );
}
