import { useCallback, useEffect, useRef, useState } from "react";
import { api, EditableSegment, ENGINE_URL, Job } from "../api";
import { STEP_LABELS } from "../labels";

interface Props {
  jobId: string;
  job: Job | undefined;
  onBack: () => void;
}

interface EditorData {
  segments: EditableSegment[];
  translations: string[];
}

export default function WorkbenchView({ jobId, job, onBack }: Props) {
  const [editor, setEditor] = useState<EditorData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [audioRef] = useState<{ current: HTMLAudioElement | null }>({ current: null });
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const [reexportVariant, setReexportVariant] = useState("bilingual");
  const [reexportEmbed, setReexportEmbed] = useState(false);

  const loadTranscript = useCallback(async () => {
    try {
      const tr = await api.getTranscript(jobId);
      setEditor({
        segments: tr.segments.map((s) => ({ start: s.start, end: s.end, text: s.text })),
        translations: tr.translations ?? [],
      });
    } catch (e) {
      setLoadError(String(e));
      setEditor(null);
    }
  }, [jobId]);

  useEffect(() => {
    audioRef.current?.pause();
    setPlayingIndex(null);
    setEditor(null);
    loadTranscript();
  }, [jobId]);

  const togglePlay = useCallback((i: number) => {
    const a = audioRef.current;
    if (!a || !editor) return;
    if (playingIndex === i) {
      a.pause();
      setPlayingIndex(null);
      return;
    }
    const seg = editor.segments[i];
    if (!seg) return;
    a.currentTime = seg.start;
    void a.play();
    setPlayingIndex(i);
  }, [editor, playingIndex]);

  const onTimeUpdate = useCallback(() => {
    const a = audioRef.current;
    if (!a || playingIndex === null || !editor) return;
    const seg = editor.segments[playingIndex];
    if (seg && a.currentTime >= seg.end - 0.02) {
      a.pause();
      setPlayingIndex(null);
    }
  }, [editor, playingIndex]);

  const saveEdits = useCallback(async () => {
    if (!editor) return;
    try {
      await api.updateTranscript(
        jobId,
        editor.segments,
        editor.translations.length ? editor.translations : undefined
      );
      await loadTranscript();
    } catch (e) {
      setLoadError(String(e));
    }
  }, [editor, jobId]);

  const rowOp = useCallback(
    async (op: "merge_next" | "split" | "delete", i: number) => {
      if (!editor) return;
      try {
        await api.updateTranscript(
          jobId,
          editor.segments,
          editor.translations.length ? editor.translations : undefined
        );
        await api.rowOp(jobId, i, op);
        await loadTranscript();
      } catch (e) {
        setLoadError(String(e));
      }
    },
    [editor, jobId]
  );

  const updSeg = (i: number, patch: Partial<EditableSegment>) => {
    setEditor((ed) =>
      ed
        ? { ...ed, segments: ed.segments.map((s, j) => (j === i ? { ...s, ...patch } : s)) }
        : ed
    );
  };
  const updTr = (i: number, v: string) => {
    setEditor((ed) =>
      ed
        ? { ...ed, translations: ed.translations.map((t, j) => (j === i ? v : t)) }
        : ed
    );
  };

  const doReexport = useCallback(async () => {
    try {
      await api.reexport(jobId, {
        variant: reexportVariant,
        save_to_video_folder: true,
        embed_video: reexportEmbed,
      });
    } catch (e) {
      setLoadError(String(e));
    }
  }, [jobId, reexportVariant, reexportEmbed]);

  const fileName = job ? job.video_path.split("/").pop() : jobId;
  const exportStep = job?.steps?.export;

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row">
          <button style={{ padding: "4px 12px" }} onClick={onBack}>← 返回列表</button>
          <h2 style={{ margin: 0 }}>{fileName}</h2>
          <span className="muted">#{jobId}</span>
        </div>
        {job && (
          <div className="row">
            {job.backend && "name" in job.backend && (
              <span className="step">{job.backend.name}/{job.backend.device}</span>
            )}
          </div>
        )}
      </div>

      <div className="panel" style={{ marginTop: 12 }}>
        <div className="row">
          <b>导出：</b>
          <label className="muted">字幕类型</label>
          <select value={reexportVariant} onChange={(e) => setReexportVariant(e.target.value)}>
            <option value="bilingual">双语对照</option>
            <option value="target">仅译文</option>
            <option value="source">仅原文</option>
          </select>
          <label className="row" style={{ gap: 4 }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={reexportEmbed}
              onChange={(e) => setReexportEmbed(e.target.checked)}
            />
            <span className="muted">烧录硬字幕视频</span>
          </label>
          <button
            onClick={doReexport}
            disabled={!editor || exportStep?.status === "running"}
          >
            重新导出
          </button>
          {exportStep && exportStep.status !== "pending" && (
            <span className={`step ${exportStep.status}`}>
              {STEP_LABELS.export}·{exportStep.status}
              {exportStep.status === "running" ? ` ${Math.round(exportStep.progress * 100)}%` : ""}
            </span>
          )}
          {exportStep?.detail && <span className="muted">{exportStep.detail}</span>}
        </div>
      </div>

      <h2>字幕编辑器</h2>
      <div className="panel">
        {loadError && <div className="error">{loadError}</div>}
        {!editor && !loadError && <span className="muted">加载中…</span>}
        {editor && (
          <>
            <audio
              ref={(el) => { audioRef.current = el; }}
              src={ENGINE_URL + "/jobs/" + jobId + "/audio"}
              preload="auto"
              style={{ display: "none" }}
              onTimeUpdate={onTimeUpdate}
            />
            <table>
              <thead>
                <tr><th>播放</th><th>开始</th><th>结束</th><th>原文</th><th>译文</th><th>操作</th></tr>
              </thead>
              <tbody>
                {editor.segments.map((s, i) => (
                  <tr key={i}>
                    <td>
                      <button
                        style={{ padding: "2px 8px" }}
                        title="播放该句原声"
                        onClick={() => togglePlay(i)}
                      >
                        {playingIndex === i ? "⏹" : "▶"}
                      </button>
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        style={{ width: 78 }}
                        value={s.start}
                        onChange={(e) => updSeg(i, { start: Number(e.target.value) })}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.01"
                        style={{ width: 78 }}
                        value={s.end}
                        onChange={(e) => updSeg(i, { end: Number(e.target.value) })}
                      />
                    </td>
                    <td style={{ minWidth: 220 }}>
                      <input
                        type="text"
                        style={{ width: "100%" }}
                        value={s.text}
                        onChange={(e) => updSeg(i, { text: e.target.value })}
                      />
                    </td>
                    <td style={{ minWidth: 220 }}>
                      <input
                        type="text"
                        style={{ width: "100%" }}
                        value={editor.translations[i] ?? ""}
                        onChange={(e) => updTr(i, e.target.value)}
                      />
                    </td>
                    <td>
                      <button style={{ padding: "2px 6px" }} title="拆分为两条" onClick={() => rowOp("split", i)}>拆</button>{" "}
                      <button style={{ padding: "2px 6px" }} title="与下一条合并" onClick={() => rowOp("merge_next", i)}>并</button>{" "}
                      <button style={{ padding: "2px 6px" }} title="删除此条" onClick={() => rowOp("delete", i)}>删</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="row" style={{ marginTop: 10 }}>
              <button onClick={saveEdits}>保存修改</button>
              <span className="muted">修改后先保存，再点上方「重新导出」生效到字幕文件 / 视频。</span>
            </div>
          </>
        )}
      </div>
    </>
  );
}
