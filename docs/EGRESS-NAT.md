# Lumina Command API — Egress nach Prefect: Cloud NAT und Port-Zuteilung

> **Charakter dieses Dokuments:** abgeleitete Zusammenfassung für die interne Confluence-Dokumentation.
> Keine eigene Autorität — massgeblich sind
> [ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md)
> und [Runbook 03, Schritt 8](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/03-gcp-project-bootstrap.md#steps).
> Übergeordnete Dokumentation:
> [System Overview](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md).
>
> **Stand:** 2026-09-09

## Übersicht

| Eigenschaft | Wert |
|-------------|------|
| **Google-Projekt** | `ethbib-lumina` |
| **Region** | `europe-west6` (Zürich) |
| **Cloud Run Service** | `lumina-command-api`, Direct VPC Egress, `all-traffic` |
| **VPC** | `lumina-egress-vpc` |
| **Cloud Router** | `lumina-egress-router` |
| **Cloud NAT** | `lumina-command-api-nat` |
| **Statische Egress-IP** | `34.65.28.93` (`lumina-command-api-egress-ip`) |
| **Ziel** | Prefect-Server der Lumina Engine, `lumina-box01.ethz.ch:4200` (`129.132.180.17`), ETH-intern |
| **Port-Zuteilung** | **dynamisch**, 64 bis 4096 Ports pro Instanz — seit 2026-09-09 |
| **TIME_WAIT** | 120 s (Standard, unverändert) |
| **Endpoint-Independent Mapping** | aus |

## Wozu dieser Weg existiert

Die `/pipeline/*`-Endpoints der Command API lesen den Zustand der Lumina Engine aus deren
Prefect-Server. Der steht im ETH-Netz. Cloud Run erreicht ihn über Direct VPC Egress in eine
eigene VPC, von dort über Cloud NAT mit einer statischen IP ins Internet und durch den ETH-Perimeter.
Die statische IP ist der Grund für das Konstrukt: sie lässt sich auf der ETH-Seite allow-listen,
die dynamischen Egress-IPs von Cloud Run nicht.

Nur `/pipeline/*` benutzt diesen Weg. OpenAI und Pinecone werden ebenfalls über die NAT erreicht,
sind aber öffentlich und nicht auf die IP angewiesen.

**Auf der ETH-Seite ist der Weg formal erlaubt.** Über die ID wurde Port 4200 auf `lumina-box01`
dediziert für die Egress-IP `34.65.28.93` geöffnet. Die statische IP ist die Voraussetzung dieser
Regel — mit den wechselnden Egress-IPs von Cloud Run liesse sie sich nicht formulieren.

**Auf der Google-Seite ist die Erstellung nicht als Prozedur festgehalten.** VPC, Router, NAT und
die Reservierung der IP wurden ausserhalb der Runbooks angelegt; diese Seite beschreibt, was
existiert, nicht die Befehlsfolge, mit der man es neu anlegen würde. Dokumentiert und verifiziert
ist die eine Einstellung, die Probleme gemacht hat — die Port-Zuteilung.

## Was am 2026-09-09 passiert ist

**Symptom.** `GET /pipeline/sources` und `GET /pipeline/runs` antworteten aus Cloud Run
mehrheitlich mit `502` — `Prefect API unreachable: All connection attempts failed`. Vom Laptop im
ETH-Netz lief derselbe Code fehlerfrei. Die Ablehnungen kamen sofort, in 80 bis 100 Millisekunden,
also keine Timeouts. Nach etwa zweieinhalb Minuten Ruhe gelangen die ersten vier Requests, dann
wurde wieder alles abgelehnt.

**Messung.** Der damalige Code öffnete für jeden Request einen neuen HTTP-Client und feuerte ein
Dutzend Prefect-Abfragen parallel:

| Aufruf | Neue TCP-Verbindungen | Zeitfenster |
|---|---:|---:|
| `GET /pipeline/sources` | 13 | 31 ms |
| Eine Studio-Seite (`sources` + `runs`) | 15 | 47 ms |

**Ursache.** Cloud NAT teilt jeder Instanz standardmässig **64 Ports statisch** zu und hält jeden
nach dem Schliessen **120 Sekunden** in TIME_WAIT. Fünfzehn Verbindungen pro Seitenaufruf ergeben
nach vier Aufrufen 60 belegte Ports — das Budget ist erschöpft, jede weitere Verbindung scheitert,
und nach zwei Minuten ist es wieder frei. Die Beobachtung «vier gut, dann alles abgelehnt, nach
150 Sekunden wieder gut» passt auf diese Rechnung genau.

Ob die sofortige Ablehnung von der NAT oder von einer Session-Rate-Limitierung am ETH-Perimeter
kam, war aus den Logs nicht zu entscheiden — beide reagieren auf denselben Burst. Der Code loggt
seither den errno der Wurzelursache: `111` heisst Firewall, `99` heisst NAT-Ports.

## Was geändert wurde — zwei Hälften

**Code** ([ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md)). Ein HTTP-Client pro Worker-Prozess statt pro Request,
mit vier Keep-Alive-Verbindungen. Der Fan-out bleibt gleich, läuft aber über vier wiederverwendete
Verbindungen statt über fünfzehn frische.

| Aufruf | vorher | nachher |
|---|---:|---:|
| `GET /pipeline/sources` | 13 | 4 |
| Studio-Seite bei warmem Pool | 15 | 0 |

**Infrastruktur** ([Runbook 03, Schritt 8](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/03-gcp-project-bootstrap.md#steps)). Cloud NAT auf dynamische
Port-Zuteilung umgestellt, 64 bis 4096 Ports pro Instanz. Die Grenze, an die der Code stiess, ist
damit weit nach oben verschoben. Wirksam sofort für neue Verbindungen, ohne Deploy.

| Einstellung | vorher | nachher |
|---|---|---|
| `enableDynamicPortAllocation` | nicht gesetzt (statisch) | `true` |
| `minPortsPerVm` | 64 (Standard) | 64 |
| `maxPortsPerVm` | — | 4096 |
| `tcpTimeWaitTimeoutSec` | 120 (Standard) | 120, unverändert |

Dazu begrenzt `deploy.sh` den Service neu auf **drei Instanzen**. Ein Worker pro Instanz, vier
Verbindungen pro Worker — das Maximum gegen Prefect ist damit zwölf, und es ist ausgesprochen statt
implizit.

**Nachweis.** Sechzig ungecachte `/sources`-Aufrufe in Folge über Apigee, sechzigmal `200`. Vor
beiden Änderungen war nach vier Schluss.

## Prüfen

Der Ist-Zustand der NAT, lesend:

```bash
gcloud compute routers nats describe lumina-command-api-nat \
  --router lumina-egress-router --region europe-west6 \
  --format="yaml(enableDynamicPortAllocation,enableEndpointIndependentMapping,minPortsPerVm,maxPortsPerVm)"
```

Erwartet: `enableDynamicPortAllocation: true`, `minPortsPerVm: 64`, `maxPortsPerVm: 4096`,
`enableEndpointIndependentMapping: false`.

Die Umstellung selbst und die Belastungsprobe stehen in
[Runbook 03, Schritt 8](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/03-gcp-project-bootstrap.md#steps);
das Fehlerbild und seine Deutung in der Troubleshooting-Tabelle von
[Runbook 01](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md#troubleshooting).

## Rückgängig

Ein Befehl, ohne Deploy:

```bash
gcloud compute routers nats update lumina-command-api-nat \
  --router lumina-egress-router --region europe-west6 \
  --no-enable-dynamic-port-allocation
```

Danach gilt wieder statische Zuteilung mit 64 Ports. Mit dem heutigen Code reicht das für rund
sechzehn kalte Seitenaufrufe pro zwei Minuten — genug für Studio hinter Apigees Cache, zu wenig für
ein Skript mit `Cache-Control: no-cache` in einer Schleife.

## Bekannte Einschränkungen

| Thema | Sachverhalt |
|-------|-------------|
| **Der Weg ist nicht dokumentiert angelegt** | VPC, Router, NAT und die Reservierung der IP wurden ausserhalb der Runbooks erstellt. Wer das Projekt neu aufsetzen muss, findet dafür keine Prozedur — Runbook 03 sagt das ausdrücklich. |
| **Die Firewall-Regel hängt an der IP** | Die ID-Regel erlaubt genau `34.65.28.93 → 129.132.180.17:4200`. Wird die Egress-IP ersetzt, die NAT neu angelegt oder der Prefect-Host umgezogen, muss die Regel nachgezogen werden — sonst `502` mit errno `111` im Log. Das ist bei diesem Fehlerbild die erste Frage. |
| **Für die ID-Regel gibt es keine Referenznummer** | Solche Einträge haben an der ETH keine Ticketnummer. Die Regel wurde vom Engine-Team bei den ID eintragen lassen. Wer sie ändern lassen muss, wendet sich mit IP und Host an die ID und zieht das Engine-Team hinzu. |
| **Die Grenze ist verschoben, nicht aufgehoben** | Dynamische Zuteilung endet bei 4096 Ports pro Instanz. Mit 120 s TIME_WAIT und vier Verbindungen pro kaltem Aufruf ist das für jede realistische Last irrelevant — aber nicht unendlich. |
| **Keep-Alive hält nur 5 Sekunden** | Uvicorn auf der Prefect-Seite schliesst Leerlaufverbindungen nach 5 s. Aufrufe, die weiter auseinanderliegen, öffnen wieder bis zu vier neue Verbindungen — was das Budget mit dynamischer Zuteilung problemlos trägt. |

## Verwandte Dokumentation

| Thema | Ort |
|-------|-----|
| Entscheid für den geteilten Client, mit Messwerten | [ADR 0009](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0009-shared-keepalive-client-for-prefect.md) |
| Warum Prefect überhaupt aus Cloud Run gelesen wird | [ADR 0007](https://github.com/eth-library/lumina-command-api/blob/main/docs/adr/0007-prefect-read-only-proxy.md) |
| NAT prüfen und umstellen | [Runbook 03, Schritt 8](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/03-gcp-project-bootstrap.md#steps) |
| Fehlerbild und Deutung des errno | [Runbook 01, Troubleshooting](https://github.com/eth-library/lumina-command-api/blob/main/docs/runbooks/01-deploy.md#troubleshooting) |
| Die betroffenen Endpoints | [Datenquellen](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-sources.md), [Pipeline-Läufe](https://github.com/eth-library/lumina-command-api/blob/main/docs/endpoints/pipeline-runs.md) |
| Gesamtsystem | [SYSTEMOVERVIEW.md](https://github.com/eth-library/lumina-command-api/blob/main/docs/SYSTEMOVERVIEW.md) |
