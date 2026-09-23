[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Container,

    [string]$ReaderPassword = ("McpReader!" + [Guid]::NewGuid().ToString("N")),

    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$seedFile = Join-Path $PSScriptRoot "seed-demo.sql"
$remoteFile = "/tmp/seed-demo.sql"
# Windows PowerShell 5.1 drops bare double quotes in native arguments, so they are escaped as \".
$sqlcmd = '/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P \"$MSSQL_SA_PASSWORD\" -C -b'

if ($ReaderPassword -notmatch '^[A-Za-z0-9!._-]+$') {
    [Console]::Error.WriteLine("Reader password contains unsupported characters.")
    exit 2
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon is not ready. Start Docker Desktop and retry."
}
$running = docker inspect --format '{{.State.Running}}' $Container
if ($LASTEXITCODE -ne 0 -or $running -ne "true") {
    throw "Container '$Container' is not running."
}

if ($Reset) {
    $drop = "DROP DATABASE IF EXISTS shop_demo; DROP DATABASE IF EXISTS hr_demo; " +
        "DROP DATABASE IF EXISTS blog_demo; " +
        "IF SUSER_ID('mcp_reader') IS NOT NULL DROP LOGIN mcp_reader;"
    docker exec $Container sh -c ($sqlcmd + ' -Q \"' + $drop + '\"')
    if ($LASTEXITCODE -ne 0) {
        throw "Could not drop the demo databases."
    }
}

docker cp $seedFile "${Container}:$remoteFile"
if ($LASTEXITCODE -ne 0) {
    throw "Could not copy the seed script into '$Container'."
}
docker exec $Container sh -c ($sqlcmd + " -v MCP_READER_PASSWORD='$ReaderPassword' -i $remoteFile")
if ($LASTEXITCODE -ne 0) {
    throw "Seeding failed. Rerun with -Reset if the demo databases already exist."
}
docker exec -u 0 $Container rm -f $remoteFile | Out-Null

$portLine = docker port $Container 1433
$port = if ($portLine) { (($portLine | Select-Object -First 1).Trim() -split ":")[-1] } else { "<port>" }
Write-Host "Seeded shop_demo, hr_demo, blog_demo. Login: mcp_reader (read-only), host port: $port."
if ($PSBoundParameters.ContainsKey("ReaderPassword")) {
    Write-Host "Password: the value passed in -ReaderPassword."
}
else {
    Write-Host "Password: $ReaderPassword"
    Write-Host "Generated for this run; put it into the connection URL now, it is not stored."
}
