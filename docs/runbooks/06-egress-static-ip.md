# 06 — Give the service a static egress IP for reaching Prefect

**Audience:** any team member with `roles/compute.networkAdmin` and `roles/run.admin` on the project
**When:** standing up the project from nothing ([03](03-gcp-project-bootstrap.md)); rebuilding the
egress path after it was removed; moving the service to another project or region
**Duration:** 20–30 minutes on the Google side; the ETH-side firewall entry is a separate request
**Last verified:** 2026-07-31 — steps 1–12 executed as written (recorded on the Confluence page
*Statische Outbound-IP für lumina-command-api*); 2026-09-09 — step 8b and the end-to-end check
executed, sixty uncached calls through Apigee all `200`

The `/pipeline/*` endpoints read the Lumina Engine's Prefect server at `129.132.180.17:4200`, an
ETH-internal host. The ETH side opens that port for exactly one source address, so the service
needs an egress IP that never changes. Cloud Run's default egress uses a changing pool of Google
addresses; this runbook routes all egress through a dedicated VPC and a Cloud NAT gateway that
holds one reserved address.

```
Cloud Run ──Direct VPC Egress──▶ lumina-egress-vpc ──▶ Cloud NAT ──34.65.28.93──▶ ETH firewall ──▶ Prefect
           (all-traffic)          10.180.0.0/25         MANUAL_ONLY               port 4200
```

## Prerequisites

- `gcloud` authenticated, active configuration pointing at the project — `gcloud config get-value project`
- The Cloud Run service exists and is deployed ([01](01-deploy.md))
- No Shared VPC in play: `gcloud compute shared-vpc get-host-project "$PROJECT_ID"` returns nothing
- Someone on the Engine side who can have the ETH firewall entry made (step 13)

## Variables

```bash
export PROJECT_ID="ethbib-lumina"
export REGION="europe-west6"
export SERVICE="lumina-command-api"
export NETWORK="lumina-egress-vpc"
export SUBNET="lumina-command-api-egress"
export SUBNET_RANGE="10.180.0.0/25"
export ORIGIN_IP_NAME="lumina-command-api-egress-ip"
export ROUTER="lumina-egress-router"
export NAT="lumina-command-api-nat"
export PREFECT_HOST="129.132.180.17"      # lumina-box01.ethz.ch
```

The names are the ones in production. Keep them: [EGRESS-NAT.md](../EGRESS-NAT.md), runbook 03 and
the ETH firewall entry all refer to them.

## Steps

1. **Confirm the project.**
   ```bash
   gcloud config get-value project
   ```
   Expected: `ethbib-lumina`. The name of the active `gcloud` configuration may differ; what
   counts is `core/project`.

2. **Confirm the service has no VPC attachment yet.**
   ```bash
   gcloud run services describe "$SERVICE" --region "$REGION" \
     --format="yaml(metadata.name,status.url,spec.template.metadata.annotations)"
   ```
   Expected: no `run.googleapis.com/network-interfaces`, `vpc-access-egress` or
   `vpc-access-connector` annotation. If they are present, the path exists — go to Verification.

3. **Look at what networks exist.**
   ```bash
   gcloud compute networks list
   gcloud compute networks subnets list --filter="region:($REGION)"
   gcloud compute shared-vpc get-host-project "$PROJECT_ID"
   ```
   Expected on a fresh project: only `default`, no Shared VPC. The egress path gets its own custom
   VPC so that nothing else shares the NAT or the address.

4. **Create the VPC.**
   ```bash
   gcloud compute networks create "$NETWORK" --project "$PROJECT_ID" \
     --subnet-mode=custom --bgp-routing-mode=regional
   gcloud compute networks describe "$NETWORK" \
     --format="yaml(name,autoCreateSubnetworks,routingConfig.routingMode)"
   ```
   Expected: `autoCreateSubnetworks: false`, `routingMode: REGIONAL`. No inbound firewall rules
   are added; nothing needs to reach this network.

5. **Create the subnet.**
   ```bash
   gcloud compute networks subnets create "$SUBNET" --project "$PROJECT_ID" \
     --network "$NETWORK" --region "$REGION" --range "$SUBNET_RANGE"
   gcloud compute networks subnets describe "$SUBNET" --region "$REGION" \
     --format="yaml(name,ipCidrRange,stackType,privateIpGoogleAccess)"
   ```
   Expected: `ipCidrRange: 10.180.0.0/25`, `stackType: IPV4_ONLY`. A `/25` holds enough addresses
   for the service at its old 25-instance ceiling plus overlapping instances during a revision
   switch; with today's `--max-instances=3` it is generous.

6. **Reserve the static external address.**
   ```bash
   gcloud compute addresses create "$ORIGIN_IP_NAME" --project "$PROJECT_ID" \
     --region "$REGION" --network-tier=PREMIUM
   gcloud compute addresses describe "$ORIGIN_IP_NAME" --region "$REGION" \
     --format="yaml(name,address,addressType,status,networkTier)"
   ```
   Expected: `addressType: EXTERNAL`, `status: RESERVED`, and the address — in production
   `34.65.28.93`. **Write it down; it is what the ETH side will allow.** On a rebuild you get a
   different address, and step 13 has to be repeated with it.

7. **Create the Cloud Router.** It is the control plane for NAT; it holds no BGP sessions here.
   ```bash
   gcloud compute routers create "$ROUTER" --project "$PROJECT_ID" \
     --network "$NETWORK" --region "$REGION"
   ```

8. **Create the NAT gateway on the reserved address.**
   ```bash
   gcloud compute routers nats create "$NAT" --project "$PROJECT_ID" \
     --router "$ROUTER" --region "$REGION" \
     --nat-custom-subnet-ip-ranges "$SUBNET" \
     --nat-external-ip-pool "$ORIGIN_IP_NAME"
   ```
   `--nat-external-ip-pool` makes the allocation `MANUAL_ONLY`: the gateway uses the reserved
   address and nothing else. Without it Cloud NAT picks addresses automatically and the firewall
   entry is worthless.

   **8b. Switch to dynamic port allocation.** The default — 64 static ports per instance, each
   held 120 s after close — was exhausted by four page loads on 2026-09-09
   ([ADR 0009](../adr/0009-shared-keepalive-client-for-prefect.md)). Dynamic allocation is part of
   the path now, not an option:
   ```bash
   gcloud compute routers nats update "$NAT" --router "$ROUTER" --region "$REGION" \
     --enable-dynamic-port-allocation --min-ports-per-vm 64 --max-ports-per-vm 4096
   gcloud compute routers nats describe "$NAT" --router "$ROUTER" --region "$REGION" \
     --format="yaml(natIpAllocateOption,natIps,enableDynamicPortAllocation,enableEndpointIndependentMapping,minPortsPerVm,maxPortsPerVm)"
   ```
   Expected: `natIpAllocateOption: MANUAL_ONLY`, one entry under `natIps` naming
   `$ORIGIN_IP_NAME`, `enableDynamicPortAllocation: true`, `minPortsPerVm: 64`,
   `maxPortsPerVm: 4096`, `enableEndpointIndependentMapping: false`. Dynamic allocation requires
   endpoint-independent mapping off; if it is on, add `--no-enable-endpoint-independent-mapping`.

9. **Back up the Cloud Run configuration** before touching the service.
   ```bash
   BACKUP_FILE="$SERVICE-before-vpc-$(date +%Y%m%d-%H%M%S).yaml"
   gcloud run services describe "$SERVICE" --region "$REGION" --format=export > "$BACKUP_FILE"
   ls -l "$BACKUP_FILE"
   ```
   The 2026-07-31 backup is `lumina-command-api-before-vpc-20260731-124042.yaml`, kept locally
   by whoever ran it; it is not in this repository.

10. **Attach the service to the VPC with Direct VPC Egress, all traffic.**
    ```bash
    gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
      --network "$NETWORK" --subnet "$SUBNET" --vpc-egress=all-traffic
    ```
    This creates a new revision and routes traffic to it. `all-traffic` is required: Prefect is
    reached on a public address, and the `private-ranges-only` setting would send that request
    around the NAT, from a changing Google address.

    **`deploy.sh` does not carry these flags.** A later `gcloud run deploy` keeps the network
    settings of the existing service, so the attachment survives ordinary deploys — but a service
    created from scratch by `deploy.sh` has none, which is why this runbook exists.

11. **Verify the service uses the path.**
    ```bash
    gcloud run services describe "$SERVICE" --region "$REGION" --format=export \
      | grep -E "network-interfaces|vpc-access-egress|maxScale"
    ```
    Expected:
    ```
    autoscaling.knative.dev/maxScale: '3'
    run.googleapis.com/network-interfaces: '[{"network":"lumina-egress-vpc","subnetwork":"lumina-command-api-egress"}]'
    run.googleapis.com/vpc-access-egress: all-traffic
    ```
    `maxScale` comes from `--max-instances=3` in `deploy.sh`. It bounds what the service can open
    toward Prefect: one worker per instance, four keep-alive connections per worker.

12. **Confirm the address is in use.**
    ```bash
    gcloud compute addresses describe "$ORIGIN_IP_NAME" --region "$REGION" \
      --format="yaml(address,status,users)"
    ```
    Expected: `status: IN_USE`, and the router under `users`.

13. **Have the ETH side open the port for this address.** This is not a `gcloud` step. The Lumina
    Engine team registers the entry with ETH's ID; there is no ticket number for such entries. The
    rule they need:
    ```
    Direction:    inbound to the Prefect host
    Protocol:     TCP
    Source:       34.65.28.93/32        (the address from step 6)
    Destination:  129.132.180.17
    Port:         4200
    Action:       allow
    ```
    `/32` is a single address; if the form takes an address rather than a CIDR, enter it without
    the suffix. Until this is done, every `/pipeline/*` call from Cloud Run returns `502`.

## Verification

End to end, through Apigee, with a consumer key:

```bash
export CK="…"
for n in $(seq 1 20); do
  curl -s -o /dev/null -w '%{http_code} ' \
    "https://api.library.ethz.ch/lumina/v1/pipeline/sources?_=$n" \
    -H "x-api-key: $CK" -H "Cache-Control: no-cache"
done; echo
```

Expected: twenty `200`. `no-cache` bypasses Apigee's 60 s response cache so every call reaches
Cloud Run and, through the path, Prefect. A `502` on every call means the firewall entry (step 13)
is missing or names the wrong address; `502` after a few good calls means port allocation (step 8b)
is static — read the errno in the Cloud Run log, per [01](01-deploy.md), Troubleshooting.

## Rollback

**Detach the service from the VPC** — egress falls back to Google's changing addresses and
`/pipeline/*` stops working until reattached:

```bash
gcloud run services update "$SERVICE" --region "$REGION" --clear-network
```

**Return traffic to the pre-VPC revision** — only meaningful right after step 10:

```bash
gcloud run revisions list --service "$SERVICE" --region "$REGION" --limit 5
gcloud run services update-traffic "$SERVICE" --region "$REGION" --to-revisions "REVISION_NAME=100"
```

**Do not delete the reserved address**, even when rolling back. The ETH firewall entry names it,
and a new reservation yields a new address and a new round of step 13. If the path is rebuilt
later, the same address is reused as long as it still exists.

**Do not change `natIpAllocateOption` away from `MANUAL_ONLY`** for the same reason.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `/pipeline/*` returns `502` on every call, `Errno 111` in the log | Firewall entry missing, or it names a different address than `$ORIGIN_IP_NAME` holds | Compare step 6's address with what the Engine team registered; step 13 |
| `502` after a few good calls, then fine after two minutes | NAT ports exhausted — static allocation | Step 8b |
| `/pipeline/*` works locally but never from Cloud Run, no errno | Service not attached to the VPC, or `vpc-access-egress` is `private-ranges-only` | Step 10, then step 11 |
| Address `status: RESERVED` after step 8 | NAT was created without `--nat-external-ip-pool` | Recreate the NAT (step 8); `MANUAL_ONLY` cannot be switched on later without re-specifying the pool |
| `gcloud run services update` refuses `--network` | Old `gcloud`; Direct VPC Egress flags need a recent SDK | `gcloud components update` |
| `/commands/*` also slower after step 10 | `all-traffic` sends OpenAI and Pinecone through the NAT too | Expected; the latency cost is small and the path is shared by design |
