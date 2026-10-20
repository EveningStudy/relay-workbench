$ErrorActionPreference='Stop'
$relayMedia=Join-Path $PSScriptRoot '../docs/media'
New-Item -ItemType Directory -Force $relayMedia | Out-Null
$relaySpeaker=New-Object -ComObject SAPI.SpVoice
$relayVoice=$relaySpeaker.GetVoices() | Where-Object { $_.GetDescription() -like '*Hazel*' } | Select-Object -First 1
if (-not $relayVoice) { throw 'English synthetic voice missing' }
$relaySpeaker.Voice=$relayVoice
$relayStream=New-Object -ComObject SAPI.SpFileStream
$relayStream.Open("$relayMedia\voice_input.wav",3,$false)
$relaySpeaker.AudioOutputStream=$relayStream
$relayText='Relay Workbench processes voice in small audio blocks. The robot character runs locally on the CPU. This example uses synthetic speech.'
$relaySpeaker.Rate=0
$relaySpeaker.Speak($relayText) | Out-Null
$relayStream.Close()
$relayText | Set-Content -Encoding utf8 "$relayMedia\narration.txt"
