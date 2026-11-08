$ErrorActionPreference = 'Stop'
$target = Join-Path $env:USERPROFILE 'video-dubbing-local\dub_8s.py'
$backup = $target + '.bak-codex-20261107'
Copy-Item -LiteralPath $target -Destination $backup
$text = [System.IO.File]::ReadAllText($target)
$text = $text.Replace('raise RuntimeError("Hebrew translation is empty.")', 'raise RuntimeError("Hebrew translation is empty. Enter a Hebrew translation in the agent and run again.")')
$old = @'
        raise RuntimeError("Hebrew translation looks wrong (no Hebrew or Arabic letters detected). "
                           "Edit hebrew_override.txt with correct Hebrew and run again.")
'@
$new = @'
        raise RuntimeError("Automatic translation was not valid Hebrew. Enter or correct the Hebrew translation in the agent's translation box and run dubbing again.")
'@
if (-not $text.Contains($old)) { throw 'Expected translation validation block not found; no changes made.' }
$text = $text.Replace($old, $new)
[System.IO.File]::WriteAllText($target, $text, [System.Text.UTF8Encoding]::new($false))
Write-Host "Fixed the translation error handling. Backup: $backup"