import { useCallback, useEffect, useRef, useState } from "react";
import { api, DownloadsSnapshot, Health, Job, Segment } from "./api";

const MODELS = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "large-v3-turbo-q4"];
const STEP_LABELS: Record<string, string> = {
  probe: "探测",
  extract_audio: "提取音频",
  asr: "语音识别",
  translate: "翻译",
  export: "导出字幕",
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [videoPath, setVideoPath] = useState("");
  const [sourceLang, setSourceLang] = useState("");
  const [targetLang, setTargetLang] = useState("zh");
  const [model, setModel] = useState("large-v3-turbo");
  const [translate, setTranslate] = useState(false);
  const [trProvider, setTrProvider] = useState("llm");
  const [subtitleVariant, setSubtitleVariant] = useState("bilingual");
  const [saveSrt, setSaveSrt] = useState(true);
  const [embedVideo, setEmbedVideo] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [msftKey, setMsftKey] = useState("");
  const [msftRegion, setMsftRegion] = useState("global");
  const [apiBase, setApiBase] = useState("https://api.openai.com/v1");
  const [apiModel, setApiModel] = useState("gpt-4o-mini");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [transcript, setTranscript] = useState<{ job: string; segs: Segment[] } | null>(null);
  const [error, setError] = useState("");
  const pollRef = useRef<number | null>(null);
  const [dl, setDl] = useState<DownloadsSnapshot | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    const t = window.setInterval(() => {
      api.listJobs().then((r) => setJobs(r.jobs)).catch(() => {});
    }, 1000);
    pollRef.current = t;
    const t2 = window.setInterval(() => {
      api.downloads().then(setDl).catch(() => {});
    }, 2000);
    api.downloads().then(setDl).catch(() => {});
    return () => { window.clearInterval(t); window.clearInterval(t2); };
  }, []);

  const submit = useCallback(async () => {
    setError("");
    try {
      await api.createJob({
        video_path: videoPath,
        source_language: sourceLang.trim() || null,
        target_language: targetLang.trim() || "zh",
        asr: { provider: "auto", model },
        translation: {
          enabled: translate,
          provider: trProvider,
          base_url: trProvider === "llm" ? (apiBase || undefined) : undefined,
          api_key: trProvider === "llm" ? (apiKey || undefined)
                 : trProvider === "microsoft" ? (msftKey || undefined) : undefined,
          region: trProvider === "microsoft" ? (msftRegion || undefined) : undefined,
          model: trProvider === "llm" ? (apiModel || undefined) : undefined,
        },
        export: {
          variant: subtitleVariant,
          save_to_video_folder: saveSrt || embedVideo,
          embed_video: embedVideo,
        },
      });
    } catch (e) {
      setError(String(e));
    }
  }, [videoPath, sourceLang, targetLang, model, translate, trProvider, apiKey, apiBase, apiModel, msftKey, msftRegion, subtitleVariant, saveSrt, embedVideo]);

  const showTranscript = useCallback(async (id: string) => {
    try {
      const tr = await api.getTranscript(id);
      setTranscript({ job: id, segs: tr.segments });
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const overall = (j: Job) => {
    const vals = Object.values(j.steps);
    const done = vals.filter((s) => s.status === "done" || s.status === "skipped").length;
    const running = vals.find((s) => s.status === "running");
    return {
      pct: (done / vals.length) * 100 + (running ? running.progress * (100 / vals.length) : 0),
      running: !!running,
    };
  };

  return (
    <>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h1>DubFlow 视频翻译</h1>
        {health ? (
          <span className="badge ok">
            引擎已连接 · {health.backend.name}/{health.backend.device}
          </span>
        ) : (
          <span className="badge err">引擎未连接（127.0.0.1:8741）</span>
        )}
      </div>
      <p className="muted">
        流水线：导入 → 提取音频 → 语音识别（GPU）→ 翻译 → 导出 SRT。中间产物断点续跑。
      </p>

      <h2>新建任务</h2>
      <div className="panel">
        <div className="row">
          <input
            type="text"
            placeholder="视频绝对路径，如 /Users/zinc/Movies/demo.mp4"
            value={videoPath}
            onChange={(e) => setVideoPath(e.target.value)}
          />
        </div>
        <div className="row" style={{ marginTop: 10 }}>
          <label className="muted">源语言</label>
          <select value={sourceLang} onChange={(e) => setSourceLang(e.target.value)}>
            <option value="">自动检测</option>
            {["en", "zh", "ja", "ko", "de", "fr", "es", "ru"].map((l) => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
          <label className="muted">目标语言</label>
          <input
            type="text"
            style={{ flex: 0, width: 60 }}
            value={targetLang}
            onChange={(e) => setTargetLang(e.target.value)}
          />
          <label className="muted">识别模型</label>
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
          <label className="row" style={{ gap: 4 }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={translate}
              onChange={(e) => setTranslate(e.target.checked)}
            />
            <span className="muted">翻译</span>
          </label>
          {translate && (
            <select value={trProvider} onChange={(e) => setTrProvider(e.target.value)}>
              <option value="llm">LLM 翻译</option>
              <option value="google">谷歌翻译</option>
              <option value="microsoft">微软翻译</option>
            </select>
          )}
        </div>
        {translate && trProvider === "llm" && (
          <div className="row" style={{ marginTop: 10 }}>
            <input type="text" style={{ flex: 2 }} value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="API Base URL" />
            <input type="text" style={{ flex: 1 }} value={apiModel} onChange={(e) => setApiModel(e.target.value)} placeholder="模型名" />
            <input type="text" style={{ flex: 1 }} value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="API Key" />
          </div>
        )}
        {translate && trProvider === "microsoft" && (
          <div className="row" style={{ marginTop: 10 }}>
            <input type="text" style={{ flex: 2 }} value={msftKey} onChange={(e) => setMsftKey(e.target.value)} placeholder="Azure Translator Key（免费 F0 档即可）" />
            <input type="text" style={{ flex: 0, width: 120 }} value={msftRegion} onChange={(e) => setMsftRegion(e.target.value)} placeholder="区域，如 global" />
          </div>
        )}
        {translate && trProvider === "google" && (
          <div className="muted" style={{ marginTop: 8 }}>谷歌免费接口，经系统代理访问，无需 key。</div>
        )}
        <div className="row" style={{ marginTop: 10 }}>
          <label className="muted">字幕类型</label>
          <select value={subtitleVariant} onChange={(e) => setSubtitleVariant(e.target.value)}>
            <option value="bilingual">双语对照</option>
            <option value="target">仅译文</option>
            <option value="source">仅原文</option>
          </select>
          <label className="row" style={{ gap: 4 }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={saveSrt}
              onChange={(e) => setSaveSrt(e.target.checked)}
            />
            <span className="muted">保存字幕到视频文件夹</span>
          </label>
          <label className="row" style={{ gap: 4 }}>
            <input
              type="checkbox"
              style={{ width: "auto" }}
              checked={embedVideo}
              onChange={(e) => {
                setEmbedVideo(e.target.checked);
                if (e.target.checked) setSaveSrt(true);
              }}
            />
            <span className="muted">烧录硬字幕生成新视频</span>
          </label>
        </div>
        <div className="row" style={{ marginTop: 12 }}>
          <button disabled={!videoPath.trim() || !health} onClick={submit}>
            开始处理
          </button>
          {error && <span className="error">{error}</span>}
        </div>
      </div>

      <h2>任务列表</h2>
      <div className="panel">
        {jobs.length === 0 && <span className="muted">暂无任务</span>}
        {jobs.map((j) => {
          const o = overall(j);
          return (
            <div className="job" key={j.id}>
              <div className="file">
                {j.video_path}
                <span className="muted" style={{ marginLeft: 8 }}>#{j.id}</span>
              </div>
              <div className="steps">
                {Object.entries(j.steps).map(([k, s]) => (
                  <span key={k} className={`step ${s.status}`}>
                    {STEP_LABELS[k] ?? k}·{s.status}
                    {s.status === "running" ? ` ${Math.round(s.progress * 100)}%` : ""}
                  </span>
                ))}
                {j.backend && "name" in j.backend && (
                  <span className="step">{j.backend.name}/{j.backend.device}</span>
                )}
                <button
                  style={{ marginLeft: "auto", padding: "2px 10px" }}
                  onClick={() => showTranscript(j.id)}
                  disabled={j.status !== "done"}
                >
                  查看字幕
                </button>
              </div>
              <div className="bar"><div style={{ width: `${o.pct}%` }} /></div>
              {j.error && <div className="error">{j.error}</div>}
            </div>
          );
        })}
      </div>

      {transcript && (
        <>
          <h2>字幕预览（{transcript.job}）</h2>
          <div className="panel">
            <table>
              <thead>
                <tr><th>开始</th><th>结束</th><th>文本</th></tr>
              </thead>
              <tbody>
                {transcript.segs.map((s, i) => (
                  <tr key={i}>
                    <td>{s.start.toFixed(2)}</td>
                    <td>{s.end.toFixed(2)}</td>
                    <td>{s.text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>模型与依赖</h2>
      <div className="panel">
        <div className="row">
          <b>ffmpeg（捆绑）</b>
          {dl?.ffmpeg.installed ? (
            <span className="badge ok">已就绪</span>
          ) : (
            <span className="badge err">未下载</span>
          )}
          {dl && !dl.ffmpeg.installed && dl.ffmpeg.status !== "downloading" && (
            <button onClick={() => api.downloadFfmpeg()}>下载当前平台 ffmpeg</button>
          )}
          {dl && dl.ffmpeg.status === "downloading" && (
            <span className="muted">
              下载中 {Math.round(dl.ffmpeg.progress * 100)}% {dl.ffmpeg.detail}
            </span>
          )}
          {dl && dl.ffmpeg.status === "failed" && (
            <span className="error">{dl.ffmpeg.detail}</span>
          )}
        </div>
        <table style={{ marginTop: 12 }}>
          <thead>
            <tr><th>模型</th><th>后端</th><th>本地大小</th><th>状态</th><th></th></tr>
          </thead>
          <tbody>
            {dl?.models.map((m) => (
              <tr key={m.key}>
                <td>{m.key}</td>
                <td>{m.backend}</td>
                <td>{m.size_mb} MB</td>
                <td>
                  {m.downloaded
                    ? "已下载"
                    : m.status === "downloading"
                    ? `下载中 ${Math.round(m.progress * 100)}%`
                    : m.status === "failed"
                    ? <span className="error">失败: {m.detail}</span>
                    : "未下载"}
                </td>
                <td>
                  {!m.downloaded && (
                    <button
                      style={{ padding: "2px 10px" }}
                      disabled={m.status === "downloading"}
                      onClick={() => api.downloadModel(m.key)}
                    >
                      下载
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted" style={{ marginBottom: 0 }}>
          mlx = MacBook Metal GPU；ctranslate2 = Windows/Linux（N卡 CUDA / CPU 兜底，TODO）；whisper.cpp Vulkan（A卡）规划中。
        </p>
      </div>
    </>
  );
}

export default App;
