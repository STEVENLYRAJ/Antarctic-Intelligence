# AETHENTRA ERA5 bulk download, unattended: keeps Windows from idle-sleeping and relaunches the downloader if it exits
# before every job is finished (it resumes from data/raw/era5/_state.json). Exits by itself once all ERA5 jobs are finished.
# Start: powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File scripts\ops\era5_background.ps1
Set-Location 'h:\scientific-intelligence'
$sig = '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
$k = Add-Type -MemberDefinition $sig -Name Pwr -Namespace KeepAwake -PassThru
$null = $k::SetThreadExecutionState([uint32]"0x80000001")   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED (screen may still turn off)
$log = 'experiments\logs\era5_supervisor.log'
while ($true) {
  if (Select-String -Path 'experiments\logs\era5_bulk.log' -Pattern 'all ERA5 jobs finished' -Quiet) { break }
  $running = Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*era5_bulk_download*' }
  if ($running) { Start-Sleep -Seconds 60; continue }       # an instance is already running: never start a second one
  Add-Content $log "$(Get-Date -Format s) starting era5_bulk_download.py"
  $p = Start-Process -WindowStyle Hidden -FilePath python -ArgumentList 'scripts/era5_bulk_download.py' -PassThru `
       -RedirectStandardOutput 'experiments\logs\era5_bulk.out' -RedirectStandardError 'experiments\logs\era5_bulk.err'
  $p.WaitForExit()
  Add-Content $log "$(Get-Date -Format s) downloader exited (code $($p.ExitCode)); restart in 60 s"
  Start-Sleep -Seconds 60
}
$null = $k::SetThreadExecutionState([uint32]"0x80000000")
Add-Content $log "$(Get-Date -Format s) all ERA5 jobs finished; supervisor stopped"
