import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../models/boundary.dart';
import '../models/robot_state.dart';
import '../services/mqtt_service.dart';
import '../widgets/emergency_stop_btn.dart';
import '../widgets/mode_selector.dart';
import 'settings_screen.dart';

class MapScreen extends StatefulWidget {
  const MapScreen({super.key});

  @override
  State<MapScreen> createState() => _MapScreenState();
}

class _MapScreenState extends State<MapScreen> {
  final MapController _mapController = MapController();
  bool _followRobot = true;
  bool _editingBoundary = false;
  BoundaryModel _boundary = const BoundaryModel(points: []);

  @override
  Widget build(BuildContext context) {
    final robotState = context.watch<RobotState>();
    final mqtt       = context.read<MqttService>();

    // Auto-follow: keep robot centred on map
    if (_followRobot) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _mapController.move(robotState.position, _mapController.camera.zoom);
      });
    }

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            _MqttIndicator(connected: robotState.mqttConnected),
            const SizedBox(width: 8),
            const Text('Agri Robot'),
            const Spacer(),
            _ModeBadge(mode: robotState.mode),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
      body: Stack(
        children: [
          // ── Map ──────────────────────────────────────────────────────────
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: robotState.position,
              initialZoom: 18.0,
              onTap: _editingBoundary
                  ? (_, latlng) => _addBoundaryPoint(latlng, mqtt)
                  : null,
              onPositionChanged: (_, hasGesture) {
                if (hasGesture) setState(() => _followRobot = false);
              },
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.agri_robot.app',
              ),

              // Coverage path overlay
              if (robotState.coveragePath.isNotEmpty)
                PolylineLayer(polylines: [
                  Polyline(
                    points: robotState.coveragePath,
                    strokeWidth: 2.0,
                    color: Colors.blue.withAlpha(153),
                  ),
                ]),

              // Boundary polygon overlay
              if (robotState.boundaryPolygon.length >= 3)
                PolygonLayer(polygons: [
                  Polygon(
                    points: robotState.boundaryPolygon,
                    color: Colors.green.withAlpha(40),
                    borderColor: Colors.green,
                    borderStrokeWidth: 2.0,
                  ),
                ]),

              // Editing boundary points
              if (_editingBoundary && _boundary.points.isNotEmpty)
                PolygonLayer(polygons: [
                  if (_boundary.points.length >= 3)
                    Polygon(
                      points: _boundary.points,
                      color: Colors.orange.withAlpha(50),
                      borderColor: Colors.orange,
                      borderStrokeWidth: 2.0,
                    ),
                ]),
              if (_editingBoundary)
                MarkerLayer(
                  markers: _boundary.points.asMap().entries.map((e) {
                    return Marker(
                      point: e.value,
                      width: 20,
                      height: 20,
                      child: GestureDetector(
                        onTap: () => _removeBoundaryPoint(e.key, mqtt),
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.orange,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),

              // Robot marker with heading arrow
              MarkerLayer(markers: [
                Marker(
                  point: robotState.position,
                  width: 40,
                  height: 40,
                  child: Transform.rotate(
                    angle: robotState.headingDeg * math.pi / 180.0,
                    child: Icon(
                      Icons.navigation,
                      color: _robotColor(robotState.mode),
                      size: 36,
                      shadows: const [Shadow(blurRadius: 4, color: Colors.black38)],
                    ),
                  ),
                ),
              ]),
            ],
          ),

          // ── Top panel: mode selector ──────────────────────────────────
          Positioned(
            top: 8,
            left: 8,
            right: 8,
            child: const ModeSelector(),
          ),

          // ── Bottom overlay: status + controls ─────────────────────────
          Positioned(
            bottom: 0,
            left: 0,
            right: 0,
            child: _BottomPanel(
              robotState: robotState,
              followRobot: _followRobot,
              editingBoundary: _editingBoundary,
              onFollowToggle: () => setState(() => _followRobot = !_followRobot),
              onBoundaryToggle: () => setState(() {
                _editingBoundary = !_editingBoundary;
                if (!_editingBoundary && _boundary.isValid) {
                  mqtt.sendBoundary(_boundary.toMqttJson());
                }
              }),
              onBoundaryClear: () => setState(() {
                _boundary = _boundary.clear();
              }),
            ),
          ),

          // ── ESTOP FAB ─────────────────────────────────────────────────
          const Positioned(
            bottom: 140,
            right: 16,
            child: EmergencyStopBtn(),
          ),

          // ── Re-centre button ─────────────────────────────────────────
          Positioned(
            bottom: 140,
            left: 16,
            child: FloatingActionButton.small(
              heroTag: 'centre_fab',
              onPressed: () {
                setState(() => _followRobot = true);
                _mapController.move(robotState.position, 18.0);
              },
              child: const Icon(Icons.my_location),
            ),
          ),
        ],
      ),
    );
  }

  void _addBoundaryPoint(LatLng pt, MqttService mqtt) {
    setState(() => _boundary = _boundary.addPoint(pt));
  }

  void _removeBoundaryPoint(int idx, MqttService mqtt) {
    setState(() => _boundary = _boundary.removePoint(idx));
  }

  Color _robotColor(RobotMode mode) {
    switch (mode) {
      case RobotMode.estop:  return Colors.red;
      case RobotMode.auto:   return Colors.blue;
      case RobotMode.follow: return Colors.green;
      case RobotMode.manual: return Colors.orange;
    }
  }
}

// ── Sub-widgets ───────────────────────────────────────────────────────────────

class _MqttIndicator extends StatelessWidget {
  final bool connected;
  const _MqttIndicator({required this.connected});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: connected ? Colors.green : Colors.red,
      ),
    );
  }
}

class _ModeBadge extends StatelessWidget {
  final RobotMode mode;
  const _ModeBadge({required this.mode});

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (mode) {
      RobotMode.manual => ('MANUAL', Colors.orange),
      RobotMode.auto   => ('AUTO',   Colors.blue),
      RobotMode.follow => ('FOLLOW', Colors.green),
      RobotMode.estop  => ('ESTOP',  Colors.red),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontWeight: FontWeight.bold,
          fontSize: 11,
        ),
      ),
    );
  }
}

class _BottomPanel extends StatelessWidget {
  final RobotState robotState;
  final bool followRobot;
  final bool editingBoundary;
  final VoidCallback onFollowToggle;
  final VoidCallback onBoundaryToggle;
  final VoidCallback onBoundaryClear;

  const _BottomPanel({
    required this.robotState,
    required this.followRobot,
    required this.editingBoundary,
    required this.onFollowToggle,
    required this.onBoundaryToggle,
    required this.onBoundaryClear,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Theme.of(context).colorScheme.surface,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Status row
            Row(
              children: [
                _StatusChip(
                  icon: Icons.gps_fixed,
                  label: robotState.gpsFixed ? 'GPS OK' : 'NO GPS',
                  ok: robotState.gpsFixed,
                ),
                const SizedBox(width: 8),
                if (robotState.navActive)
                  _StatusChip(
                    icon: Icons.route,
                    label:
                        'WP ${robotState.navWaypointIdx}/${robotState.navTotal} '
                        '(${robotState.navDistToNext.toStringAsFixed(0)}m)',
                    ok: true,
                  ),
                if (robotState.boundaryWarning)
                  _StatusChip(icon: Icons.warning, label: 'BOUNDARY WARNING', ok: false),
                if (robotState.boundaryViolation)
                  _StatusChip(icon: Icons.dangerous, label: 'VIOLATION!', ok: false),
              ],
            ),
            const SizedBox(height: 8),
            // Action buttons
            Row(
              children: [
                OutlinedButton.icon(
                  onPressed: onFollowToggle,
                  icon: Icon(followRobot ? Icons.location_on : Icons.location_off),
                  label: Text(followRobot ? 'Following' : 'Follow'),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(
                  onPressed: onBoundaryToggle,
                  icon: Icon(editingBoundary ? Icons.check : Icons.edit_location_alt),
                  label: Text(editingBoundary ? 'Save Boundary' : 'Edit Boundary'),
                  style: editingBoundary
                      ? OutlinedButton.styleFrom(foregroundColor: Colors.orange)
                      : null,
                ),
                if (editingBoundary) ...[
                  const SizedBox(width: 8),
                  IconButton(
                    onPressed: onBoundaryClear,
                    icon: const Icon(Icons.delete_outline),
                    tooltip: 'Clear boundary',
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final IconData icon;
  final String   label;
  final bool     ok;

  const _StatusChip({required this.icon, required this.label, required this.ok});

  @override
  Widget build(BuildContext context) {
    final color = ok ? Colors.green[700]! : Colors.red[700]!;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(20),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withAlpha(100)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(label, style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}
