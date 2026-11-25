<p align="center">
  <img src="assets/icon.png" width="96" alt="Ícone do Baixar Vídeos YT">
</p>

<h1 align="center">Baixar Vídeos YT</h1>

<p align="center">
  Programa para Windows que baixa vídeos e áudios do YouTube escolhendo a qualidade e o formato.
</p>

<p align="center">
  <a href="../../releases/latest"><b>⬇️ Baixar o .exe</b></a>
</p>

---

## Funcionalidades

- Cole o link e veja título, canal e duração do vídeo.
- **Qualidade de vídeo:** lista só as resoluções que o vídeo realmente tem (até 4K/8K), com tamanho aproximado.
- **Formatos de vídeo:** MP4, MKV, WEBM, MOV e AVI.
- **Somente áudio:** MP3, M4A, OPUS, WAV e FLAC, com bitrate de 96 a 320 kbps.
- Barra de progresso com velocidade e tempo restante, além de botão para cancelar.
- Lembra a última pasta e os últimos formatos usados.
- **Não precisa instalar nada:** ffmpeg e Deno já vêm dentro do `.exe`.

## Como usar

1. Baixe o `BaixarVideosYT.exe` na página de [Releases](../../releases/latest) e abra.
2. Cole o link do YouTube e clique em **Buscar**.
3. Escolha **Vídeo** ou **Somente áudio**, a qualidade e o formato.
4. Escolha a pasta de destino e clique em **Baixar**.

> Na primeira execução, o Windows SmartScreen pode avisar que o app é desconhecido (ele não é assinado digitalmente). Para abrir mesmo assim, clique em **Mais informações → Executar assim mesmo**.

## Rodando a partir do código

Requer **Python 3.11+** no Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

## Gerando o executável

```powershell
.\build.ps1
```

O script cria o ambiente virtual (se preciso), instala as dependências, copia o ffmpeg e o Deno para `bin/` e gera `dist\BaixarVideosYT.exe` com o PyInstaller.

## Quando parar de funcionar

O YouTube muda com frequência. Se os downloads começarem a falhar, atualize o yt-dlp e gere o `.exe` de novo:

```powershell
.\.venv\Scripts\python -m pip install -U "yt-dlp[default]"
.\build.ps1
```

## Estrutura do projeto

| Arquivo | Descrição |
| --- | --- |
| `app.py` | Interface gráfica (Tkinter) |
| `downloader.py` | Busca de informações, download e conversão (yt-dlp + ffmpeg) |
| `build.ps1` | Gera o executável com PyInstaller |
| `requirements.txt` | Dependências Python |
| `assets/icon.ico` | Ícone do aplicativo |
| `assets/icon.png` | Ícone em PNG (usado neste README) |

## Tecnologias

- [yt-dlp](https://github.com/yt-dlp/yt-dlp): extração e download
- [FFmpeg](https://ffmpeg.org/) via [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg): junção e conversão de mídia
- [Deno](https://deno.com/): runtime JavaScript exigido pelo YouTube
- [PyInstaller](https://pyinstaller.org/): empacotamento em `.exe`

## Aviso

Use este programa apenas para baixar conteúdo que você tem direito de usar, como seus próprios vídeos, conteúdo em domínio público ou com licença que permita download. Respeite os direitos autorais e os Termos de Serviço do YouTube.
