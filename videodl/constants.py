"""Constantes compartidas por el compresor y los clips."""

from __future__ import annotations

# Tamaños máximos típicos (MB) de cada plataforma.
COMPRESS_PRESETS = {
    "whatsapp": 16,
    "whatsapp-hd": 64,
    "discord": 10,
    "discord-nitro": 25,
    "telegram": 50,
    "email": 20,
}

ALLOWED_HEIGHTS = {0, 360, 480, 540, 720, 1080, 1440}

ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
    ".mpg", ".mpeg", ".flv", ".ts", ".3gp", ".wmv",
}

# La transcripción acepta audio y también vídeo: de un vídeo se extrae la pista
# de audio antes de pasarla al modelo.
ALLOWED_AUDIO_SUFFIXES = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac",
    ".wma", ".amr", ".aiff", ".aif",
} | ALLOWED_SUFFIXES

UPLOAD_CHUNK = 1024 * 1024
