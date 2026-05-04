import 'dart:async';

import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import 'mqtt_service.dart';

/// Streams phone GPS and forwards it to MQTT app/follow_position at ~5 Hz.
class LocationService {
  StreamSubscription<Position>? _sub;
  bool _publishing = false;

  Future<bool> requestPermission() async {
    LocationPermission perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    return perm == LocationPermission.whileInUse ||
           perm == LocationPermission.always;
  }

  Future<LatLng?> getCurrentPosition() async {
    if (!await requestPermission()) return null;
    try {
      final pos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 5),
      );
      return LatLng(pos.latitude, pos.longitude);
    } catch (_) {
      return null;
    }
  }

  /// Start streaming phone GPS to MQTT at ~5 Hz.
  Future<void> startPublishing(MqttService mqtt) async {
    if (_publishing) return;
    if (!await requestPermission()) return;

    _publishing = true;
    const settings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 0,           // every update regardless of movement
    );

    _sub = Geolocator.getPositionStream(locationSettings: settings).listen(
      (pos) {
        if (_publishing) {
          mqtt.sendFollowPosition(pos.latitude, pos.longitude);
        }
      },
      onError: (_) {},
    );
  }

  void stopPublishing() {
    _publishing = false;
    _sub?.cancel();
    _sub = null;
  }

  void dispose() => stopPublishing();
}
