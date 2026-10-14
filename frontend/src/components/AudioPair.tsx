import { useEffect, useRef } from "react";
import type { Detection } from "../types";

interface Props {
  referenceUrl: string | null;
  participantUrl: string | null;
  selected: Detection | null;
}

export default function AudioPair({ referenceUrl, participantUrl, selected }: Props) {
  const refEl = useRef<HTMLAudioElement>(null);
  const parEl = useRef<HTMLAudioElement>(null);

  // When a detection is selected, move both players to the start of its
  // (independent) reference/participant intervals. Manual seek — no claim of
  // automatic synced playback.
  useEffect(() => {
    if (!selected) return;
    if (refEl.current && Number.isFinite(selected.reference_start)) {
      refEl.current.currentTime = Math.max(0, selected.reference_start);
    }
    if (parEl.current && Number.isFinite(selected.participant_start)) {
      parEl.current.currentTime = Math.max(0, selected.participant_start);
    }
  }, [selected]);

  return (
    <div className="grid cols-2">
      <div className="card">
        <div className="k" style={{ color: "var(--ref)" }}>Reference</div>
        {referenceUrl ? (
          <audio ref={refEl} controls preload="metadata" src={referenceUrl} />
        ) : (
          <div className="muted small">No reference audio available.</div>
        )}
        {selected && referenceUrl && (
          <button className="secondary small" style={{ marginTop: 8 }}
            onClick={() => { if (refEl.current) refEl.current.currentTime = Math.max(0, selected.reference_start); }}>
            Jump to {selected.reference_start.toFixed(2)}s
          </button>
        )}
      </div>
      <div className="card">
        <div className="k" style={{ color: "var(--par)" }}>Participant</div>
        {participantUrl ? (
          <audio ref={parEl} controls preload="metadata" src={participantUrl} />
        ) : (
          <div className="muted small">No participant audio available.</div>
        )}
        {selected && participantUrl && (
          <button className="secondary small" style={{ marginTop: 8 }}
            onClick={() => { if (parEl.current) parEl.current.currentTime = Math.max(0, selected.participant_start); }}>
            Jump to {selected.participant_start.toFixed(2)}s
          </button>
        )}
      </div>
    </div>
  );
}
