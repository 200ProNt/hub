$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System.Runtime.InteropServices;
public static class HubShell {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    public static extern void SHChangeNotify(int eventId, uint flags, string item, System.IntPtr other);
}
'@

try {
    $profileDir = Join-Path $env:LOCALAPPDATA 'Hub'
    $applicationDir = Join-Path $profileDir 'App'
    $application = Join-Path $applicationDir 'Hub.exe'
    $icon = Join-Path $PSScriptRoot 'hub-icon.ico'
    $oldRoot = $null
    $arguments = ''
    if (-not (Test-Path (Join-Path $profileDir 'data'))) {
        $message = 'Перенести данные старого Hub? Сначала закрой старую версию через её значок в трее или окно консоли.'
        $answer = [Windows.Forms.MessageBox]::Show($message, 'Установка Hub', 'YesNoCancel', 'Question')
        if ($answer -eq 'Cancel') { return }
        if ($answer -eq 'Yes') {
            $picker = New-Object Windows.Forms.FolderBrowserDialog
            try {
                $picker.Description = 'Папка старого Hub с файлами server.py и data'
                $picker.ShowNewFolderButton = $false
                if ($picker.ShowDialog() -ne 'OK') { return }
                $oldRoot = $picker.SelectedPath
            } finally { $picker.Dispose() }
            if (-not (Test-Path (Join-Path $oldRoot 'server.py') -PathType Leaf) -or
                -not (Test-Path (Join-Path $oldRoot 'data') -PathType Container)) {
                throw 'В выбранной папке нет server.py или data. Запусти Setup.cmd и выбери папку старого Hub.'
            }
            $arguments = '--migrate "' + $oldRoot.TrimEnd('\') + '"'
        }
    }

    New-Item -ItemType Directory -Force $applicationDir | Out-Null
    $iconHash = (Get-FileHash -LiteralPath $icon -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
    $installedIcon = Join-Path $applicationDir "Hub-$iconHash.ico"
    if ([IO.Path]::GetFullPath($icon) -ne $installedIcon) {
        Copy-Item -LiteralPath $icon -Destination $installedIcon -Force
    }
    $package = Join-Path $PSScriptRoot 'Hub.exe'
    if ([IO.Path]::GetFullPath($package) -ne $application) {
        $staged = Join-Path $applicationDir ('Hub-' + [Guid]::NewGuid() + '.tmp')
        try {
            Copy-Item -LiteralPath $package -Destination $staged
            if (Test-Path -LiteralPath $application) {
                [IO.File]::Replace($staged, $application, [NullString]::Value)
            } else {
                [IO.File]::Move($staged, $application)
            }
        } finally {
            if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged }
        }
    }

    # SHCNE_UPDATEITEM, SHCNF_PATHW
    [HubShell]::SHChangeNotify(0x2000, 0x0005, $application, [IntPtr]::Zero)
    $shell = New-Object -ComObject WScript.Shell
    foreach ($folder in @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs'))) {
        $link = Join-Path $folder 'Hub.lnk'
        $shortcut = $shell.CreateShortcut($link)
        $shortcut.TargetPath = $application
        $shortcut.WorkingDirectory = $applicationDir
        $shortcut.IconLocation = "$installedIcon,0"
        $shortcut.Description = 'Hub — инструменты для Windows'
        $shortcut.Save()
        [HubShell]::SHChangeNotify(0x2000, 0x0005, $link, [IntPtr]::Zero)
    }
    if ($arguments) { Start-Process -FilePath $application -ArgumentList $arguments }
    else { Start-Process -FilePath $application }
} catch {
    [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Установка Hub', 'OK', 'Error')
}
