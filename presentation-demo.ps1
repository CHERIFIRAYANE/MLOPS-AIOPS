[CmdletBinding()]
param(
    [string]$Namespace = "aiops",
    [int]$PhaseSeconds = 18,
    [int]$RequestsPerPhase = 12,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$script:PortForwards = @()
$script:OriginalSettings = @{}
$script:DemoStartTime = Get-Date

function Write-Stage {
    param(
        [string]$Title,
        [string]$Detail = ""
    )

    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host $Title -ForegroundColor Cyan
    if ($Detail) {
        Write-Host $Detail
    }
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

function Invoke-Kubectl {
    param([string[]]$Arguments)

    if ($DryRun) {
        Write-Host "[dry-run] kubectl $($Arguments -join ' ')"
        return ""
    }

    return (& kubectl @Arguments)
}

function Wait-ForPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )

    if ($DryRun) { return }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            if (Test-NetConnection -ComputerName "127.0.0.1" -Port $Port -InformationLevel Quiet) {
                return
            }
        }
        catch {
        }

        Start-Sleep -Seconds 1
    }

    throw "Port $Port did not become ready within $TimeoutSeconds seconds."
}

function Start-PortForward {
    param(
        [string]$ServiceName,
        [int]$LocalPort
    )

    if ($DryRun) {
        Write-Host "[dry-run] start port-forward for $ServiceName on localhost:$LocalPort"
        return
    }

    $stdoutLog = Join-Path $env:TEMP "aiops-$ServiceName-portforward.out.log"
    $stderrLog = Join-Path $env:TEMP "aiops-$ServiceName-portforward.err.log"
    $arguments = @(
        "port-forward",
        "-n", $Namespace,
        "svc/$ServiceName",
        "$LocalPort`:$LocalPort"
    )

    $process = Start-Process -FilePath "kubectl" -ArgumentList $arguments -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

    $script:PortForwards += [pscustomobject]@{
        Service = $ServiceName
        Port = $LocalPort
        ProcessId = $process.Id
        StdOutLogPath = $stdoutLog
        StdErrLogPath = $stderrLog
    }

    Wait-ForPort -Port $LocalPort -TimeoutSeconds 30
}

function Get-CronjobEnvValue {
    param(
        [string]$Name,
        [string]$Fallback
    )

    if ($DryRun) { return $Fallback }

    $jsonPath = "jsonpath={.spec.jobTemplate.spec.template.spec.containers[0].env[?(@.name=='$Name')].value}"
    $value = Invoke-Kubectl @("get", "cronjob", "aiops-drift-detection", "-n", $Namespace, "-o", $jsonPath)

    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Fallback
    }

    return $value.Trim()
}

function Set-CronjobEnv {
    param(
        [string]$DriftThreshold,
        [string]$MinSamples,
        [string]$MinHours
    )

    Invoke-Kubectl @(
        "set", "env", "cronjob/aiops-drift-detection",
        "-n", $Namespace,
        "DRIFT_THRESHOLD=$DriftThreshold",
        "MIN_SAMPLES_FOR_RETRAIN=$MinSamples",
        "MIN_HOURS_BETWEEN_RETRAIN=$MinHours"
    ) | Out-Null
}

function Restore-CronjobEnv {
    if ($DryRun) { return }

    if ($script:OriginalSettings.Count -eq 0) { return }

    Set-CronjobEnv `
        -DriftThreshold $script:OriginalSettings.DRIFT_THRESHOLD `
        -MinSamples $script:OriginalSettings.MIN_SAMPLES_FOR_RETRAIN `
        -MinHours $script:OriginalSettings.MIN_HOURS_BETWEEN_RETRAIN
}

function Set-EchoMode {
    param([string]$Mode)

    if ($DryRun) {
        Write-Host "[dry-run] POST http://localhost:5000/mode { mode = $Mode }"
        return
    }

    $body = @{ mode = $Mode } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "http://localhost:5000/mode" -Body $body -ContentType "application/json" | Out-Null
    Write-Host "Echo server mode set to $Mode"
}

function Send-RequestBurst {
    param(
        [int]$Count,
        [int]$DelayMs = 250
    )

    if ($Count -le 0) { return }

    for ($i = 1; $i -le $Count; $i++) {
        if ($DryRun) {
            Write-Host "[dry-run] GET http://localhost:5000/echo ($i/$Count)"
            continue
        }

        try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5000/echo" -TimeoutSec 10 | Out-Null
        }
        catch {
            # 500 responses are expected in error mode; keep the burst moving.
        }

        Start-Sleep -Milliseconds $DelayMs
    }
}

function Wait-Phase {
    param([int]$Seconds)

    if ($DryRun -or $Seconds -le 0) {
        return
    }

    Start-Sleep -Seconds $Seconds
}

function Start-DriftCheckJob {
    $jobName = "demo-drift-$((Get-Date).ToString('yyyyMMdd-HHmmss'))"

    if ($DryRun) {
        Write-Host "[dry-run] kubectl create job --from=cronjob/aiops-drift-detection $jobName -n $Namespace"
        return $jobName
    }

    Invoke-Kubectl @(
        "create", "job",
        "--from=cronjob/aiops-drift-detection",
        $jobName,
        "-n", $Namespace
    ) | Out-Null

    return $jobName
}

function Wait-JobComplete {
    param(
        [string]$JobName,
        [int]$TimeoutSeconds = 240
    )

    if ($DryRun) {
        Write-Host "[dry-run] wait for job/$JobName completion"
        return
    }

    Invoke-Kubectl @(
        "wait",
        "--for=condition=complete",
        "job/$JobName",
        "-n", $Namespace,
        "--timeout=$TimeoutSeconds`s"
    ) | Out-Null
}

function Get-NewRetrainingJobName {
    param([datetime]$Since)

    if ($DryRun) {
        return "aiops-retrain-demo"
    }

    $jobsJson = Invoke-Kubectl @("get", "jobs", "-n", $Namespace, "-o", "json")
    if ([string]::IsNullOrWhiteSpace($jobsJson)) {
        return $null
    }

    $jobs = ($jobsJson | ConvertFrom-Json).items
    $candidates = @()

    foreach ($job in $jobs) {
        if ($job.metadata.name -like "aiops-retrain-*") {
            try {
                $created = [datetime]$job.metadata.creationTimestamp
                if ($created -ge $Since) {
                    $candidates += [pscustomobject]@{
                        Name = $job.metadata.name
                        Created = $created
                    }
                }
            }
            catch {
            }
        }
    }

    if ($candidates.Count -eq 0) {
        return $null
    }

    return ($candidates | Sort-Object Created | Select-Object -Last 1).Name
}

function Wait-ForRetrainingJob {
    param(
        [datetime]$Since,
        [int]$TimeoutSeconds = 180
    )

    if ($DryRun) {
        Write-Host "[dry-run] poll for aiops-retrain-* job created after $Since"
        return "aiops-retrain-demo"
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $jobName = Get-NewRetrainingJobName -Since $Since
        if ($jobName) {
            return $jobName
        }

        Start-Sleep -Seconds 3
    }

    return $null
}

function Show-Runbook {
    Write-Host "Presentation runbook:"
    Write-Host "  1. Open Grafana: http://localhost:3000"
    Write-Host "  2. Keep the AIOps dashboard on screen with auto-refresh enabled."
    Write-Host "  3. Follow the terminal output as the demo moves through normal -> slow -> error -> cpu -> retraining."
    Write-Host "  4. Watch the retraining job logs and the model health panel for the hot-reload confirmation."
}

try {
    Write-Stage -Title "AIOps Presentation Demo" -Detail "Target runtime: about 3-5 minutes. This sequence uses real cluster endpoints and real job creation."

    if (-not $DryRun) {
        $script:OriginalSettings = @{
            DRIFT_THRESHOLD = Get-CronjobEnvValue -Name "DRIFT_THRESHOLD" -Fallback "0.80"
            MIN_SAMPLES_FOR_RETRAIN = Get-CronjobEnvValue -Name "MIN_SAMPLES_FOR_RETRAIN" -Fallback "200"
            MIN_HOURS_BETWEEN_RETRAIN = Get-CronjobEnvValue -Name "MIN_HOURS_BETWEEN_RETRAIN" -Fallback "24"
        }
    }

    Write-Stage -Title "Step 0 - Start local access" -Detail "Starting port-forwards for echo-server, Prometheus, and Grafana."
    if (-not $DryRun) {
        Start-PortForward -ServiceName "echo-server" -LocalPort 5000
        Start-PortForward -ServiceName "prometheus" -LocalPort 9090
        Start-PortForward -ServiceName "grafana" -LocalPort 3000
    }
    else {
        Write-Host "[dry-run] start port-forward echo-server -> 5000"
        Write-Host "[dry-run] start port-forward prometheus -> 9090"
        Write-Host "[dry-run] start port-forward grafana -> 3000"
    }

    Show-Runbook

    Write-Stage -Title "Step 1 - Prepare a demo-friendly retraining profile" -Detail "This only changes the live CronJob env for the duration of the demo and restores it at the end."
    if (-not $DryRun) {
        Set-CronjobEnv -DriftThreshold "0.999" -MinSamples "20" -MinHours "0"
    }
    else {
        Write-Host "[dry-run] set CronJob env: DRIFT_THRESHOLD=0.999, MIN_SAMPLES_FOR_RETRAIN=20, MIN_HOURS_BETWEEN_RETRAIN=0"
    }

    Write-Stage -Title "Step 2 - Baseline traffic (normal mode)" -Detail "Show the dashboard in a calm state, then move to anomaly phases."
    Set-EchoMode -Mode "normal"
    Send-RequestBurst -Count $RequestsPerPhase
    Wait-Phase -Seconds $PhaseSeconds

    Write-Stage -Title "Step 3 - Slow response phase" -Detail "This should lift latency panels and anomaly score."
    Set-EchoMode -Mode "slow"
    Send-RequestBurst -Count $RequestsPerPhase
    Wait-Phase -Seconds $PhaseSeconds

    Write-Stage -Title "Step 4 - Error phase" -Detail "This should lift 5xx/error panels and show a different anomaly signature."
    Set-EchoMode -Mode "error"
    Send-RequestBurst -Count $RequestsPerPhase
    Wait-Phase -Seconds $PhaseSeconds

    Write-Stage -Title "Step 5 - CPU stress phase" -Detail "This should move the CPU and latency-related metrics."
    Set-EchoMode -Mode "cpu"
    Send-RequestBurst -Count $RequestsPerPhase
    Wait-Phase -Seconds $PhaseSeconds

    Write-Stage -Title "Step 6 - Trigger drift detection manually" -Detail "Create the CronJob-driven drift check immediately instead of waiting for the next 5-minute slot."
    $driftJobName = Start-DriftCheckJob
    Write-Host "Drift-check job created: $driftJobName"

    if (-not $DryRun) {
        Wait-JobComplete -JobName $driftJobName -TimeoutSeconds 240
        Write-Host "Drift-check job completed."
    }
    else {
        Write-Host "[dry-run] drift-check job would be waited on here."
    }

    Write-Stage -Title "Step 7 - Wait for the retraining job" -Detail "This is the core lifecycle proof: drift detection launches the actual retraining job."
    $retrainJobName = Wait-ForRetrainingJob -Since $script:DemoStartTime -TimeoutSeconds 180
    if ($retrainJobName) {
        Write-Host "Retraining job detected: $retrainJobName"
        if (-not $DryRun) {
            Wait-JobComplete -JobName $retrainJobName -TimeoutSeconds 240
            Write-Host "Retraining job completed."

            try {
                Write-Host ""
                Write-Host "Last retraining logs:" -ForegroundColor Yellow
                Invoke-Kubectl @("logs", "-n", $Namespace, "job/$retrainJobName", "--tail=40")
            }
            catch {
                Write-Host "Could not fetch retraining logs: $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }
    else {
        Write-Host "No retraining job appeared within the timeout window." -ForegroundColor Yellow
    }

    Write-Stage -Title "Step 8 - Return to normal mode" -Detail "Finish the demo by showing the system back in a healthy state."
    Set-EchoMode -Mode "normal"
    Send-RequestBurst -Count 6

    Write-Stage -Title "Demo summary" -Detail "Show Grafana panels for model health, anomaly score, retraining status, and the restored baseline."
    Write-Host "Recommended closing line: the system detects drift, triggers retraining, and hot-reloads the model without restarting the pod."
}
finally {
    if (-not $DryRun) {
        try {
            Restore-CronjobEnv
            Write-Host "CronJob settings restored to their original values." -ForegroundColor Green
        }
        catch {
            Write-Host "Warning: could not restore CronJob env cleanly. Please reset aiops-drift-detection manually." -ForegroundColor Yellow
        }
    }
}
