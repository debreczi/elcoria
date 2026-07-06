#!/usr/bin/env python3
"""
Download models for offline use.
Run this once on an internet-connected machine before using the PoC offline.
"""

import os
import sys
from pathlib import Path
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Models to download
MODELS = {
    "ASR Models": {
        "whisper-small-hu": {
            "repo": "openai/whisper-small",
            "type": "huggingface",
        },
        "whisper-large-v3-hu": {
            "repo": "benmajor27/whisper-large-v3-hu_full",
            "type": "huggingface_ctr anslate2",  # Special handling for CTranslate2
        },
    },
    "Emotion Models": {
        "wav2vec2-xlsr-emotion": {
            "repo": "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition",
            "type": "huggingface",
        },
        "xlm-roberta-sentiment": {
            "repo": "cardiffnlp/twitter-xlm-roberta-base-sentiment",
            "type": "huggingface",
        },
    },
    "VAD Models": {
        "silero-vad": {
            "repo": "snakers4/silero-vad",
            "type": "torch_hub",
        },
    },
}


def download_huggingface_model(repo_id: str, local_dir: str) -> None:
    """Download HuggingFace model to local directory."""
    try:
        from huggingface_hub import snapshot_download

        logger.info(f"Downloading {repo_id} to {local_dir}...")

        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
            resume_download=True,
            trust_repo=True,
        )

        logger.info(f"✓ Downloaded {repo_id}")
    except Exception as e:
        logger.error(f"✗ Failed to download {repo_id}: {e}")


def download_faster_whisper_model(repo_id: str, local_dir: str) -> None:
    """Download Whisper model in CTranslate2 format for faster-whisper."""
    try:
        from faster_whisper import WhisperModel

        logger.info(f"Downloading {repo_id} (CTranslate2 format) to {local_dir}...")

        # This downloads and converts to CTranslate2 format automatically
        model = WhisperModel(
            repo_id,
            device="cpu",
            compute_type="int8",
            download_root=local_dir,
            local_files_only=False,
        )

        logger.info(f"✓ Downloaded {repo_id} in CTranslate2 format")
    except Exception as e:
        logger.error(f"✗ Failed to download {repo_id}: {e}")


def download_torch_hub_model(repo_id: str, local_dir: str) -> None:
    """Download Silero VAD from torch.hub."""
    try:
        import torch

        logger.info(f"Downloading {repo_id} to {local_dir}...")

        torch.hub.set_dir(local_dir)
        model = torch.hub.load(repo_id, "silero_vad", source="github", verbose=False)

        logger.info(f"✓ Downloaded {repo_id}")
    except Exception as e:
        logger.error(f"✗ Failed to download {repo_id}: {e}")


def main():
    """Main download routine."""
    # Set offline mode to prevent accidental external calls later
    os.environ["TRANSFORMERS_OFFLINE"] = "0"  # Temporarily enable to download
    os.environ["HF_HUB_OFFLINE"] = "0"

    models_dir = Path(__file__).parent.parent / "models"
    models_dir.mkdir(exist_ok=True)

    logger.info(f"Downloading models to {models_dir}")
    logger.info("This may take a while depending on your internet connection...\n")

    total_models = 0
    for category, models in MODELS.items():
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Downloading {category}")
        logger.info(f"{'=' * 60}")

        for model_name, model_info in models.items():
            total_models += 1
            local_dir = str(models_dir / model_name)

            # Skip if already downloaded
            if Path(local_dir).exists():
                logger.info(f"⊘ {model_name} already exists, skipping")
                continue

            repo_id = model_info["repo"]
            model_type = model_info["type"]

            if model_type == "huggingface":
                download_huggingface_model(repo_id, local_dir)
            elif model_type == "huggingface_ctranslate2":
                download_faster_whisper_model(repo_id, local_dir)
            elif model_type == "torch_hub":
                download_torch_hub_model(repo_id, local_dir)

    logger.info(f"\n{'=' * 60}")
    logger.info("✓ Model download complete!")
    logger.info(f"{'=' * 60}")
    logger.info(f"\nModels saved to: {models_dir}")
    logger.info("\nYou can now use the PoC offline.")
    logger.info("Set environment variables:")
    logger.info('  TRANSFORMERS_OFFLINE=1')
    logger.info('  HF_HUB_OFFLINE=1')
    logger.info('  HF_DATASETS_OFFLINE=1')


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\nDownload cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
