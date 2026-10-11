import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Lang } from "../api/client";
import { useSim } from "../store/sim";

/** Radio row (§41): upload a clip or hold to record → transcript lands in the text box, editable. Never parses. */
export default function RadioInput() {
  const { t, i18n } = useTranslation();
  const set = useSim((s) => s.set);
  const run = useSim((s) => s.run);
  const sttPath = useSim((s) => s.sttPath);
  const health = useSim((s) => s.health);
  const [clip, setClip] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const canRecord = typeof window !== "undefined" && "MediaRecorder" in window && !!navigator.mediaDevices && window.isSecureContext;

  async function send(blob: Blob, name: string) {
    const r = await run("transcribe", () => api.transcribe(blob, name, (i18n.resolvedLanguage || "en") as Lang));
    if (!r) return;
    set("sttPath", r.stt_path);
    if (r.transcript) set("draftText", r.transcript);
    else set("notice", t("radio.unavailable"));
  }

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const m = new MediaRecorder(stream);
      chunks.current = [];
      m.ondataavailable = (e) => chunks.current.push(e.data);
      m.onstop = () => {
        stream.getTracks().forEach((tr) => tr.stop());
        const blob = new Blob(chunks.current, { type: "audio/webm" });
        setClip(URL.createObjectURL(blob));
        void send(blob, "radio.webm");
      };
      m.start();
      rec.current = m;
      setRecording(true);
    } catch {
      set("notice", t("radio.noMic"));
    }
  }

  function stop() {
    rec.current?.stop();
    rec.current = null;
    setRecording(false);
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">{t("radio.label")}</span>
        {canRecord && (
          <button type="button" className={`btn btn-sm ${recording ? "bg-conflict text-white" : "btn-ghost"}`}
            onPointerDown={() => void start()} onPointerUp={stop} onPointerLeave={() => recording && stop()}
            aria-pressed={recording}>
            ● {recording ? t("radio.recording") : t("radio.hold")}
          </button>
        )}
        <label className="btn btn-ghost btn-sm cursor-pointer">
          {t("radio.upload")}
          <input type="file" accept=".wav,.mp3,.webm,audio/*" className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) { setClip(URL.createObjectURL(f)); void send(f, f.name); }
              e.target.value = "";
            }} />
        </label>
        <span className={`chip ${(sttPath ?? health?.stt) === "unavailable" ? "border-held/60 text-held" : ""}`}>
          {t("chip.stt")} <span className="num text-ink">{sttPath ?? health?.stt ?? "—"}</span>
        </span>
      </div>
      {clip && <audio controls src={clip} className="h-9 w-full" />}
    </div>
  );
}
