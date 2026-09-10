import { useCallback, useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import type { EditableSegment } from "./api";

const NORMAL = "rgba(79, 140, 255, 0.30)";
const SELECTED = "rgba(63, 185, 112, 0.45)";
const ENGINE_URL = "http://127.0.0.1:8741";

interface WsRegion {
  id: string;
  start: number;
  end: number;
  setOptions(opts: { start?: number; end?: number; color?: string }): void;
  remove(): void;
}

interface Props {
  jobId: string;
  segments: EditableSegment[];
  selectedIndex: number | null;
  onChange: (index: number, start: number, end: number) => void;
  onSelect: (index: number) => void;
}

type DragMode = "move" | "resize-start" | "resize-end";

interface DragState {
  index: number;
  mode: DragMode;
  grabOffset: number;   // seconds between segment.start and pointer at down
  startX: number;
  origStart: number;
  origEnd: number;
  width: number;
}

export default function Timeline({ jobId, segments, selectedIndex, onChange, onSelect }: Props) {
  const waveContainerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const [duration, setDuration] = useState(0);
  const [drag, setDrag] = useState<DragState | null>(null);
  const dragRef = useRef<DragState | null>(null);
  dragRef.current = drag;
  const segsRef = useRef(segments);
  segsRef.current = segments;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // create wavesurfer per job (render only; interactions are our own overlay)
  useEffect(() => {
    const container = waveContainerRef.current;
    if (!container) return;
    const ws = WaveSurfer.create({
      container,
      url: `${ENGINE_URL}/jobs/${jobId}/audio`,
      waveColor: "#3a4360",
      progressColor: "#4f8cff",
      cursorWidth: 1,
      height: 96,
      normalize: true,
    });
    wsRef.current = ws;
    ws.on("decode", () => setDuration(ws.getDuration() || 0));
    return () => {
      ws.destroy();
      wsRef.current = null;
    };
  }, [jobId]);

  const commit = useCallback((index: number, start: number, end: number) => {
    onChangeRef.current(index, Number(start.toFixed(3)), Number(end.toFixed(3)));
  }, []);

  const onBlockPointerDown = useCallback(
    (e: React.PointerEvent, index: number, mode: DragMode) => {
      e.stopPropagation();
      e.preventDefault();
      const seg = segsRef.current[index];
      if (!seg) return;
      const width = (e.currentTarget as HTMLElement).parentElement?.clientWidth ?? 1;
      const pxPerSec = width / (duration || 1);
      setDrag({
        index,
        mode,
        grabOffset: mode === "move" ? (e.clientX - (e.currentTarget as HTMLElement).getBoundingClientRect().x) / pxPerSec : 0,
        startX: e.clientX,
        origStart: seg.start,
        origEnd: seg.end,
        width,
      });
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      onSelect(index);
    },
    [duration]
  );

  // live drag via window listeners (pointer capture keeps events on the block)
  useEffect(() => {
    if (!drag) return;
    const pxToSec = (dx: number) => (drag.width ? (dx / drag.width) * duration : 0);
    const onMove = (e: PointerEvent) => {
      const seg = segsRef.current[drag.index];
      if (!seg) return;
      const delta = pxToSec(e.clientX - drag.startX);
      let start = seg.start;
      let end = seg.end;
      if (drag.mode === "move") {
        const shift = pxToSec(e.clientX - drag.startX);
        start = drag.origStart + shift;
        end = drag.origEnd + shift;
      } else if (drag.mode === "resize-start") {
        start = Math.min(Math.max(drag.origStart + delta, 0), seg.end - 0.05);
      } else {
        end = Math.max(drag.origEnd + delta, seg.start + 0.05);
      }
      // commit into editor state live (round to ms)
      onChangeRef.current(drag.index, Number(start.toFixed(3)), Number(end.toFixed(3)));
    };
    const onUp = () => setDrag(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [drag, duration]);

  const preview = useCallback((index: number) => {
    const seg = segsRef.current[index];
    wsRef.current?.play(seg.start, seg.end);
  }, []);

  return (
    <div>
      <div style={{ position: "relative" }}>
        <div ref={waveContainerRef} />
        {/* subtitle blocks overlay */}
        <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
          {segments.map((s, i) => {
            if (!duration) return null;
            const left = (s.start / duration) * 100;
            const width = Math.max(((s.end - s.start) / duration) * 100, 0.3);
            const selected = i === selectedIndex;
            const isDrag = drag?.index === i;
            return (
              <div
                key={i}
                data-seg={i}
                onPointerDown={(e) => onBlockPointerDown(e, i, "move")}
                onDoubleClick={() => preview(i)}
                style={{
                  position: "absolute",
                  left: `${left}%`,
                  width: `${width}%`,
                  top: 4,
                  height: 88,
                  background: selected ? SELECTED : NORMAL,
                  border: `1px solid ${selected ? "#3fb970" : "rgba(79,140,255,0.8)"}`,
                  borderRadius: 4,
                  cursor: "grab",
                  touchAction: "none",
                  pointerEvents: "auto",
                  zIndex: isDrag ? 5 : 1,
                }}
                title={s.text}
              >
                <div
                  onPointerDown={(e) => { e.stopPropagation(); onBlockPointerDown(e, i, "resize-start"); }}
                  style={{ position: "absolute", left: 0, top: 0, width: 6, height: "100%", cursor: "ew-resize" }}
                />
                <div
                  onPointerDown={(e) => { e.stopPropagation(); onBlockPointerDown(e, i, "resize-end"); }}
                  style={{ position: "absolute", right: 0, top: 0, width: 6, height: "100%", cursor: "ew-resize" }}
                />
              </div>
            );
          })}
        </div>
      </div>
      <p className="muted" style={{ marginBottom: 0 }}>
        时间轴：拖动区块移动时间、拖左右边缘调整起止、双击区块试听。修改后记得「保存修改」。
      </p>
    </div>
  );
}
