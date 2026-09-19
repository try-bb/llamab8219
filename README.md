# 🦙 LlamaGUI — llama.cpp 图形化运行器

**让跑 GGUF 模型像双击桌面图标一样简单。**

一个用 Python + PyQt5 写的图形化工具，把 llama.cpp 的 `llama-server` 和 Open WebUI 装进一个窗口里：选模型、调参数、点启动，全程不用碰命令行。

> 作者：[try-bb](https://github.com/try-bb)

## ✨ 为什么用它

| 痛点 | LlamaGUI 的解法 |
|------|----------------|
| 命令行参数记不住、打错就崩 | 全部参数做成滑块/输入框，带范围限制，改错了也不会崩 |
| 不知道模型支不支持看图 | 自动解析 GGUF 文件头，📷 标记内置视觉的模型，自动匹配 mmproj |
| 调好的参数下次又要重调 | **参数预设**：一键保存/加载，你的调优成果不会丢 |
| 不知道显存/内存够不够 | 状态页实时显示内存、CPU、GPU 占用和 token 速度 |
| 想要网页聊天界面 | 内置 Open WebUI 管理页，一键启动，OpenAI 兼容 API 直接对接 |

## 🎛️ 可调参数（全部图形化）

- **上下文长度**（512 ~ 1M tokens）
- **batch / ubatch**（推理与预填充分片）
- **并行数**（多对话并发）
- **CPU 线程数**
- **API 端口**
- **视觉开关**（是否加载 mmproj 图片识别）

## 📦 功能一览

- 🚀 **一键启动/停止** llama-server，自动扫描模型目录
- 📷 **视觉模型识别**：自动检测 GGUF 是否内置视觉编码器，智能匹配 mmproj
- 💾 **参数预设**：保存多套调优方案，随时切换
- 📊 **实时监控**：token 速度、显存/内存/CPU 占用、服务状态
- 🌐 **Open WebUI 集成**：图形化聊天界面，OpenAI 兼容 API（`http://127.0.0.1:8081`）
- 📋 **日志页**：完整运行日志，出问题一眼定位

## 🚀 快速开始

### 1. 准备

- Windows 10/11 + Python 3.12（`pip install PyQt5 requests`）
- **llama.cpp 预编译版**（不用自己编译）：
  1. 打开 [llama.cpp Releases 页面](https://github.com/ggml-org/llama.cpp/releases)，找**最新一条** release（b 号越大越新）
  2. 在下面的附件列表里，**按你的显卡选对应的 Windows 包**：
     - **NVIDIA 显卡** → 选 `llama-...-win-cuda-12.x.zip`（数字选你 CUDA 驱动支持的版本，不确定就选 12.4，兼容性最好）
     - **AMD / Intel 显卡** → 选 `llama-...-win-vulkan.zip`
     - **纯 CPU 跑** → 选 `llama-...-win-avx2.zip`（CPU 支持 AVX512 的选 avx512 版）
  3. 下载后**解压到本项目的 `llama-bin/` 目录**（解压完 `llama-bin/llama-server.exe` 能直接看到就行，多一层文件夹就再往里挪一下）
- 你的 `.gguf` 模型文件（放到 `C:\Users\<用户名>\.lmstudio\models\`，或改 bat 里的路径）

### 2. 启动

```
双击 start_llama_with_choice.bat   ← 选模型、选上下文，启动后端
双击 run.bat                       ← 打开图形界面
```

### 3. 使用

界面里选模型 → 调参数（或加载预设）→ 点 **▶ 启动** → 完事。

API 地址：`http://127.0.0.1:8081`（OpenAI 兼容格式，可直接接各种客户端）

## 📁 文件说明

| 文件 | 作用 |
|------|------|
| `界面运行api服务.py` | 主程序（GUI + 服务管理） |
| `run.bat` | 一键启动界面 |
| `start_llama_with_choice.bat` | 选模型启动 llama-server |
| `stop_llama.bat` | 停止服务 |

## ⚠️ 注意

- bat 里的 Python 路径是写死的（`C:\Users\Administrator\...`），换机器请改成你自己的 Python 路径
- 模型文件和 `llama-server.exe` 体积太大，不放在仓库里，需自行准备
- 27B 级别模型建议上下文 4096 起步，显存不够就调小

## 📄 License

MIT — 随便用，改了记得回来看看。
