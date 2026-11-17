param([string]$Src, [string]$OutDir)
# Render with real PowerPoint: slide PNGs plus a PDF.
$p = New-Object -ComObject PowerPoint.Application
$d = $p.Presentations.Open($Src, -1, 0, 0)
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$i = 1
foreach ($s in $d.Slides) {
  $s.Export((Join-Path $OutDir ("s{0:d2}.png" -f $i)), "PNG", 1600, 900)
  $i++
}
$d.SaveAs((Join-Path $OutDir "deck.pdf"), 32)
$d.Close()
$p.Quit()
Write-Output "rendered $($i-1)"
