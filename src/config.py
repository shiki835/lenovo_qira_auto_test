import os
from pathlib import Path
from dataclasses import dataclass, field
import yaml


@dataclass
class AppConfig:
    window_title: str = "Lenovo Qira"
    process_name: str = "QuantumAI.Hub"
    launch_path: str = ""


@dataclass
class UIConfig:
    template_confidence: float = 0.75
    chat_window_width: int = 480
    chat_window_max_height: int = 500


@dataclass
class ExecutionConfig:
    response_timeout: int = 90
    retry_count: int = 1
    poll_interval: int = 1


@dataclass
class JudgeConfig:
    llm_enabled: bool = True
    llm_model: str = "claude-sonnet-4-6"
    error_keywords: list[str] = field(default_factory=lambda: [
        "抱歉，我无法回答", "网络错误", "服务不可用",
        "请求超时", "系统繁忙",
    ])


@dataclass
class ExcelConfig:
    question_column: str = "问题"
    expected_column: str = "期望答案"
    category_column: str = ""
    reset_session_column: str = "新建会话"


@dataclass
class Config:
    version: str = "v1.0"
    app: AppConfig = field(default_factory=AppConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    excel: ExcelConfig = field(default_factory=ExcelConfig)


def load_config(config_path: str | None = None) -> Config:
    """Load configuration from YAML file, falling back to defaults."""
    if config_path is None:
        config_path = os.environ.get("CHAT_TEST_CONFIG", "")
        if not config_path:
            candidate = Path(__file__).parent.parent / "config.yaml"
            if candidate.exists():
                config_path = str(candidate)

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        return Config(
            version=raw.get("version", "v1.0"),
            app=AppConfig(**raw.get("app", {})),
            ui=UIConfig(**raw.get("ui", {})),
            execution=ExecutionConfig(**raw.get("execution", {})),
            judge=JudgeConfig(**raw.get("judge", {})),
            excel=ExcelConfig(**raw.get("excel", {})),
        )

    return Config()
