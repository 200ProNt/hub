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
    $version = (Select-String -Path 'server.py' -Pattern '^VERSION = "([0-9.]+)"$').Matches[0].Groups[1].Value
    $runtimeName = "HubRuntime-$version"
    $bundle = Join-Path $Output 'Hub'
    $runtime = Join-Path $bundle $runtimeName
    $rustBuild = Join-Path $build 'rust'
    & $Cargo build --locked --release --manifest-path "$root/rust/diskmap-worker/Cargo.toml" --target-dir $rustBuild
    if ($LASTEXITCODE) { throw 'Не удалось собрать Rust Worker для Windows' }
    $worker = Join-Path $rustBuild 'release\hub-diskmap-worker.exe'
    if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) { throw 'Не найден собранный Rust Worker' }
    $icon = Join-Path $root 'web\hub-icon.ico'
    $iconHash = (Get-FileHash -LiteralPath $icon -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
    # PyInstaller ищет DLL в PATH. В сборку могут попасть системные DLL соседних приложений.
    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
    & $Python -m PyInstaller --noconfirm --onedir --contents-directory $runtimeName --windowed --name Hub `
        --icon $icon --specpath $build --workpath $build --distpath $Output --add-binary "$worker;bin" `
        --add-data "$root/native/material;native/material" --add-data "$root/web/fonts;web/fonts" --add-data "$root/web/hub-icon*;web" `
        --add-data "$root\native\window.xaml;native" --add-data "$root/native/flags;native/flags" --add-data "$root\README.md;." `
        --add-data "$root\web\drop.html;web" --add-data "$root\web\transfer.html;web" `
        --add-data "$root\web\transfer.js;web" `
        --add-data "$root\LICENSE;." "$root\desktop.py"
    if ($LASTEXITCODE) { throw 'Не удалось собрать Hub.exe' }
    $pythonDll = & $Python -c 'import sys; print("python%d%d.dll" % sys.version_info[:2])'
    if ($LASTEXITCODE) { throw 'Не удалось определить версию Python' }
    foreach ($file in @($pythonDll, 'vcruntime140.dll', 'vcruntime140_1.dll', 'bin/hub-diskmap-worker.exe')) {
        if (-not (Test-Path -LiteralPath (Join-Path $runtime $file) -PathType Leaf)) {
            throw "В комплекте Hub отсутствует $file"
        }
    }
    $env:Path = $originalPath
    if ($InnoSetup) {
        & $InnoSetup "/DHubVersion=$version" "/DHubExe=$(Join-Path $bundle 'Hub.exe')" "/DHubRuntime=$runtime" "/DHubRuntimeName=$runtimeName" "/DHubIcon=$icon" "/DHubIconName=Hub-$iconHash.ico" "/O$Output" (Join-Path $PSScriptRoot 'setup.iss')
        if ($LASTEXITCODE) { throw 'Не удалось собрать установщик Hub' }
    }
    Compress-Archive -LiteralPath @(
        (Join-Path $bundle 'Hub.exe'),
        $runtime,
        $icon,
        (Join-Path $PSScriptRoot 'Setup.cmd'),
        (Join-Path $PSScriptRoot 'Setup.ps1'),
        (Join-Path $PSScriptRoot 'Install.txt')
    ) -DestinationPath (Join-Path $Output 'Hub-Windows-x64.zip') -Force
} finally {
    $env:Path = $originalPath
    Pop-Location
}
