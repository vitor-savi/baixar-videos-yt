"""Núcleo do downloader: consulta informações e baixa vídeos do YouTube com yt-dlp."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Callable

import yt_dlp
from yt_dlp.utils import DownloadCancelled

VIDEO_FORMATS = ["MP4", "MKV", "WEBM", "MOV", "AVI"]
AUDIO_FORMATS = ["MP3", "M4A", "OPUS", "WAV", "FLAC"]
AUDIO_BITRATES = ["320", "256", "192", "128", "96"]
LOSSLESS_AUDIO = {"WAV", "FLAC"}

HEIGHT_NAMES = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}


# --------------------------------------------------------------------------- #
# Binários auxiliares (ffmpeg e deno)
# --------------------------------------------------------------------------- #
def _bin_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "bin")  # type: ignore[attr-defined]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin")


def find_ffmpeg() -> str | None:
    bundled = os.path.join(_bin_dir(), "ffmpeg.exe")
    if os.path.isfile(bundled):
        return bundled
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def find_deno() -> str | None:
    bundled = os.path.join(_bin_dir(), "deno.exe")
    if os.path.isfile(bundled):
        return bundled
    try:
        import deno

        return deno.find_deno_bin()
    except Exception:
        return shutil.which("deno")


def _base_opts() -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "windowsfilenames": True,
        "noprogress": True,
    }
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg
    deno = find_deno()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    return opts


# --------------------------------------------------------------------------- #
# Consulta de informações
# --------------------------------------------------------------------------- #
@dataclass
class QualityOption:
    height: int | None  # None = melhor disponível
    label: str


@dataclass
class VideoInfo:
    url: str
    title: str
    uploader: str
    duration: int | None
    qualities: list[QualityOption]


def _fmt_size(n: float | None) -> str:
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB", "MB") else f"{n:.2f} {unit}"
        n /= 1024
    return ""


def _fmt_size_of(f: dict) -> float | None:
    return f.get("filesize") or f.get("filesize_approx")


def fetch_info(url: str) -> VideoInfo:
    with yt_dlp.YoutubeDL(_base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        if not entries:
            raise ValueError("Nenhum vídeo encontrado nesse link.")
        info = entries[0]

    formats = info.get("formats") or []
    audios = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
    best_audio = max(audios, key=lambda f: f.get("abr") or 0, default=None)
    audio_size = _fmt_size_of(best_audio) if best_audio else 0

    by_height: dict[int, float | None] = {}
    for f in formats:
        h = f.get("height")
        if not h or h < 144 or f.get("vcodec") in (None, "none"):
            continue
        size = _fmt_size_of(f)
        if h not in by_height or (size or 0) > (by_height[h] or 0):
            by_height[h] = size

    qualities = [QualityOption(None, "Melhor disponível")]
    for h in sorted(by_height, reverse=True):
        name = f"{h}p" + (f" ({HEIGHT_NAMES[h]})" if h in HEIGHT_NAMES else "")
        size = by_height[h]
        if size:
            name += f"  ~{_fmt_size(size + (audio_size or 0))}"
        qualities.append(QualityOption(h, name))

    return VideoInfo(
        url=info.get("webpage_url") or url,
        title=info.get("title") or "(sem título)",
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=info.get("duration"),
        qualities=qualities,
    )


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
@dataclass
class Progress:
    stage: str  # texto para o usuário
    fraction: float | None  # 0..1 ou None (indeterminado)
    detail: str = ""


ProgressCallback = Callable[[Progress], None]


def _hidden_startupinfo():
    if sys.platform != "win32":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


def _run_ffmpeg(args: list[str], duration: float | None, on_progress: ProgressCallback,
                stage: str, cancel: threading.Event) -> bool:
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg não encontrado.")
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats", *args]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        text=True, startupinfo=_hidden_startupinfo(),
    )
    assert proc.stdout
    for line in proc.stdout:
        if cancel.is_set():
            proc.kill()
            proc.wait()
            raise DownloadCancelled()
        if line.startswith("out_time_us=") and duration:
            try:
                secs = int(line.split("=", 1)[1]) / 1_000_000
                on_progress(Progress(stage, min(secs / duration, 1.0)))
            except ValueError:
                pass
    return proc.wait() == 0


def _convert(src: str, dst: str, target: str, duration: float | None,
             on_progress: ProgressCallback, cancel: threading.Event) -> None:
    stage = f"Convertendo para {target}..."
    on_progress(Progress(stage, 0 if duration else None))
    if target == "MOV":
        ok = _run_ffmpeg(["-i", src, "-c", "copy", "-movflags", "+faststart", dst],
                         duration, on_progress, stage, cancel)
        if not ok:  # codecs incompatíveis com MOV: recodifica
            ok = _run_ffmpeg(["-i", src, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                              "-movflags", "+faststart", dst],
                             duration, on_progress, stage, cancel)
    elif target == "AVI":
        ok = _run_ffmpeg(["-i", src, "-c:v", "libxvid", "-q:v", "3", "-vtag", "XVID",
                          "-c:a", "libmp3lame", "-b:a", "192k", dst],
                         duration, on_progress, stage, cancel)
    else:
        raise ValueError(target)
    if not ok:
        raise RuntimeError(f"Falha ao converter para {target}.")


def download(url: str, out_dir: str, audio_only: bool, fmt: str, height: int | None,
             audio_bitrate: str, on_progress: ProgressCallback,
             cancel: threading.Event) -> str:
    """Baixa o vídeo e retorna o caminho do arquivo final."""
    fmt = fmt.upper()
    opts = _base_opts()
    opts["paths"] = {"home": out_dir}
    opts["overwrites"] = True

    temp_files: set[str] = set()

    def hook(d: dict) -> None:
        for key in ("tmpfilename", "filename"):
            if d.get(key):
                temp_files.add(d[key])
        if cancel.is_set():
            raise DownloadCancelled()
        if d["status"] == "downloading":
            info = d.get("info_dict") or {}
            is_audio = info.get("vcodec") == "none"
            stage = "Baixando áudio..." if (is_audio and not audio_only) else "Baixando..."
            if not audio_only and not is_audio:
                stage = "Baixando vídeo..."
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            frac = done / total if total else None
            parts = []
            if total:
                parts.append(f"{_fmt_size(done)} de {_fmt_size(total)}")
            if d.get("speed"):
                parts.append(f"{_fmt_size(d['speed'])}/s")
            if d.get("eta") is not None:
                m, s = divmod(int(d["eta"]), 60)
                parts.append(f"restam {m}:{s:02d}")
            on_progress(Progress(stage, frac, "  •  ".join(parts)))

    def pp_hook(d: dict) -> None:
        if cancel.is_set():
            raise DownloadCancelled()
        if d["status"] == "started":
            names = {
                "Merger": "Juntando vídeo e áudio...",
                "ExtractAudio": f"Convertendo áudio para {fmt}...",
                "VideoRemuxer": f"Ajustando contêiner {fmt}...",
                "Metadata": "Gravando metadados...",
            }
            name = names.get(d.get("postprocessor"))
            if name:
                on_progress(Progress(name, None))

    opts["progress_hooks"] = [hook]
    opts["postprocessor_hooks"] = [pp_hook]

    convert_after: str | None = None
    if audio_only:
        opts["format"] = "bestaudio/best"
        opts["outtmpl"] = "%(title)s.%(ext)s"
        pp = {"key": "FFmpegExtractAudio", "preferredcodec": fmt.lower()}
        if fmt not in LOSSLESS_AUDIO:
            pp["preferredquality"] = audio_bitrate
        opts["postprocessors"] = [pp, {"key": "FFmpegMetadata"}]
    else:
        res = f"res:{height}" if height else "res"
        opts["format"] = "bv*+ba/b"
        opts["outtmpl"] = "%(title)s [%(height)sp].%(ext)s"
        if fmt in ("MP4", "MOV", "AVI"):
            # Prioriza H.264 + AAC (máxima compatibilidade) sem abrir mão da resolução
            opts["format_sort"] = [res, "fps", "vcodec:h264", "acodec:aac"]
        elif fmt == "WEBM":
            opts["format_sort"] = [res, "fps", "vcodec:vp9", "acodec:opus"]
        else:  # MKV aceita qualquer codec
            opts["format_sort"] = [res, "fps"]

        if fmt in ("MOV", "AVI"):
            convert_after = fmt
            container = "mp4" if fmt == "MOV" else "mkv"
            opts["outtmpl"] = "%(title)s [%(height)sp].tmp.%(ext)s"
        else:
            container = fmt.lower()
        opts["merge_output_format"] = container
        opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": container}]

    on_progress(Progress("Iniciando...", None))
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info.get("_type") == "playlist":
                info = next(e for e in info["entries"] if e)
            path = info["requested_downloads"][0]["filepath"]
    except BaseException:
        if cancel.is_set():  # remove arquivos parciais
            for f in temp_files:
                for candidate in (f, f + ".part", f + ".ytdl"):
                    try:
                        os.remove(candidate)
                    except OSError:
                        pass
        raise

    if convert_after:
        final = path.replace(".tmp.", ".")
        final = os.path.splitext(final)[0] + "." + convert_after.lower()
        try:
            _convert(path, final, convert_after, info.get("duration"), on_progress, cancel)
        except BaseException:
            if os.path.exists(final):
                os.remove(final)
            raise
        finally:
            if os.path.exists(path):
                os.remove(path)
        path = final

    on_progress(Progress("Concluído!", 1.0))
    return path
