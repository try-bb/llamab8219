# llamab8219

llama.cpp 带界面的跑模型项目（最简版）

## 文件说明

| 文件 | 作用 |
|------|------|
| `界面运行api服务.py` | 主程序：GUI 界面 + API 服务 |
| `run.bat` | 一键启动界面 |
| `start_llama_with_choice.bat` | 选模型启动 llama-server（扫描 .lmstudio/models 下的 gguf） |
| `stop_llama.bat` | 停止 llama-server |

## 使用

1. 把 `llama-bin/llama-server.exe` 放到项目根目录（或改 bat 里的路径）
2. 模型放 `C:\Users\<你的用户名>\.lmstudio\models\` 下
3. 双击 `start_llama_with_choice.bat` 选模型启动后端
4. 双击 `run.bat` 打开界面

## 依赖

- Python 3.12（路径在 bat 里写死了，换机器要改）
- llama.cpp 的 `llama-server.exe`（不推仓库，太大）
- 模型文件 .gguf（不推仓库，太大）
