param(
    [ValidateSet('all','draft-512-10','balanced-768-20','detail-1024-25','quality-1024-40','guidance-1024-25-cfg6','decode-1024-25-tile512')]
    [string]$Preset = 'all',
    [int]$Repeat = 1,
    [double]$MaxVram = 7.0
)
$ErrorActionPreference = 'Stop'
$benchPython = 'python'
& $benchPython (Join-Path $PSScriptRoot 'benchmark.py') --preset $Preset --repeat $Repeat --max-vram $MaxVram
if ($LASTEXITCODE -ne 0) { throw 'Benchmark failed. See the saved log and result files.' }
