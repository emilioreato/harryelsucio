$ErrorActionPreference = 'Stop'

$root = [System.IO.Path]::GetFullPath($PSScriptRoot)
$scriptPath = [System.IO.Path]::GetFullPath((Join-Path $root 'app.py'))
$pythonExePattern = '(?:"[^"\r\n]*python(?:w|[0-9.]*)?\.exe"|[^\s"]*python(?:w|[0-9.]*)?\.exe)'
$scriptArgPattern = '(?:"' + [regex]::Escape($scriptPath) + '"|' + [regex]::Escape($scriptPath) + ')'
$scriptPattern = '(?i)^\s*' + $pythonExePattern + '\s+' + $scriptArgPattern + '(?:\s|$)'
$legacyScriptPattern = '(?i)^\s*' + $pythonExePattern + '\s+"?app\.py"?(?:\s|$)'
$statePath = Join-Path $root '.lumbre-instance.json'
$statePid = 0
$stateWriteTime = $null
$statePidBelongsToLumbre = $false

if (Test-Path -LiteralPath $statePath) {
    try {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $statePid = [int]$state.pid
        $stateWriteTime = (Get-Item -LiteralPath $statePath).LastWriteTimeUtc
    }
    catch {
        $statePid = 0
        $stateWriteTime = $null
    }
}

function Test-LumbreEndpoint([int]$Port) {
    $baseUrl = "http://127.0.0.1:$Port"
    try {
        $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 1 -ErrorAction Stop
        if ($health.app -eq 'Lumbre') {
            return $true
        }
    }
    catch {
        # La ruta health no existia en versiones anteriores.
    }

    try {
        $scenes = Invoke-RestMethod -Uri "$baseUrl/api/scenes" -TimeoutSec 1 -ErrorAction Stop
        $detectors = Invoke-RestMethod -Uri "$baseUrl/api/detectors" -TimeoutSec 1 -ErrorAction Stop
        return (
            $scenes.PSObject.Properties.Name -contains 'scenes' -and
            $detectors.PSObject.Properties.Name -contains 'detectors' -and
            @($detectors.detectors).Count -gt 0
        )
    }
    catch {
        return $false
    }
}

function Get-ListeningProcessIds([int]$Port) {
    try {
        $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        return @($connections | ForEach-Object { [int]$_.OwningProcess })
    }
    catch {
        $netstat = & "$env:WINDIR\System32\netstat.exe" -ano -p tcp 2>$null
        $processIds = @(
            foreach ($line in $netstat) {
                if ($line -match ("^\s*TCP\s+\S+:" + $Port + "\s+\S+\s+LISTENING\s+(\d+)\s*$")) {
                    [int]$Matches[1]
                }
            }
        )
        return $processIds
    }
}

try {
    $stoppedIds = [System.Collections.Generic.HashSet[int]]::new()

    # El PID del estado solo se considera propio si sigue siendo Python y su
    # proceso nació antes de que Lumbre escribiera ese estado. Esto evita matar
    # otro proceso si Windows ya reutilizó el PID de una instancia antigua.
    if ($statePid -gt 0 -and $null -ne $stateWriteTime) {
        $trackedProcess = Get-Process -Id $statePid -ErrorAction SilentlyContinue
        if (
            $null -ne $trackedProcess -and
            $trackedProcess.ProcessName -match '^python(?:w|[0-9.]*)?$' -and
            $trackedProcess.StartTime.ToUniversalTime() -le $stateWriteTime
        ) {
            $statePidBelongsToLumbre = $true
            Stop-Process -Id $statePid -Force -ErrorAction Stop
            [void]$stoppedIds.Add($statePid)
            Write-Output ("Proceso de Lumbre detenido desde el estado local (PID {0})." -f $statePid)
        }
    }

    $pythonProcesses = @(
        Get-CimInstance -ClassName Win32_Process -Filter "Name LIKE 'python%.exe'" |
            Where-Object { $_.Name -match '^python(?:w|[0-9.]*)?\.exe$' }
    )
    $targetList = [System.Collections.Generic.List[object]]::new()
    $targetIds = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($process in $pythonProcesses) {
        $commandLine = [string]$process.CommandLine
        if (
            $commandLine -match $scriptPattern -and
            -not $stoppedIds.Contains([int]$process.ProcessId) -and
            $targetIds.Add([int]$process.ProcessId)
        ) {
            $targetList.Add($process)
        }
    }

    # Versiones anteriores lanzaban `app.py` como ruta relativa y no guardaban
    # el PID. Solo se aceptan si la API confirma que el puerto es Lumbre y el
    # proceso Python que lo escucha tiene `app.py` como script principal.
    foreach ($port in 8501..8520) {
        $ownerIds = @(Get-ListeningProcessIds -Port $port)
        if ($ownerIds.Count -eq 0) {
            continue
        }
        if (-not (Test-LumbreEndpoint -Port $port)) {
            continue
        }
        foreach ($ownerId in $ownerIds) {
            $legacyProcess = $pythonProcesses |
                Where-Object {
                    $_.ProcessId -eq $ownerId -and
                    ([string]$_.CommandLine -match $legacyScriptPattern)
                } |
                Select-Object -First 1
            if (
                $null -ne $legacyProcess -and
                -not $stoppedIds.Contains([int]$ownerId) -and
                $targetIds.Add([int]$ownerId)
            ) {
                $targetList.Add($legacyProcess)
            }
        }
    }
    $targets = @($targetList.ToArray())

    if ($targets.Count -eq 0) {
        Write-Output 'No quedan procesos de Lumbre de esta copia.'
    }
    else {
        foreach ($process in $targets) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            [void]$stoppedIds.Add([int]$process.ProcessId)
            Write-Output ("Proceso de Lumbre detenido (PID {0})." -f $process.ProcessId)
        }
        foreach ($process in $targets) {
            Wait-Process -Id $process.ProcessId -Timeout 5 -ErrorAction SilentlyContinue
        }

        $restantes = @(
            Get-CimInstance -ClassName Win32_Process -Filter "Name LIKE 'python%.exe'" |
                Where-Object { $stoppedIds.Contains([int]$_.ProcessId) }
        )
        if ($restantes.Count -gt 0) {
            throw 'Uno o mas procesos de Lumbre siguen activos.'
        }
    }

    if (Test-Path -LiteralPath $statePath) {
        if (-not $statePidBelongsToLumbre -or $stoppedIds.Contains($statePid)) {
            Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
        }
    }
}
catch {
    Write-Error ("No se pudieron comprobar o detener los procesos de Lumbre: {0}" -f $_.Exception.Message)
    exit 1
}

exit 0
