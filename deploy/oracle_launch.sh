#!/usr/bin/env bash
# Auto-retry launcher for the ALTER EGO Oracle box. Grinds against the
# A1.Flex "Out of capacity" lottery in Milan until a slot opens, then waits
# for RUNNING and prints the public IP. Paced at 90s to avoid rate limits.
set -u
export OCI_CLI_PROFILE=alterego-api SUPPRESS_LABEL_WARNING=True

TENANCY="ocid1.tenancy.oc1..aaaaaaaainhqrw6k2da3cat4ourxxrxft35fkaduozqvsgl5oq4nsfruwseq"
AD="VkhA:EU-MILAN-1-AD-1"
SUBNET="ocid1.subnet.oc1.eu-milan-1.aaaaaaaavpjf73saajfbbnvtpls26xgpehascnxijflnejcbchxsbpzunbrq"
IMAGE="ocid1.image.oc1.eu-milan-1.aaaaaaaa4nrshfscpbilbpx4upw4osenk45ncyriilddtmbusfrruz6efbcq"
SSH_PUB="$HOME/.ssh/alterego_oracle.pub"
LOG="$HOME/alteregoscraper/logs/oracle_grinder.log"
mkdir -p "$(dirname "$LOG")"
echo "=== grinder started $(date) — target: A1.Flex 1 OCPU / 6 GB ===" | tee -a "$LOG"

attempt=0
while true; do
  attempt=$((attempt+1))
  ts=$(date '+%H:%M:%S')
  out=$(oci compute instance launch \
    --availability-domain "$AD" \
    --compartment-id "$TENANCY" \
    --shape "VM.Standard.A1.Flex" \
    --shape-config '{"ocpus":1,"memoryInGBs":6}' \
    --image-id "$IMAGE" \
    --subnet-id "$SUBNET" \
    --assign-public-ip true \
    --display-name "alterego" \
    --ssh-authorized-keys-file "$SSH_PUB" 2>&1)
  if [ $? -eq 0 ]; then
    iid=$(echo "$out" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])" 2>/dev/null)
    echo "[$ts] attempt $attempt: LAUNCHED -> $iid" | tee -a "$LOG"
    echo "[$ts] waiting for RUNNING..." | tee -a "$LOG"
    oci compute instance get --instance-id "$iid" --wait-for-state RUNNING >/dev/null 2>&1
    ip=$(oci compute instance list-vnics --instance-id "$iid" --query 'data[0]."public-ip"' --raw-output 2>/dev/null)
    echo "[$ts] RUNNING -- PUBLIC_IP=$ip" | tee -a "$LOG"
    break
  fi
  # API key never expires, so every failure (capacity, rate-limit, timeout,
  # transient auth blip) is just retried — nothing is fatal except a real launch.
  flat=$(echo "$out" | tr '\n' ' ')
  msg=$(echo "$out" | grep -oE '"message"[: ]*"[^"]*"' | head -1 | sed -E 's/"message"[: ]*"//; s/"$//')
  [ -z "$msg" ] && msg=$(echo "$flat" | grep -ioE 'out of capacity|too many requests|timed out|limitexceeded' | head -1)
  echo "[$ts] attempt $attempt: retry -- ${msg:-unknown}" | tee -a "$LOG"
  sleep 90
done
