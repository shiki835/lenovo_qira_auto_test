# Auto Chat Test

基于图像模板匹配的聊天模块自动化测试框架，专为 **Lenovo Qira（联想小天）** 浮动聊天窗口设计。

## 核心思路

1. **模板匹配导航** — 4 张截图模板识别浮空按钮、菜单、聊天窗，自动操作 UI
2. **无人值守执行** — 读 Excel 数据集 → 逐条发送 → 轮询等待 → 滚动拼接截图 → 记录耗时
3. **视觉模型判断** — 本地部署 Qwen3-VL 看图判断回复是否符合预期（PASS/FAIL/UNCERTAIN）

## 项目结构

```
├── config.yaml              # 运行时配置
├── requirements.txt         # Python 依赖
├── data/
│   └── questions.xlsx       # 测试数据集
├── templates/               # UI 模板截图（4 张）
│   ├── float_button.png     # 浮空按钮
│   ├── chat_menu.png        # Chat 菜单项
│   ├── send_button.png      # 发送按钮
│   └── reset_chat.png       # 重置按钮
├── results/                 # 测试结果（按版本归档）
│   └── 0525/
│       ├── raw_responses.json
│       ├── test_results.xlsx
│       ├── judge_results.xlsx
│       └── screenshots/
├── scripts/
│   └── deploy_ollama.ps1    # Ollama 模型部署脚本
├── src/
│   ├── config.py            # 配置加载
│   ├── excel_reader.py      # Excel 读取
│   ├── ui_automator.py      # UI 自动化核心（模板匹配 + 截图）
│   ├── executor.py          # 测试执行器（顺序执行 + 断点续跑）
│   ├── judge.py             # 判断引擎（L1 规则 + L2 视觉模型）
│   ├── reporter.py          # HTML 报告 + 版本对比
│   ├── main.py              # CLI 入口
│   └── template_capture.py  # 模板截图 GUI 工具
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 config.yaml

```yaml
version: "0525"

app:
  window_title: "Lenovo Qira"
  process_name: "QuantumAI.Hub"

ui:
  template_confidence: 0.75       # 模板匹配置信度（0.6~0.85）

execution:
  response_timeout: 90            # 单条超时（秒）
  poll_interval: 1                # 轮询间隔（秒）

judge:
  ollama_base_url: "http://localhost:11434/v1"
  ollama_model: "qwen3-vl:2b"     # 视觉模型（2b/4b/8b）
  ollama_max_tokens: 256
  ollama_temperature: 0

excel:
  question_column: "问题"
  expected_column: "期望答案"
  category_column: "分类"
  reset_session_column: "新建会话"
```

### 3. 准备 Excel 数据集

| 问题 | 期望答案 | 分类 | 新建会话 |
|------|----------|------|----------|
| 今天天气怎么样？ | 我无法获取实时天气... | 天气 | 是 |
| 讲个笑话 | 期望包含幽默短故事 | 娱乐 | 否 |

- **新建会话 = 是**：发送前点重置按钮，清空对话历史
- **新建会话 = 否**：保留上下文继续对话

### 4. 截取模板图片（换机器必须重做）

```bash
python -m src.template_capture
```

先打开目标 UI 元素 → 点 Capture → 拖拽框选 → 自动保存到 `templates/`。

### 5. 部署判断模型（可选，用于自动判断）

```powershell
# 安装 Ollama: https://ollama.com/download/windows
ollama pull qwen3-vl:2b
```

### 6. 运行测试

```bash
# 执行测试
python -m src.main run -e data/questions.xlsx

# 模型判断（需先部署 Ollama）
python -m src.main judge -v 0525

# 生成 HTML 报告
python -m src.main report -v 0525

# 版本对比
python -m src.main compare -a v1 -b v2
```

## 结果文件

每次测试在 `results/<version>/` 下生成：

| 文件 | 说明 |
|------|------|
| `raw_responses.json` | 原始测试数据（可断点续跑） |
| `test_results.xlsx` | 含每条耗时和错误信息 |
| `judge_results.xlsx` | 模型判断结果（判定 + 原始回复） |
| `screenshots/qXXXX_after.png` | 每条对话的滚动拼接截图 |

## 自动化流程

1. 定位浮空按钮 → 点击 → 等 3 秒
2. 定位 Chat 菜单 → 点击 → 等 3 秒
3. 聊天窗出现（双锚点确认：重置按钮 + 发送按钮）
4. 逐条：重置（可选）→ 剪贴板粘贴问题 → 发送
5. 等 3 秒后每 1 秒轮询发送按钮 → 出现即截图
6. 长回复自动滚动拼接（PageDown + 像素对比检测到底）
7. 截图由双锚点定位裁剪（重置按钮左上角 → 发送按钮右下角）
8. 结尾重置清理

## 判断流程

1. **L1 规则检查**：超时？空响应？错误关键词？
2. **L2 视觉模型**：截图 + 期望答案 → Qwen3-VL 看图判断 → PASS / FAIL / UNCERTAIN
3. 结果保存到 `judge_results.xlsx`（含模型原始回复）
