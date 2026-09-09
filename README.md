# DubFlow — 跨平台视频翻译工具

自动化视频翻译流水线：**导入 → 提取音频 → 语音识别（GPU）→ LLM 翻译 → 导出 SRT / 双语字幕**。

## 架构

```
GUI (Tauri 2 + React)  ←HTTP/WS→  引擎 (Python FastAPI)  →  ffmpeg / GPU 推理
```

ASR 多后端（自动探测，输出统一为 Transcript）：

| 硬件 | 引擎 | 加速 |
|---|---|---|
| MacBook (M 系列) | mlx-whisper | Metal ✅ 已实现，**强制 GPU，无 CPU 兜底**（Apple Silicon 必有 Metal） |
| NVIDIA | faster-whisper | CUDA（接口已留，MVP2 验证） |
| AMD / Intel | whisper.cpp | Vulkan（MVP2） |
| Windows/Linux 无显卡 | faster-whisper | CPU int8 兜底 ✅ 已实现 |

## 目录

```
engine/   Python 引擎（FastAPI + 流水线 + ASR Provider 抽象）
gui/      Tauri 2 + React 前端脚手架
scripts/  smoke_test.py 冒烟测试 / benchmark_asr.py 双后端基准
```

## 引擎（macOS 先行）

```bash
cd engine
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 运行（Metal 需要真实终端环境，沙箱内 GPU 不可用）
.venv/bin/python -m dubflow
# 引擎监听 http://127.0.0.1:8741
```

注意：mlx 初始化在无 GPU 权限的沙箱进程里会崩溃，务必在正常终端运行。

### 端到端冒烟测试

```bash
engine/.venv/bin/python scripts/smoke_test.py
# 用 macOS say 合成语音 → 引擎 API → Metal 转录 → SRT 导出
# SMOKE_MODEL=base 可换模型
```

### 模型管理

模型查找顺序：本地目录 `~/.dubflow/models/<name>` → HF 仓库下载。
国内网络 huggingface.co 不可达时，手动从镜像拉取（hf_hub 元数据校验与镜像不兼容）：

```bash
mkdir -p ~/.dubflow/models/whisper-tiny
curl -L "https://hf-mirror.com/mlx-community/whisper-tiny/resolve/main/config.json" \
     -o ~/.dubflow/models/whisper-tiny/config.json
curl -L "https://hf-mirror.com/mlx-community/whisper-tiny/resolve/main/weights.npz" \
     -o ~/.dubflow/models/whisper-tiny/weights.npz
```

环境变量：`DUBFLOW_PORT`(8741) `DUBFLOW_DATA_DIR`(~/​.dubflow) `DUBFLOW_MODELS_DIR` `HF_ENDPOINT`(默认 hf-mirror)
`DUBFLOW_TRANSLATE_BASE_URL` `DUBFLOW_TRANSLATE_API_KEY` `DUBFLOW_TRANSLATE_MODEL`

### 后端基准测试（决定是否需要 mlx，还是 whisper.cpp 一家通吃）

```bash
engine/.venv/bin/python scripts/benchmark_asr.py sample.wav --models tiny,base
```

## GUI

```bash
# 前置：安装 Rust（https://rustup.rs），引擎先跑起来
cd gui
npm install
npm run tauri dev     # 开发模式
npm run tauri build   # 打包 .app/.dmg
```

首次 `tauri build` 需要 app 图标：`npx @tauri-apps/cli icon path/to/icon.png`。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /health | 健康检查 + 当前 ASR 后端 |
| POST | /jobs | 建任务：`{video_path, source_language, target_language, asr:{model}, translation:{enabled,base_url,api_key,model}}` |
| GET | /jobs, /jobs/:id | 任务列表/状态（各步骤进度） |
| GET | /jobs/:id/transcript | 识别结果（段落+时间轴） |
| POST | /jobs/:id/cancel | 请求取消（步骤间生效） |
| WS | /ws/jobs/:id | 实时进度事件 |

任务产物落盘于 `data/jobs/<id>/`：`audio.wav` `transcript.json` `source.srt` `<目标语>.srt` `bilingual.srt`，重跑自动跳过已完成步骤。

## 路线图

- [x] MVP：导入 → Metal 识别 → 导出 SRT（已验证）
- [ ] 字幕编辑器 / 时间轴
- [ ] whisper.cpp 后端（AMD/Vulkan）+ NVIDIA CUDA 实测
- [ ] TTS 配音（edge-tts）+ 人声分离（demucs）
- [ ] 引擎作为 Tauri sidecar 打包分发
- [ ] 批量任务队列持久化
