# Auto Chat Test

基于图像模板匹配的聊天模块自动化测试框架，专为 **Lenovo Qira（联想小天）** 浮动聊天窗口设计。

## 核心思路

1. **模板匹配导航** — 通过截图模板识别浮空按钮、菜单、聊天窗等 UI 元素，自动操作
2. **无人值守执行** — 读 Excel 数据集 → 逐条发送 → 等回复 → 滚动拼接截图 → 记录耗时
3. **执行与判断解耦** — 先跑完收集截图，再离线人工判断，不阻塞测试

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
├── src/
│   ├── config.py            # 配置加载
│   ├── excel_reader.py      # Excel 读取
│   ├── ui_automator.py      # UI 自动化核心
│   ├── executor.py          # 测试执行器
│   ├── judge.py             # 判断引擎（规则 + LLM）
│   ├── reporter.py          # HTML 报告生成
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
version: "0525"                    # 测试版本号，必改

app:
  window_title: "Lenovo Qira"      # 客户端窗口标题
  process_name: "QuantumAI.Hub"    # 进程名
  launch_path: ""                  # 启动路径（可选）

ui:
  template_confidence: 0.75        # 模板匹配置信度阈值

execution:
  response_timeout: 90             # 单条超时（秒）
  retry_count: 1                   # 失败重试次数
  poll_interval: 1                 # 轮询间隔（秒）

excel:
  question_column: "问题"           # 问题列名
  expected_column: "期望答案"       # 期望答案列名
  category_column: "分类"          # 分类列名（可选）
  reset_session_column: "新建会话" # 是否新建会话（是/否）
```

### 3. 准备 Excel 数据集

| 问题 | 期望答案 | 分类 | 新建会话 |
|------|----------|------|----------|
| 今天天气怎么样？ | 我无法获取实时天气... | 天气 | 是 |
| 讲个笑话 | 期望包含一个幽默短故事 | 娱乐 | 否 |

- **新建会话 = 是**：发送前点重置按钮，清空对话历史
- **新建会话 = 否**：保留上下文继续对话
- 期望答案和分类无所谓，随便填

### 4. 截取模板图片（换机器后必须重做）

```bash
python -m src.template_capture
```

- 或者更简单的方法，直接自己截对应的图片
先打开目标 UI 元素 → 点 Capture → 拖拽框选 → 自动保存到 `templates/`。

### 5. 运行测试

```bash
python -m src.main run -e data/questions.xlsx
```

结果保存到 `results/<version>/`：
- `raw_responses.json` — 原始数据
- `test_results.xlsx` — 含耗时和错误信息
- `screenshots/` — 每条对话的截图

## CLI 命令

| 命令 | 说明 |
|------|------|
| `python -m src.main run -e <excel>` | 执行测试 |
| `python -m src.main judge -v <version>` | 离线判断（需 ANTHROPIC_API_KEY） |
| `python -m src.main report -v <version>` | 生成 HTML 报告 |
| `python -m src.main compare -a v1 -b v2` | 版本对比 |

## 自动化流程

1. 定位浮空按钮 → 点击 → 等 3 秒
2. 定位 Chat 菜单 → 点击 → 等 3 秒
3. 聊天窗出现（重置按钮 + 发送按钮确认）
4. 逐条：重置（可选）→ 粘贴问题 → 发送 → 每 1 秒轮询发送按钮 → 出现即截图
5. 长回复自动滚动拼接，宽高由两个锚点精确定位
6. 结尾重置清理

## 注意事项
1. 每次运行前，如果result文件夹下已经有对应版本的文件夹，则需要删除。如果运行后直接结束，大概率是忘记删了
2. 运行时保持qira最小化的状态
