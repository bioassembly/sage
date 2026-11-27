# The client doctor supplies check_pass and check_warn.
check_sage_remote_mcps() {
  local config="$1" table="$2" registry="$3" name url
  [[ -f "$config" ]] || return 0
  while IFS=$'\t' read -r name url; do
    if curl -sf --max-time 4 -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
        -d '{"jsonrpc":"2.0","method":"ping","id":1}' -- "$url" >/dev/null; then
      check_pass "$name remote MCP endpoint responded"
    else
      check_warn "$name remote MCP endpoint did not answer the ping"
    fi
  done < <(jq -r --arg table "$table" --slurpfile defs "$registry" '
    .[$table] // {} | to_entries[] |
    select(.value.enabled != false and .value.disabled != true and .value.url != null
           and .value.url == $defs[0][.key].url) | [.key, .value.url] | @tsv
  ' "$config")
}
