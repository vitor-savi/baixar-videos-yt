"""Interface gráfica do Baixar Vídeos YT."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from yt_dlp.utils import DownloadCancelled

import downloader as dl

APP_NAME = "Baixar Vídeos YT"
APP_ID = "BaixarVideosYT.App"


def resource_path(*parts: str) -> str:
    """Caminho de um arquivo empacotado (funciona no .py e no .exe)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
CONFIG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BaixarVideosYT", "config.json")


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def default_download_dir() -> str:
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def fmt_duration(sec: int | None) -> str:
    if not sec:
        return ""
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def friendly_error(e: BaseException) -> str:
    msg = str(e).replace("ERROR: ", "")
    low = msg.lower()
    if "unsupported url" in low or "is not a valid url" in low:
        return "Esse link não parece ser um vídeo válido do YouTube."
    if "private video" in low:
        return "Esse vídeo é privado."
    if "sign in to confirm your age" in low:
        return "Esse vídeo tem restrição de idade e exige login no YouTube."
    if "video unavailable" in low:
        return "Vídeo indisponível (removido, bloqueado ou privado)."
    if "getaddrinfo failed" in low or "unable to download webpage" in low:
        return "Não foi possível acessar o YouTube. Verifique sua conexão com a internet."
    return msg


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        icon = resource_path("assets", "icon.ico")
        if os.path.isfile(icon):
            try:
                # default= aplica o ícone também às caixas de diálogo
                self.iconbitmap(default=icon)
            except tk.TclError:
                pass
        self.minsize(620, 0)
        self.resizable(True, False)

        self.cfg = load_config()
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.info: dl.VideoInfo | None = None
        self.busy = False
        self.last_file: str | None = None

        self._build_ui()
        self._on_type_change()
        self.after(100, self._poll_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("VTitle.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Muted.TLabel", foreground="#666")
        style.configure("Big.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 6))

        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)

        ttk.Label(root, text="Baixar vídeos do YouTube", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))

        # Link
        ttk.Label(root, text="Link do vídeo:").grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(root, textvariable=self.url_var)
        self.url_entry.grid(row=1, column=1, sticky="ew")
        self.url_entry.bind("<Return>", lambda e: self._fetch())
        btns = ttk.Frame(root)
        btns.grid(row=1, column=2, sticky="e", padx=(8, 0))
        self.paste_btn = ttk.Button(btns, text="Colar", width=7, command=self._paste)
        self.paste_btn.pack(side="left")
        self.fetch_btn = ttk.Button(btns, text="Buscar", width=8, command=self._fetch)
        self.fetch_btn.pack(side="left", padx=(4, 0))

        # Info do vídeo
        info = ttk.LabelFrame(root, text="Vídeo", padding=10)
        info.grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)
        info.columnconfigure(0, weight=1)
        self.title_lbl = ttk.Label(info, text="Cole um link e clique em Buscar.",
                                   style="VTitle.TLabel", wraplength=560)
        self.title_lbl.grid(row=0, column=0, sticky="w")
        self.meta_lbl = ttk.Label(info, text="", style="Muted.TLabel")
        self.meta_lbl.grid(row=1, column=0, sticky="w")

        # Opções
        opts = ttk.LabelFrame(root, text="Opções", padding=10)
        opts.grid(row=3, column=0, columnspan=3, sticky="ew")
        opts.columnconfigure(1, weight=1)

        ttk.Label(opts, text="Tipo:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        self.type_var = tk.StringVar(value=self.cfg.get("type", "video"))
        tf = ttk.Frame(opts)
        tf.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(tf, text="Vídeo (com áudio)", value="video", variable=self.type_var,
                        command=self._on_type_change).pack(side="left")
        ttk.Radiobutton(tf, text="Somente áudio", value="audio", variable=self.type_var,
                        command=self._on_type_change).pack(side="left", padx=(16, 0))

        ttk.Label(opts, text="Qualidade:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self.quality_var = tk.StringVar()
        self.quality_cb = ttk.Combobox(opts, textvariable=self.quality_var, state="readonly", width=32)
        self.quality_cb.grid(row=1, column=1, sticky="w")

        ttk.Label(opts, text="Formato:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self.format_var = tk.StringVar()
        self.format_cb = ttk.Combobox(opts, textvariable=self.format_var, state="readonly", width=12)
        self.format_cb.grid(row=2, column=1, sticky="w")
        self.format_cb.bind("<<ComboboxSelected>>", lambda e: self._on_format_change())
        self.format_hint = ttk.Label(opts, text="", style="Muted.TLabel")
        self.format_hint.grid(row=3, column=1, sticky="w")

        ttk.Label(opts, text="Salvar em:").grid(row=4, column=0, sticky="w", pady=(8, 4), padx=(0, 8))
        df = ttk.Frame(opts)
        df.grid(row=4, column=1, sticky="ew", pady=(8, 4))
        df.columnconfigure(0, weight=1)
        out = self.cfg.get("out_dir")
        self.dir_var = tk.StringVar(value=out if out and os.path.isdir(out) else default_download_dir())
        ttk.Entry(df, textvariable=self.dir_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(df, text="Procurar...", command=self._choose_dir).grid(row=0, column=1, padx=(8, 0))

        # Ações
        actions = ttk.Frame(root)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        self.download_btn = ttk.Button(actions, text="Baixar", style="Big.TButton", command=self._download)
        self.download_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        self.open_btn = ttk.Button(actions, text="Abrir pasta", command=self._open_folder, state="disabled")
        self.open_btn.pack(side="right")

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=1000)
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew")
        self.status_lbl = ttk.Label(root, text="Pronto.")
        self.status_lbl.grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.detail_lbl = ttk.Label(root, text="", style="Muted.TLabel")
        self.detail_lbl.grid(row=7, column=0, columnspan=3, sticky="w")

        self.url_entry.focus_set()

    # ------------------------------------------------------------ helpers
    def _on_type_change(self) -> None:
        audio = self.type_var.get() == "audio"
        if audio:
            self.quality_cb["values"] = [f"{b} kbps" for b in dl.AUDIO_BITRATES]
            want = self.cfg.get("audio_quality", "192 kbps")
            self.quality_var.set(want if want in self.quality_cb["values"] else "192 kbps")
            self.format_cb["values"] = dl.AUDIO_FORMATS
            want = self.cfg.get("audio_format", "MP3")
        else:
            labels = [q.label for q in self.info.qualities] if self.info else ["Melhor disponível"]
            self.quality_cb["values"] = labels
            self.quality_var.set(labels[0])
            self.format_cb["values"] = dl.VIDEO_FORMATS
            want = self.cfg.get("video_format", "MP4")
        self.format_var.set(want if want in self.format_cb["values"] else self.format_cb["values"][0])
        self._on_format_change()

    def _on_format_change(self) -> None:
        fmt = self.format_var.get()
        hints = {
            "MP4": "Mais compatível: abre em qualquer player, celular e TV.",
            "MKV": "Mantém a qualidade original, sem conversão.",
            "WEBM": "Formato aberto, usado nativamente pelo YouTube.",
            "MOV": "Ideal para Apple / editores de vídeo.",
            "AVI": "Para players antigos (é recodificado, pode demorar mais).",
            "MP3": "Áudio mais compatível.",
            "M4A": "Áudio AAC, ótima qualidade e tamanho menor.",
            "OPUS": "Melhor qualidade por tamanho; menos compatível.",
            "WAV": "Sem compressão (arquivo grande).",
            "FLAC": "Sem perdas, comprimido.",
        }
        self.format_hint.config(text=hints.get(fmt, ""))
        if self.type_var.get() == "audio":
            lossless = fmt in dl.LOSSLESS_AUDIO
            self.quality_cb.config(state="disabled" if lossless else "readonly")

    def _paste(self) -> None:
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        self.url_var.set(text)
        self._fetch()

    def _choose_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.dir_var.get() or default_download_dir())
        if d:
            self.dir_var.set(os.path.normpath(d))

    def _open_folder(self) -> None:
        if self.last_file and os.path.exists(self.last_file):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.last_file)])
        else:
            os.startfile(self.dir_var.get())

    def _set_busy(self, busy: bool, downloading: bool = False) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for w in (self.fetch_btn, self.paste_btn, self.download_btn):
            w.config(state=state)
        self.url_entry.config(state=state)
        self.cancel_btn.config(state="normal" if downloading else "disabled")

    def _set_progress(self, fraction: float | None) -> None:
        if fraction is None:
            if str(self.progress["mode"]) != "indeterminate":
                self.progress.config(mode="indeterminate")
                self.progress.start(12)
        else:
            if str(self.progress["mode"]) != "determinate":
                self.progress.stop()
                self.progress.config(mode="determinate")
            self.progress["value"] = fraction * 1000

    # -------------------------------------------------------------- ações
    def _fetch(self) -> None:
        url = self.url_var.get().strip()
        if not url or self.busy:
            if not url:
                messagebox.showinfo(APP_NAME, "Cole o link de um vídeo do YouTube.")
            return
        self._set_busy(True)
        self.info = None
        self.title_lbl.config(text="Buscando informações do vídeo...")
        self.meta_lbl.config(text="")
        self.status_lbl.config(text="Buscando...")
        self.detail_lbl.config(text="")
        self._set_progress(None)

        def work():
            try:
                self.events.put(("info", dl.fetch_info(url)))
            except BaseException as e:
                self.events.put(("info_error", e))

        threading.Thread(target=work, daemon=True).start()

    def _download(self) -> None:
        if self.busy:
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo(APP_NAME, "Cole o link de um vídeo do YouTube.")
            return
        out_dir = self.dir_var.get().strip()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            messagebox.showerror(APP_NAME, "A pasta de destino é inválida.")
            return

        audio = self.type_var.get() == "audio"
        fmt = self.format_var.get()
        height = None
        bitrate = "192"
        if audio:
            bitrate = self.quality_var.get().split()[0]
        elif self.info:
            label = self.quality_var.get()
            height = next((q.height for q in self.info.qualities if q.label == label), None)

        self.cfg.update(out_dir=out_dir, type=self.type_var.get())
        if audio:
            self.cfg.update(audio_format=fmt, audio_quality=self.quality_var.get())
        else:
            self.cfg["video_format"] = fmt
        save_config(self.cfg)

        self.cancel_event.clear()
        self._set_busy(True, downloading=True)
        self.open_btn.config(state="disabled")
        self.status_lbl.config(text="Iniciando...")
        self.detail_lbl.config(text="")

        def on_progress(p: dl.Progress) -> None:
            self.events.put(("progress", p))

        def work():
            try:
                path = dl.download(url, out_dir, audio, fmt, height, bitrate, on_progress, self.cancel_event)
                self.events.put(("done", path))
            except DownloadCancelled:
                self.events.put(("cancelled", None))
            except BaseException as e:
                if self.cancel_event.is_set():
                    self.events.put(("cancelled", None))
                else:
                    self.events.put(("error", e))

        threading.Thread(target=work, daemon=True).start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.cancel_btn.config(state="disabled")
        self.status_lbl.config(text="Cancelando...")

    def _on_close(self) -> None:
        if self.busy and self.cancel_btn["state"] == "normal":
            if not messagebox.askyesno(APP_NAME, "Há um download em andamento. Deseja cancelar e sair?"):
                return
            self.cancel_event.set()
        self.destroy()

    # ------------------------------------------------------------- eventos
    def _poll_events(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                self._handle(kind, data)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _handle(self, kind: str, data) -> None:
        if kind == "info":
            self.info = data
            self.title_lbl.config(text=data.title)
            meta = " • ".join(x for x in (data.uploader, fmt_duration(data.duration)) if x)
            self.meta_lbl.config(text=meta)
            self._on_type_change()
            self._set_progress(0)
            self.status_lbl.config(text="Escolha a qualidade e o formato e clique em Baixar.")
            self._set_busy(False)
        elif kind == "info_error":
            self.title_lbl.config(text="Não foi possível obter o vídeo.")
            self._set_progress(0)
            self.status_lbl.config(text="Erro.")
            self._set_busy(False)
            messagebox.showerror(APP_NAME, friendly_error(data))
        elif kind == "progress":
            p: dl.Progress = data
            if not self.cancel_event.is_set():
                self.status_lbl.config(text=p.stage)
            self.detail_lbl.config(text=p.detail)
            self._set_progress(p.fraction)
        elif kind == "done":
            self.last_file = data
            self._set_progress(1)
            self.status_lbl.config(text="Download concluído!")
            self.detail_lbl.config(text=data)
            self.open_btn.config(state="normal")
            self._set_busy(False)
        elif kind == "cancelled":
            self._set_progress(0)
            self.status_lbl.config(text="Download cancelado.")
            self.detail_lbl.config(text="")
            self._set_busy(False)
        elif kind == "error":
            self._set_progress(0)
            self.status_lbl.config(text="Erro no download.")
            self.detail_lbl.config(text="")
            self._set_busy(False)
            messagebox.showerror(APP_NAME, friendly_error(data))


def main() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            # Faz a barra de tarefas usar o ícone do app em vez do padrão
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
