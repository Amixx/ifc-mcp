#!/bin/sh
set -u
if [ "$1" = "--verbose" ]; then
  shift
  name="$1"
  shift
  printf '== %s ==\n' "$name"
  exec "$@"
fi
name="$1"
shift
out="$(mktemp "${TMPDIR:-/tmp}/quiet_step.XXXXXX")"
start="$(date +%s)"
if "$@" >"$out" 2>&1; then
  elapsed="$(($(date +%s) - start))"
  summary="$(tail -n 1 "$out")"
  if [ -n "$summary" ]; then
    printf 'ok  %-14s %3ss  %s\n' "$name" "$elapsed" "$summary"
  else
    printf 'ok  %-14s %3ss\n' "$name" "$elapsed"
  fi
  rm -f "$out"
else
  status=$?
  printf 'FAIL %s (exit %s):\n' "$name" "$status"
  grep -vE '^[.sxXFEP]+( +\[ *[0-9]+%\])?$' "$out"
  rm -f "$out"
  exit "$status"
fi
