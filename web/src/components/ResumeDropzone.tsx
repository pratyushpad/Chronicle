"use client";
import { useCallback, useRef, useState } from "react";
import { m, AnimatePresence, useReducedMotion } from "motion/react";
import { cn, formatNumber } from "@/lib/utils";
import { duration, ease } from "@/lib/motion";

interface ResumeInfo {
  resume_chars: number | null;
  resume_updated_at: string | null;
}

interface Props extends ResumeInfo {
  /** Called with the new resume state after a successful upload or removal. */
  onChange: (info: ResumeInfo) => void;
}

type Status = "idle" | "dragging" | "working" | "success" | "error";

const btnOutline =
  "inline-flex min-h-[36px] items-center justify-center border border-foreground px-5 font-mono text-xs uppercase tracking-[0.12em] text-foreground transition-colors duration-100 hover:bg-foreground hover:text-background disabled:opacity-50 cursor-pointer";
const labelCls = "font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground";

/**
 * Drag-and-drop resume dropzone with idle / dragging / working / success / error
 * states. Reuses the existing POST/DELETE /api/user/resume endpoints unchanged — the
 * API returns a character count (not a skill count), so the success reveal surfaces
 * "Extracted N characters". Motion is transform/opacity only; reduced-motion falls back
 * to plain fades.
 */
export function ResumeDropzone({ resume_chars, resume_updated_at, onChange }: Props) {
  const reduce = useReducedMotion();
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [extracted, setExtracted] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const upload = useCallback(
    async (file: File) => {
      setStatus("working");
      setMessage(`Reading ${file.name}…`);
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/user/resume", { method: "POST", body: form });
      if (res.ok) {
        const d = await res.json();
        onChange({ resume_chars: d.resume_chars, resume_updated_at: d.resume_updated_at });
        setExtracted(d.resume_chars ?? null);
        setStatus("success");
        setMessage("");
      } else {
        const d = await res.json().catch(() => null);
        setStatus("error");
        setMessage(d?.detail ?? "Upload failed.");
      }
    },
    [onChange]
  );

  const remove = useCallback(async () => {
    setStatus("working");
    setMessage("");
    const res = await fetch("/api/user/resume", { method: "DELETE" });
    if (res.ok) {
      onChange({ resume_chars: null, resume_updated_at: null });
      setExtracted(null);
      setStatus("idle");
    } else {
      setStatus("error");
      setMessage("Remove failed.");
    }
  }, [onChange]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setStatus("idle");
    if (status === "working") return;
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  };

  const working = status === "working";
  const hasResume = !!resume_chars;

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!working && status !== "dragging") setStatus("dragging");
        }}
        onDragLeave={(e) => {
          // Ignore leaves onto child nodes — only reset when the pointer exits the box.
          if (!e.currentTarget.contains(e.relatedTarget as Node)) {
            setStatus((s) => (s === "dragging" ? "idle" : s));
          }
        }}
        onDrop={onDrop}
        onClick={() => !working && inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !working) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        aria-label={hasResume ? "Replace resume" : "Upload resume"}
        className={cn(
          "relative flex min-h-[132px] cursor-pointer flex-col items-center justify-center gap-2 border-2 border-dashed p-6 text-center transition-colors duration-100 focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-foreground focus-visible:outline-offset-2",
          status === "dragging" ? "border-foreground bg-muted" : "border-border-light hover:border-foreground"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,application/pdf,text/plain"
          className="hidden"
          disabled={working}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) upload(f);
            e.target.value = "";
          }}
        />

        {working ? (
          <m.span
            className={`${labelCls} text-foreground`}
            animate={reduce ? undefined : { opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 1.2, ease, repeat: Infinity }}
          >
            {message || "Working…"}
          </m.span>
        ) : (
          <>
            <span className="font-body text-sm text-foreground">
              {status === "dragging" ? "Drop to upload" : hasResume ? "Drop a new file, or click to replace" : "Drop your resume, or click to browse"}
            </span>
            <span className={labelCls}>PDF or .txt — we keep only the extracted text, never the file</span>
          </>
        )}
      </div>

      {/* Current state + success/error reveals */}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {hasResume && !working && (
          <span className="font-body text-sm text-foreground">
            Resume on file ({formatNumber(resume_chars as number)} characters
            {resume_updated_at && `, updated ${new Date(resume_updated_at).toLocaleDateString()}`})
          </span>
        )}
        {hasResume && !working && (
          <button onClick={remove} disabled={working} className={btnOutline} type="button">
            Remove
          </button>
        )}
      </div>

      <AnimatePresence mode="wait">
        {status === "success" && extracted != null && (
          <m.p
            key="success"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: duration.base, ease }}
            className="mt-3 font-mono text-[10px] uppercase tracking-[0.15em] text-foreground"
          >
            ✓ Extracted {formatNumber(extracted)} characters — matching updated
          </m.p>
        )}
        {status === "error" && (
          <m.p
            key="error"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: duration.base, ease }}
            className="mt-3 font-mono text-[10px] uppercase tracking-[0.15em] text-foreground"
          >
            {message}
          </m.p>
        )}
      </AnimatePresence>
    </div>
  );
}
