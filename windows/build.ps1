param(
    [string]$Python = 'py',
    [string]$Output = (Join-Path $PSScriptRoot '..\dist'),
    [string]$InnoSetup,
    [string]$Cargo = 'cargo'
)
$ErrorActionPreference = 'Stop'
$Python = (Get-Command $Python -CommandType Application | Select-Object -First 1).Source
$Cargo = (Get-Command $Cargo -CommandType Application | Select-Object -First 1).Source
$originalPath = $env:Path
$Output = [IO.Path]::GetFullPath($Output)
$build = Join-Path $Output 'build'
New-Item -ItemType Directory -Force $build | Out-Null
Push-Location (Join-Path $PSScriptRoot '..')
try {
    $root = (Get-Location).Path
    $rustBuild = Join-Path $build 'rust'
    & $Cargo build --locked --release --manifest-path "$root/rust/diskmap-worker/Cargo.toml" --target-dir $rustBuild
    if ($LASTEXITCODE) { throw 'Не удалось собрать Rust Worker для Windows' }
    $worker = Join-Path $rustBuild 'release\hub-diskmap-worker.exe'
    if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) { throw 'Не найден собранный Rust Worker' }
    $icon = Join-Path $root 'web\hub-icon.ico'
    $iconHash = (Get-FileHash -LiteralPath $icon -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
    # PyInstaller ищет DLL в PATH. В сборку могут попасть системные DLL соседних приложений.
    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
    & $Python -m PyInstaller --noconfirm --onefile --windowed --name Hub `
        --icon $icon --specpath $build --workpath $build --distpath $Output --add-binary "$worker;bin" `
        --add-data "$root/native/material;native/material" --add-data "$root/web/fonts;web/fonts" --add-data "$root/web/hub-icon*;web" `
        --add-data "$root\native\window.xaml;native" --add-data "$root/native/flags;native/flags" --add-data "$root\README.md;." `
        --add-data "$root\web\drop.html;web" --add-data "$root\web\transfer.html;web" `
        --add-data "$root\web\transfer.js;web" `
        --add-data "$root\LICENSE;." "$root\desktop.py"
    if ($LASTEXITCODE) { throw 'Не удалось собрать Hub.exe' }
    $env:Path = $originalPath
    if ($InnoSetup) {
        $version = (Select-String -Path 'server.py' -Pattern '^VERSION = "([0-9.]+)"$').Matches[0].Groups[1].Value
        & $InnoSetup "/DHubVersion=$version" "/DHubExe=$(Join-Path $Output 'Hub.exe')" "/DHubIcon=$icon" "/DHubIconName=Hub-$iconHash.ico" "/O$Output" (Join-Path $PSScriptRoot 'setup.iss')
        if ($LASTEXITCODE) { throw 'Не удалось собрать установщик Hub' }
    }
    Compress-Archive -LiteralPath @(
        (Join-Path $Output 'Hub.exe'),
        $icon,
        (Join-Path $PSScriptRoot 'Setup.cmd'),
        (Join-Path $PSScriptRoot 'Setup.ps1'),
        (Join-Path $PSScriptRoot 'Install.txt')
    ) -DestinationPath (Join-Path $Output 'Hub-Windows-x64.zip') -Force
} finally {
    $env:Path = $originalPath
    Pop-Location
}
