import { useCallback, useEffect, useState } from "react";
import { api, DirListing } from "../api";

interface Props {
  /** 打开时的起始目录 */
  value?: string;
  onPick: (path: string) => void;
  onClose: () => void;
}

/**
 * 输出目录选择器。
 *
 * 浏览器出于安全考虑不允许网页读取本地绝对路径（showDirectoryPicker 只给句柄），
 * 所以目录枚举交给引擎的 /fs/dirs 完成，前端只负责展示与点选 —— 这样在浏览器
 * 和 Tauri 桌面窗口里行为完全一致。
 */
export default function DirPicker({ value, onPick, onClose }: Props) {
  const [listing, setListing] = useState<DirListing | null>(null);
  const [manual, setManual] = useState(value ?? "");
  const [err, setErr] = useState("");

  const load = useCallback(async (path?: string) => {
    setErr("");
    try {
      const d = await api.listDirs(path);
      setListing(d);
      setManual(d.path);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    void load(value || undefined);
    // 只在打开时定位一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>选择输出目录</h3>

        <div className="row">
          <input
            type="text"
            value={manual}
            placeholder="目录绝对路径"
            onChange={(e) => setManual(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void load(manual);
            }}
          />
          <button onClick={() => void load(manual)}>前往</button>
        </div>

        {listing && listing.drives.length > 0 && (
          <div className="row" style={{ marginTop: 8 }}>
            {listing.drives.map((d) => (
              <button key={d} className="ghost" onClick={() => void load(d)}>
                {d}
              </button>
            ))}
          </div>
        )}

        {err && <div className="error">{err}</div>}

        <div className="dirlist">
          {listing?.parent && (
            <div className="dirrow" onDoubleClick={() => void load(listing.parent as string)}>
              <span className="diritem">..（上级目录）</span>
            </div>
          )}
          {listing?.dirs.map((d) => (
            <div
              key={d.path}
              className="dirrow"
              onDoubleClick={() => void load(d.path)}
              onClick={() => setManual(d.path)}
            >
              <span className="diritem">{d.name}</span>
              {!d.writable && <span className="muted">只读</span>}
            </div>
          ))}
          {listing && listing.dirs.length === 0 && (
            <div className="dirrow muted">（这里没有子目录）</div>
          )}
          {!listing && !err && <div className="dirrow muted">读取中…</div>}
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <span className="muted" style={{ marginRight: "auto" }}>
            双击进入子目录，单击选中
          </span>
          <button className="ghost" onClick={onClose}>
            取消
          </button>
          <button
            disabled={!manual.trim()}
            onClick={() => {
              onPick(manual.trim());
              onClose();
            }}
          >
            使用此目录
          </button>
        </div>
      </div>
    </div>
  );
}
