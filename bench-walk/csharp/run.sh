#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! command -v dotnet >/dev/null 2>&1; then
    echo "C# benchmark blocked: dotnet SDK is not installed; no measurements produced" >&2
    exit 127
fi
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
export DOTNET_PROCESSOR_COUNT=1
work=$(mktemp -d "${TMPDIR:-/tmp}/omitnix-csharp.XXXXXX")
trap 'rm -rf "$work"' EXIT HUP INT TERM
export DOTNET_CLI_HOME="$work/home"
export NUGET_PACKAGES="$work/packages"
dotnet build "$here/Benchmark.csproj" -c Release --nologo -m:1 --disable-build-servers \
    --configfile "$here/NuGet.Config" \
    -p:BaseIntermediateOutputPath="$work/obj/" -p:MSBuildProjectExtensionsPath="$work/obj/" \
    -p:OutputPath="$work/out/" >&2
dotnet "$work/out/Benchmark.dll" "$@"
