[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Manifest,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [string]$YtDlp = "yt-dlp",
    [string]$FfmpegLocation,
    [string]$CookiesFromBrowser,
    [string]$Proxy,
    [ValidateRange(144, 4320)]
    [int]$MinHeight = 720,
    [ValidateRange(144, 4320)]
    [int]$MaxHeight = 1080,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"

function Add-OptionalArgument {
    param(
        [System.Collections.Generic.List[string]]$Arguments,
        [string]$Name,
        [string]$Value
    )
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        $Arguments.Add($Name)
        $Arguments.Add($Value)
    }
}

function Invoke-YtDlp {
    param([string[]]$Arguments)
    & $YtDlp @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "yt-dlp failed with exit code $LASTEXITCODE"
    }
}

function Get-SubtitleLanguage {
    param([string]$Url)

    $arguments = [System.Collections.Generic.List[string]]::new()
    @("--dump-single-json", "--skip-download", "--no-playlist", "--no-warnings", $Url) |
        ForEach-Object { $arguments.Add($_) }
    Add-OptionalArgument $arguments "--cookies-from-browser" $CookiesFromBrowser
    Add-OptionalArgument $arguments "--proxy" $Proxy

    $jsonText = (& $YtDlp @arguments) -join "`n"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($jsonText)) {
        return $null
    }
    try {
        $metadata = $jsonText | ConvertFrom-Json
    } catch {
        return $null
    }

    $manual = @()
    $automatic = @()
    if ($metadata.subtitles) {
        $manual = @($metadata.subtitles.PSObject.Properties.Name | Where-Object { $_ -ne "live_chat" })
    }
    if ($metadata.automatic_captions) {
        $automatic = @($metadata.automatic_captions.PSObject.Properties.Name | Where-Object { $_ -ne "live_chat" })
    }

    $groups = @(
        @($manual | Where-Object { $_ -eq "en" }),
        @($manual | Where-Object { $_ -like "en*" }),
        @($automatic | Where-Object { $_ -eq "en" }),
        @($automatic | Where-Object { $_ -like "en*" }),
        @($manual | Where-Object { $_ -like "zh*" }),
        @($automatic | Where-Object { $_ -like "zh*" }),
        $manual,
        $automatic
    )
    foreach ($group in $groups) {
        $candidate = $group | Select-Object -First 1
        if ($candidate) {
            return $candidate
        }
    }
    return $null
}

$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$rows = @(Import-Csv -LiteralPath $manifestPath -Encoding UTF8)
if ($rows.Count -eq 0) {
    throw "Manifest contains no data rows: $manifestPath"
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$logPath = Join-Path $OutputRoot "下载状态.csv"
$statusRows = [System.Collections.Generic.List[object]]::new()

foreach ($row in $rows) {
    $folderName = [string]$row.folder_name
    $url = [string]$row.url
    if ([string]::IsNullOrWhiteSpace($folderName) -or [string]::IsNullOrWhiteSpace($url)) {
        $statusRows.Add([pscustomobject]@{
            folder_name = $folderName
            url = $url
            video = $false
            subtitle = $false
            subtitle_language = ""
            status = "invalid manifest row"
        })
        continue
    }
    if ($url -notmatch '^https://(www\.)?(youtube\.com/watch\?|youtu\.be/)') {
        $statusRows.Add([pscustomobject]@{
            folder_name = $folderName
            url = $url
            video = $false
            subtitle = $false
            subtitle_language = ""
            status = "unsupported URL"
        })
        continue
    }

    $topicDir = Join-Path $OutputRoot $folderName
    if ($PlanOnly) {
        Write-Output "PLAN`t$folderName`t$url`t$topicDir"
        continue
    }

    New-Item -ItemType Directory -Path $topicDir -Force | Out-Null
    $existingVideo = Get-ChildItem -LiteralPath $topicDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.BaseName -eq "高清源视频" -and $_.Extension -in @(".mp4", ".mkv", ".webm") } |
        Select-Object -First 1
    $status = "complete"
    $subtitleLanguage = [string]$row.subtitle_language

    try {
        if (-not $existingVideo) {
            $arguments = [System.Collections.Generic.List[string]]::new()
            @(
                "--continue", "--no-overwrites", "--no-playlist",
                "--retries", "10", "--fragment-retries", "10",
                "--concurrent-fragments", "4", "--embed-metadata",
                "--merge-output-format", "mp4", "--remux-video", "mp4",
                "-f", "bestvideo[height<=$MaxHeight][height>=$MinHeight]+bestaudio/best[height<=$MaxHeight][height>=$MinHeight]",
                "-o", (Join-Path $topicDir "高清源视频.%(ext)s"), $url
            ) | ForEach-Object { $arguments.Add($_) }
            Add-OptionalArgument $arguments "--ffmpeg-location" $FfmpegLocation
            Add-OptionalArgument $arguments "--cookies-from-browser" $CookiesFromBrowser
            Add-OptionalArgument $arguments "--proxy" $Proxy
            Invoke-YtDlp $arguments.ToArray()
        }

        $existingSubtitle = Get-ChildItem -LiteralPath $topicDir -File -Filter "*.srt" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if (-not $existingSubtitle) {
            if ([string]::IsNullOrWhiteSpace($subtitleLanguage)) {
                $subtitleLanguage = Get-SubtitleLanguage $url
            }
            if (-not [string]::IsNullOrWhiteSpace($subtitleLanguage)) {
                $arguments = [System.Collections.Generic.List[string]]::new()
                @(
                    "--skip-download", "--no-playlist", "--write-subs", "--write-auto-subs",
                    "--sub-langs", $subtitleLanguage, "--convert-subs", "srt",
                    "-o", (Join-Path $topicDir "字幕.%(ext)s"), $url
                ) | ForEach-Object { $arguments.Add($_) }
                Add-OptionalArgument $arguments "--ffmpeg-location" $FfmpegLocation
                Add-OptionalArgument $arguments "--cookies-from-browser" $CookiesFromBrowser
                Add-OptionalArgument $arguments "--proxy" $Proxy
                Invoke-YtDlp $arguments.ToArray()

                $generated = Get-ChildItem -LiteralPath $topicDir -File -Filter "字幕*.srt" -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 1
                if ($generated -and $generated.Name -ne "字幕.srt") {
                    Move-Item -LiteralPath $generated.FullName -Destination (Join-Path $topicDir "字幕.srt") -Force
                }
            }
        }
    } catch {
        $status = $_.Exception.Message
    }

    $videoCheck = Get-ChildItem -LiteralPath $topicDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.BaseName -eq "高清源视频" -and $_.Extension -in @(".mp4", ".mkv", ".webm") } |
        Select-Object -First 1
    $subtitleCheck = Get-ChildItem -LiteralPath $topicDir -File -Filter "*.srt" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ((-not $videoCheck -or -not $subtitleCheck) -and $status -eq "complete") {
        $status = "incomplete"
    }

    $statusRows.Add([pscustomobject]@{
        folder_name = $folderName
        url = $url
        video = [bool]$videoCheck
        subtitle = [bool]$subtitleCheck
        subtitle_language = $subtitleLanguage
        status = $status
    })
    $statusRows | Export-Csv -LiteralPath $logPath -Encoding UTF8 -NoTypeInformation
}

if ($PlanOnly) {
    Write-Output "Planned $($rows.Count) topic(s). No files downloaded."
} else {
    $complete = @($statusRows | Where-Object { $_.video -and $_.subtitle }).Count
    Write-Output "Completed $complete/$($statusRows.Count) topic(s). Status: $logPath"
}

