import 'package:flutter/foundation.dart';
import 'package:latlong2/latlong.dart';

enum RobotMode { manual, auto, follow, estop }

RobotMode modeFromString(String s) {
  switch (s.toUpperCase()) {
    case 'AUTO':   return RobotMode.auto;
    case 'FOLLOW': return RobotMode.follow;
    case 'ESTOP':  return RobotMode.estop;
    default:       return RobotMode.manual;
  }
}

String modeToString(RobotMode m) {
  switch (m) {
    case RobotMode.auto:   return 'AUTO';
    case RobotMode.follow: return 'FOLLOW';
    case RobotMode.estop:  return 'ESTOP';
    case RobotMode.manual: return 'MANUAL';
  }
}

class RobotState extends ChangeNotifier {
  // Position
  LatLng position = const LatLng(10.762622, 106.660172); // fallback: HCM City
  double headingDeg = 0.0;

  // Status
  RobotMode mode = RobotMode.manual;
  bool gpsFixed = false;
  bool stuck    = false;
  bool mqttConnected = false;

  // Navigation
  bool navActive     = false;
  int  navWaypointIdx = 0;
  int  navTotal       = 0;
  double navDistToNext = 0.0;

  // Boundary
  bool boundaryWarning   = false;
  bool boundaryViolation = false;
  double distToEdge      = 0.0;

  // Stuck detection
  bool   stuckConfirmed = false;
  double stuckMismatchS = 0.0;

  // Follow mode
  bool   followActive    = false;
  double followDistM     = 0.0;
  double followHeadingErr = 0.0;

  // Coverage path (for map overlay)
  List<LatLng> coveragePath = [];

  // Boundary polygon (for map overlay)
  List<LatLng> boundaryPolygon = [];

  void updateFromPosition(Map<String, dynamic> msg) {
    final lat = (msg['lat'] as num?)?.toDouble();
    final lon = (msg['lon'] as num?)?.toDouble();
    if (lat != null && lon != null) {
      position = LatLng(lat, lon);
    }
    headingDeg = (msg['heading_deg'] as num?)?.toDouble() ?? headingDeg;
    final modeStr = msg['mode'] as String?;
    if (modeStr != null) mode = modeFromString(modeStr);
    notifyListeners();
  }

  void updateFromStatus(Map<String, dynamic> msg) {
    final modeStr = msg['mode'] as String?;
    if (modeStr != null) mode = modeFromString(modeStr);
    gpsFixed = msg['gps_fix'] as bool? ?? gpsFixed;
    mqttConnected = msg['mqtt_ok'] as bool? ?? mqttConnected;

    final bnd = msg['boundary'] as Map?;
    if (bnd != null) {
      boundaryWarning   = bnd['warning']   as bool? ?? false;
      boundaryViolation = bnd['violation'] as bool? ?? false;
      distToEdge        = (bnd['dist_to_edge_m'] as num?)?.toDouble() ?? 0.0;
    }

    final nav = msg['navigation'] as Map?;
    if (nav != null) {
      navActive       = nav['active']        as bool? ?? false;
      navWaypointIdx  = nav['waypoint_idx']  as int?  ?? 0;
      navTotal        = nav['total']         as int?  ?? 0;
      navDistToNext   = (nav['dist_to_next'] as num?)?.toDouble() ?? 0.0;
    }

    final stk = msg['stuck'] as Map?;
    if (stk != null) {
      stuckConfirmed = stk['stuck']      as bool?  ?? false;
      stuckMismatchS = (stk['mismatch_s'] as num?)?.toDouble() ?? 0.0;
    }

    final flw = msg['follow'] as Map?;
    if (flw != null) {
      followActive     = flw['active']          as bool?  ?? false;
      followDistM      = (flw['dist_to_target'] as num?)?.toDouble() ?? 0.0;
      followHeadingErr = (flw['heading_err_deg'] as num?)?.toDouble() ?? 0.0;
    }

    notifyListeners();
  }

  void updateCoveragePath(List<dynamic> points) {
    coveragePath = points
        .map((p) => LatLng(
              (p['lat'] as num).toDouble(),
              (p['lon'] as num).toDouble(),
            ))
        .toList();
    notifyListeners();
  }

  void updateBoundaryPolygon(List<dynamic> points) {
    boundaryPolygon = points
        .map((p) => LatLng(
              (p['lat'] as num).toDouble(),
              (p['lon'] as num).toDouble(),
            ))
        .toList();
    notifyListeners();
  }

  void setMqttConnected(bool v) {
    mqttConnected = v;
    notifyListeners();
  }

  void setMode(RobotMode m) {
    mode = m;
    notifyListeners();
  }
}
