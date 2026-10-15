# Builds bin\MiniSnap.exe and bin\MiniSnap-Setup.exe with the C# compiler that ships with Windows (.NET Framework 4.x).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$fw = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
if (-not (Test-Path "$fw\csc.exe")) { $fw = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319' }
$csc = "$fw\csc.exe"
$winmd = Join-Path $env:WINDIR 'System32\WinMetadata'
$out = Join-Path $root 'bin'
$obj = Join-Path $root 'obj'
New-Item -ItemType Directory -Force $out, $obj | Out-Null

function Invoke-Csc([string[]]$cscArgs) {
    & $csc /nologo /optimize+ /codepage:65001 /platform:anycpu @cscArgs
    if ($LASTEXITCODE -ne 0) { throw "Build failed" }
}

$refs = @(
    '/r:System.dll', '/r:System.Core.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll', '/r:Microsoft.VisualBasic.dll', '/r:System.Web.Extensions.dll',
    "/r:$fw\System.Runtime.dll",
    "/r:$winmd\Windows.Foundation.winmd", "/r:$winmd\Windows.Graphics.winmd", "/r:$winmd\Windows.Media.winmd",
    "/r:$winmd\Windows.Globalization.winmd", "/r:$winmd\Windows.Storage.winmd"
)
$sources = Get-ChildItem (Join-Path $root 'src') -Filter *.cs | ForEach-Object { $_.FullName }
$manifest = "/win32manifest:$root\app.manifest"

# Pass 1 builds the app so it can draw its own .ico; pass 2 embeds that icon in the exe.
$ico = Join-Path $obj 'MiniSnap.ico'
Invoke-Csc (@('/target:winexe', "/out:$obj\MiniSnap.exe", $manifest) + $refs + $sources)
& "$obj\MiniSnap.exe" --export-icon $ico | Out-Null
if (-not (Test-Path $ico)) { throw "Icon export failed" }
Invoke-Csc (@('/target:winexe', "/out:$out\MiniSnap.exe", $manifest, "/win32icon:$ico") + $refs + $sources)
Write-Host "OK: $out\MiniSnap.exe"

# Installer: a single exe that carries MiniSnap.exe as an embedded resource.
$setupDir = Join-Path $root 'installer'
if (Test-Path $setupDir) {
    $setupSources = @((Get-ChildItem $setupDir -Filter *.cs | ForEach-Object { $_.FullName })) + @("$root\src\Icons.cs", "$root\src\Shapes.cs", "$root\src\Strings.cs", "$root\src\Theme.cs")
    Invoke-Csc (@('/target:winexe', "/out:$out\MiniSnap-Setup.exe", "/win32manifest:$root\app.manifest", "/win32icon:$ico",
        "/resource:$out\MiniSnap.exe,MiniSnap.exe",
        '/r:System.dll', '/r:System.Core.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll', '/r:Microsoft.CSharp.dll') + $setupSources)
    Write-Host "OK: $out\MiniSnap-Setup.exe"
}
