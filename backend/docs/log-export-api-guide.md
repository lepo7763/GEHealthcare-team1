# Axone Log Export — API Guide

This service exposes 8 HTTP GET endpoints for retrieving system logs. Call them with any HTTP client
(curl, Postman, your own code).

**Base URL / port:** `http://<host>:9200` (no path prefix — paths below are appended directly to the
host).

**Calling from within the Kubernetes cluster:** these endpoints are only reachable from inside the
cluster (there's no public ingress). If your application needs to call them, it needs to run as a pod
inside the same cluster — you'll likely need to deploy your app as its own pod/deployment so it can
reach the service over the cluster network, rather than calling it from your laptop or an external
machine.

## Endpoints

| # | Method | Path | Query shape | Response |
|---|--------|------|-------------|----------|
| 1 | GET | `/getLogsByDevice` | logs for one device, all events | JSON |
| 2 | GET | `/getSpecificDeviceLogsInCSV` | logs for one device, all events | CSV |
| 3 | GET | `/getLogsByDeviceAndEvent` | logs for one device, one event category | JSON |
| 4 | GET | `/getLogsByDeviceAndEventInCsv` | logs for one device, one event category | CSV |
| 5 | GET | `/getLogsByDate` | logs for all devices, all events | JSON |
| 6 | GET | `/getAllDeviceLogsInCSV` | logs for all devices, all events | CSV |
| 7 | GET | `/getLogsByDateAndEvent` | logs for all devices, one event category | JSON |
| 8 | GET | `/getLogsByDateAndEventInCsv` | logs for all devices, one event category | CSV |

### Parameters by query shape

**By device** (endpoints 1–4): require `deviceuuid`, `startTimestamp`, `endTimestamp`. Endpoints 3–4
also require `eventCategory`.
- Max time range: 7 days.

**By date** (endpoints 5–8): require `startTimestamp`, `endTimestamp`. Endpoints 7–8 also require
`eventCategory`.
- Max time range: 1 hour.
- The `HH` hour component of `startTimestamp` and `endTimestamp` must be the same value (e.g. both
  `09`), even though the minutes/seconds can differ.

**Common parameter formats:**
- `deviceuuid`: string UUID of the device/source.
- `startTimestamp` / `endTimestamp`: ISO-local date-time, e.g. `2024-01-15T09:00:00.000`. `endTimestamp`
  must be strictly after `startTimestamp`.
- `eventCategory`: an integer code, not a name. Known categories (per project docs): UserAction,
  Security, PerfData, Exception, Timing, General — but there's no in-code lookup table for which
  integer maps to which name, so confirm the mapping with the team before relying on a specific value.

## Example requests and responses

### 1. GET /getLogsByDevice

```
GET /getLogsByDevice?deviceuuid=d4e5f6a7-1234-5678-9abc-def012345678&startTimestamp=2024-01-15T00:00:00.000&endTimestamp=2024-01-15T06:00:00.000
```

```json
[
  {
    "dateStamp": "2024-01-15",
    "timeStamp": "2024-01-15T00:12:03.512Z",
    "sourceUUID": "d4e5f6a7-1234-5678-9abc-def012345678",
    "eventCategory": "General",
    "logLevel": "INFO",
    "hostName": "axone-node-02",
    "friendlyName": "Hub-01",
    "description": "Service started successfully",
    "processCounter": 1,
    "concentrationCounter": 1,
    "processID": "4521",
    "processName": "axone-log-export",
    "threadID": "14",
    "threadName": "main",
    "sourceFileName": "StartupService.java",
    "sourceFileLineNum": 88,
    "timeZoneOffSetInMin": -300,
    "hashValue": "a1b2c3d4e5f6..."
  }
]
```

### 2. GET /getSpecificDeviceLogsInCSV

```
GET /getSpecificDeviceLogsInCSV?deviceuuid=d4e5f6a7-1234-5678-9abc-def012345678&startTimestamp=2024-01-15T00:00:00.000&endTimestamp=2024-01-15T06:00:00.000
```

```csv
timeStampAndOffset,processCounter,concentrationCounter,logLevel,hostName,sourceUUID,friendlyName,processInfo,sourceInfo,eventCategory,description
2024-01-15T00:12:03.512-05:00,1,1,INFO,axone-node-02,d4e5f6a7-1234-5678-9abc-def012345678,Hub-01,axone-log-export:4521:main,StartupService.java:88,General,Service started successfully
```

### 3. GET /getLogsByDeviceAndEvent

```
GET /getLogsByDeviceAndEvent?deviceuuid=d4e5f6a7-1234-5678-9abc-def012345678&eventCategory=1&startTimestamp=2024-01-15T00:00:00.000&endTimestamp=2024-01-15T06:00:00.000
```

```json
[
  {
    "dateStamp": "2024-01-15",
    "timeStamp": "2024-01-15T02:47:19.221Z",
    "sourceUUID": "d4e5f6a7-1234-5678-9abc-def012345678",
    "eventCategory": "Security",
    "logLevel": "WARN",
    "hostName": "axone-node-02",
    "friendlyName": "Hub-01",
    "description": "Failed login attempt for user 'operator1'",
    "processCounter": 7,
    "concentrationCounter": 1,
    "processID": "4521",
    "processName": "axone-log-export",
    "threadID": "22",
    "threadName": "auth-handler",
    "sourceFileName": "AuthService.java",
    "sourceFileLineNum": 142,
    "timeZoneOffSetInMin": -300,
    "hashValue": "b2c3d4e5f6a7..."
  }
]
```

### 4. GET /getLogsByDeviceAndEventInCsv

```
GET /getLogsByDeviceAndEventInCsv?deviceuuid=d4e5f6a7-1234-5678-9abc-def012345678&eventCategory=1&startTimestamp=2024-01-15T00:00:00.000&endTimestamp=2024-01-15T06:00:00.000
```

```csv
timeStampAndOffset,processCounter,concentrationCounter,logLevel,hostName,sourceUUID,friendlyName,processInfo,sourceInfo,eventCategory,description
2024-01-15T02:47:19.221-05:00,7,1,WARN,axone-node-02,d4e5f6a7-1234-5678-9abc-def012345678,Hub-01,axone-log-export:4521:auth-handler,AuthService.java:142,Security,Failed login attempt for user 'operator1'
```

### 5. GET /getLogsByDate

```
GET /getLogsByDate?startTimestamp=2024-01-15T09:00:00.000&endTimestamp=2024-01-15T09:45:00.000
```
(Note: the hour, `09`, matches on both timestamps, and the range is under 1 hour.)

```json
[
  {
    "dateStamp": "2024-01-15",
    "hour": "09",
    "timeStamp": "2024-01-15T09:03:11.004Z",
    "sourceUUID": "a1b2c3d4-aaaa-bbbb-cccc-123456789abc",
    "eventCategory": "General",
    "logLevel": "INFO",
    "hostName": "axone-node-01",
    "friendlyName": "MRI-Scanner-01",
    "description": "Heartbeat received",
    "processCounter": 3,
    "concentrationCounter": 1,
    "processID": "3310",
    "processName": "axone-log-export",
    "threadID": "9",
    "threadName": "heartbeat",
    "sourceFileName": "HeartbeatService.java",
    "sourceFileLineNum": 54,
    "timeZoneOffSetInMin": -300,
    "hashValue": "c3d4e5f6a7b8..."
  }
]
```

### 6. GET /getAllDeviceLogsInCSV

```
GET /getAllDeviceLogsInCSV?startTimestamp=2024-01-15T09:00:00.000&endTimestamp=2024-01-15T09:45:00.000
```

```csv
timeStampAndOffset,processCounter,concentrationCounter,logLevel,hostName,sourceUUID,friendlyName,processInfo,sourceInfo,eventCategory,description
2024-01-15T09:03:11.004-05:00,3,1,INFO,axone-node-01,a1b2c3d4-aaaa-bbbb-cccc-123456789abc,MRI-Scanner-01,axone-log-export:3310:heartbeat,HeartbeatService.java:54,General,Heartbeat received
```

### 7. GET /getLogsByDateAndEvent

```
GET /getLogsByDateAndEvent?eventCategory=3&startTimestamp=2024-01-15T09:00:00.000&endTimestamp=2024-01-15T09:45:00.000
```

```json
[
  {
    "dateStamp": "2024-01-15",
    "hour": "09",
    "timeStamp": "2024-01-15T09:21:47.330Z",
    "sourceUUID": "e5f6a7b8-dddd-eeee-ffff-987654321abc",
    "eventCategory": "Exception",
    "logLevel": "ERROR",
    "hostName": "axone-node-03",
    "friendlyName": "Ultrasound-07",
    "description": "NullPointerException while parsing calibration data",
    "processCounter": 15,
    "concentrationCounter": 1,
    "processID": "5102",
    "processName": "axone-log-export",
    "threadID": "4",
    "threadName": "calibration-worker",
    "sourceFileName": "CalibrationParser.java",
    "sourceFileLineNum": 211,
    "timeZoneOffSetInMin": -300,
    "hashValue": "d4e5f6a7b8c9..."
  }
]
```

### 8. GET /getLogsByDateAndEventInCsv

```
GET /getLogsByDateAndEventInCsv?eventCategory=3&startTimestamp=2024-01-15T09:00:00.000&endTimestamp=2024-01-15T09:45:00.000
```

```csv
timeStampAndOffset,processCounter,concentrationCounter,logLevel,hostName,sourceUUID,friendlyName,processInfo,sourceInfo,eventCategory,description
2024-01-15T09:21:47.330-05:00,15,1,ERROR,axone-node-03,e5f6a7b8-dddd-eeee-ffff-987654321abc,Ultrasound-07,axone-log-export:5102:calibration-worker,CalibrationParser.java:211,Exception,NullPointerException while parsing calibration data
```

## Response field reference

**JSON fields** (both JSON response shapes share these):

| Field | Type | Notes |
|---|---|---|
| `dateStamp` | string | date of the log entry |
| `hour` | string | only present on `/getLogsByDate*` responses |
| `timeStamp` | string (ISO instant) | exact time of the log entry |
| `sourceUUID` | string | device/source UUID |
| `eventCategory` | string | category name |
| `logLevel` | string | e.g. INFO, WARN, ERROR |
| `hostName` | string | host that generated the log |
| `friendlyName` | string | human-readable device name |
| `description` | string | log message |
| `processCounter` | number | |
| `concentrationCounter` | number | |
| `processID` | string | |
| `processName` | string | |
| `threadID` | string | |
| `threadName` | string | |
| `sourceFileName` | string | |
| `sourceFileLineNum` | number | |
| `timeZoneOffSetInMin` | number | |
| `hashValue` | string | |

**CSV header** (all 4 CSV endpoints use this column order):

```
timeStampAndOffset,processCounter,concentrationCounter,logLevel,hostName,sourceUUID,friendlyName,processInfo,sourceInfo,eventCategory,description
```

## Errors

- `400 Bad Request` — bad or missing parameters, invalid timestamp format, time range too large,
  `endTimestamp` not after `startTimestamp`, mismatched hour on by-date queries, or an unrecognized
  `eventCategory`. Body is a plain JSON array of error message strings, e.g.
  `["Invalid timestamp Format"]`.
- `500 Internal Server Error` — backend/database issue on the server side.

## Reaching the service from your own pod

There's no public endpoint for these APIs — only pods running inside the same Kubernetes cluster can
reach them. If you're writing an application that calls these endpoints, deploy it as a pod in the
cluster and call the service's in-cluster DNS name on port 9200, for example:

```
curl "http://axone-log-export-tcp:9200/getLogsByDate?startTimestamp=2024-01-15T09:00:00.000&endTimestamp=2024-01-15T09:45:00.000"
```

(If your pod runs in a different namespace, use
`axone-log-export-tcp.<namespace>.svc.cluster.local:9200` instead.)
