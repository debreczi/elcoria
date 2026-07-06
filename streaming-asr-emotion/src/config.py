import yaml
from pathlib import Path
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Dict, Any, Optional, List
import os


class VADConfig(BaseModel):
    implementation: str
    params: Dict[str, Any]


class ASRConfig(BaseModel):
    implementation: str
    params: Dict[str, Any]


class EmotionConfig(BaseModel):
    implementation: str
    params: Dict[str, Any]


class FusionConfig(BaseModel):
    implementation: str
    params: Dict[str, Any]


class StreamingConfig(BaseModel):
    chunk_ms: int
    vad_buffer_ms: int
    emotion_interval_ms: int


class PipelineConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    description: str
    models_dir: str
    vad: VADConfig
    asr: ASRConfig
    emotion: EmotionConfig
    fusion: FusionConfig
    streaming: StreamingConfig

    @field_validator("models_dir")
    @classmethod
    def resolve_models_dir(cls, v: str, info) -> str:
        if not Path(v).is_absolute():
            config_dir = Path(__file__).parent.parent
            v = str(config_dir / v)
        return v


_DEFAULT_CONFIGS_DIR = str(Path(__file__).parent.parent / "configs")


class ConfigManager:
    def __init__(self, configs_dir: str = _DEFAULT_CONFIGS_DIR):
        configs_path = Path(configs_dir)
        if not configs_path.is_absolute():
            configs_path = Path(__file__).parent.parent / configs_dir
        self.configs_dir = configs_path
        if not self.configs_dir.exists():
            raise FileNotFoundError(f"Configs directory not found: {self.configs_dir}")

    def list_configs(self, available_only: bool = True) -> List[str]:
        names = [f.stem for f in self.configs_dir.glob("*.yaml")]
        if not available_only:
            return names
        ready = []
        for name in names:
            try:
                self.load_config(name)
                ready.append(name)
            except Exception:
                continue
        return ready

    def load_config(self, config_name: str) -> PipelineConfig:
        config_path = self.configs_dir / f"{config_name}.yaml"

        if not config_path.exists():
            raise FileNotFoundError(
                f"Config not found: {config_path}\nAvailable configs: {self.list_configs()}"
            )

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        config = PipelineConfig(**data)
        self._validate_model_paths(config)
        return config

    def _validate_model_paths(self, config: PipelineConfig) -> None:
        for stage_name, stage_config in [
            ("vad", config.vad),
            ("asr", config.asr),
            ("emotion", config.emotion),
            ("fusion", config.fusion),
        ]:
            model_path = stage_config.params.get("model_path")
            if model_path and not Path(model_path).is_absolute():
                model_path = str(Path(config.models_dir) / model_path)
                stage_config.params["model_path"] = model_path

            if model_path and not Path(model_path).exists():
                raise FileNotFoundError(
                    f"Model path not found for {stage_name}: {model_path}\n"
                    f"Please run scripts/download_models.py first."
                )


# Singleton instance
_config_manager = None


def get_config_manager(configs_dir: str = _DEFAULT_CONFIGS_DIR) -> ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(configs_dir)
    return _config_manager


def load_config(config_name: str) -> PipelineConfig:
    manager = get_config_manager()
    return manager.load_config(config_name)
