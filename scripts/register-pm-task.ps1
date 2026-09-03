# Register a read-only `pm` command with Windows Task Scheduler.
# Called by `pm schedule add`. Nothing that writes to Jira is allowed
# through this script — the Python side refuses those commands first.
#
#   powershell -File register-pm-task.ps1 -Name today -Command "today" `
#       -Kind weekdays -Time 08:30 -Days "mon,tue,wed,thu,fri"

param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(Mandatory = $true)][string]$Kind,
    [Parameter(Mandatory = $true)][string]$Time,
    [string]$Days = "mon,tue,wed,thu,fri"
)

$taskName = "pm\$Name"
$pm = Get-Command pm -ErrorAction SilentlyContinue
if (-not $pm) {
    Write-Error "pm is not on PATH. Install with: pip install -e ."
    exit 1
}

$argList = $Command
$action = New-ScheduledTaskAction -Execute $pm.Source -Argument $argList
$parts = $Time.Split(":")
$hour = [int]$parts[0]
$minute = [int]$parts[1]
$at = Get-Date -Hour $hour -Minute $minute -Second 0

if ($Kind -eq "weekdays") {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $at
} else {
    $map = @{
        mon = "Monday"; tue = "Tuesday"; wed = "Wednesday"
        thu = "Thursday"; fri = "Friday"; sat = "Saturday"; sun = "Sunday"
    }
    $chosen = @()
    foreach ($d in $Days.Split(",")) {
        $key = $d.Trim().ToLower()
        if ($map.ContainsKey($key)) { $chosen += $map[$key] }
    }
    if (-not $chosen) { $chosen = @("Friday") }
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $chosen -At $at
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Force | Out-Null
Write-Output "Registered $taskName"
