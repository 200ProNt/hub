param(
    [string]$Python = 'py',
    [string]$Output = (Join-Path $PSScriptRoot '..\dist'),
    [string]$InnoSetup
)
$ErrorActionPreference = 'Stop'
$Output = [IO.Path]::GetFullPath($Output)
$build = Join-Path $Output 'build'
New-Item -ItemType Directory -Force $build | Out-Null
$icon = Join-Path $build 'hub.ico'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    $root = (Get-Location).Path
    & $Python (Join-Path $PSScriptRoot 'icon.py') $icon
    if ($LASTEXITCODE) { throw 'Не удалось создать значок Hub' }
    & $Python -m PyInstaller --noconfirm --onefile --windowed --name Hub `
        --icon $icon --specpath $build --workpath $build --distpath $Output `
        --add-data "$icon;." --add-data "$root\native\window.xaml;native" --add-data "$root\README.md;." `
        --add-data "$root\web\drop.html;web" --add-data "$root\web\transfer.html;web" `
        --add-data "$root\web\transfer.js;web" `
        --add-data "$root\LICENSE;." "$root\desktop.py"
    if ($LASTEXITCODE) { throw 'Не удалось собрать Hub.exe' }
    if ($InnoSetup) {
        $version = (Select-String -Path 'server.py' -Pattern '^VERSION = "([0-9.]+)"$').Matches[0].Groups[1].Value
        & $InnoSetup "/DHubVersion=$version" "/DHubExe=$(Join-Path $Output 'Hub.exe')" "/DHubIcon=$icon" "/O$Output" (Join-Path $PSScriptRoot 'setup.iss')
        if ($LASTEXITCODE) { throw 'Не удалось собрать установщик Hub' }
    }
    Compress-Archive -LiteralPath @(
        (Join-Path $Output 'Hub.exe'),
        (Join-Path $PSScriptRoot 'Setup.cmd'),
        (Join-Path $PSScriptRoot 'Setup.ps1'),
        (Join-Path $PSScriptRoot 'Install.txt')
    ) -DestinationPath (Join-Path $Output 'Hub-Windows-x64.zip') -Force
} finally {
    Pop-Location
}
