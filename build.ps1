# Gera dist\BaixarVideosYT.exe (um único arquivo, com ffmpeg e deno embutidos)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
.\.venv\Scripts\python -m pip install -q -r requirements.txt

# Copia ffmpeg e deno com nomes padrão para a pasta bin\
New-Item -ItemType Directory -Force bin | Out-Null
$ffmpeg = & .\.venv\Scripts\python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
$deno = & .\.venv\Scripts\python -c "import deno; print(deno.find_deno_bin())"
Copy-Item $ffmpeg bin\ffmpeg.exe -Force
Copy-Item $deno bin\deno.exe -Force

.\.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed `
    --name BaixarVideosYT `
    --icon assets\icon.ico `
    --add-data "assets\icon.ico;assets" `
    --add-binary "bin\ffmpeg.exe;bin" `
    --add-binary "bin\deno.exe;bin" `
    --collect-data yt_dlp_ejs `
    app.py

Write-Host ""
Write-Host "Pronto: $PSScriptRoot\dist\BaixarVideosYT.exe"
