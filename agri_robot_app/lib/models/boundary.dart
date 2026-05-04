import 'dart:convert';
import 'package:latlong2/latlong.dart';

class BoundaryModel {
  final List<LatLng> points;

  const BoundaryModel({required this.points});

  bool get isValid => points.length >= 3;

  BoundaryModel addPoint(LatLng pt) =>
      BoundaryModel(points: [...points, pt]);

  BoundaryModel removePoint(int index) {
    final updated = List<LatLng>.from(points)..removeAt(index);
    return BoundaryModel(points: updated);
  }

  BoundaryModel movePoint(int index, LatLng newPos) {
    final updated = List<LatLng>.from(points)..[index] = newPos;
    return BoundaryModel(points: updated);
  }

  BoundaryModel clear() => const BoundaryModel(points: []);

  /// Serialise to MQTT app/boundary payload: [{lat, lon}, ...]
  String toMqttJson() {
    final list = points.map((p) => {'lat': p.latitude, 'lon': p.longitude}).toList();
    return jsonEncode(list);
  }

  static BoundaryModel fromMqttJson(String json) {
    final list = jsonDecode(json) as List;
    final pts = list
        .map((p) => LatLng(
              (p['lat'] as num).toDouble(),
              (p['lon'] as num).toDouble(),
            ))
        .toList();
    return BoundaryModel(points: pts);
  }
}
