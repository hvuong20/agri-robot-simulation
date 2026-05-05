import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/robot_state.dart';
import '../services/location_service.dart';
import '../services/mqtt_service.dart';
import '../widgets/emergency_stop_btn.dart';
import '../widgets/mode_selector.dart';
import 'settings_screen.dart';

class ControlScreen extends StatefulWidget {
  const ControlScreen({super.key});

  @override
  State<ControlScreen> createState() => _ControlScreenState();
}

class _ControlScreenState extends State<ControlScreen> {
  double _followDistance = 5.0;    // metres
  double _rowOffset      = 3.0;    // metres
  bool   _followingGps   = false;

  @override
  Widget build(BuildContext context) {
    final robotState = context.watch<RobotState>();
    final mqtt       = context.read<MqttService>();
    final location   = context.read<LocationService>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Control Panel'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 4),
            child: _MqttDot(connected: robotState.mqttConnected),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Mode ─────────────────────────────────────────────────────────
          const _SectionHeader('Mode'),
          const SizedBox(height: 8),
          const ModeSelector(),
          const SizedBox(height: 24),

          // ── Status cards ──────────────────────────────────────────────────
          _StatusRow(robotState: robotState),
          const SizedBox(height: 24),

          // ── Follow mode ───────────────────────────────────────────────────
          const _SectionHeader('Follow Mode'),
          const SizedBox(height: 4),
          const Text(
            'Robot follows your phone GPS at the set distance.',
            style: TextStyle(color: Colors.grey, fontSize: 13),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Text('Distance:'),
              Expanded(
                child: Slider(
                  value: _followDistance,
                  min: 1.0,
                  max: 15.0,
                  divisions: 14,
                  label: '${_followDistance.toStringAsFixed(0)} m',
                  onChanged: (v) => setState(() => _followDistance = v),
                ),
              ),
              SizedBox(
                width: 48,
                child: Text(
                  '${_followDistance.toStringAsFixed(0)} m',
                  textAlign: TextAlign.right,
                ),
              ),
            ],
          ),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: robotState.mode == RobotMode.estop
                      ? null
                      : () async {
                          // Send follow distance config via coverage_config repurposed field
                          mqtt.sendCoverageConfig(_rowOffset); // keep existing
                          // Switch to FOLLOW mode
                          mqtt.sendModeSet(RobotMode.follow);
                          // Start publishing phone GPS
                          await location.startPublishing(mqtt);
                          setState(() => _followingGps = true);
                        },
                  icon: const Icon(Icons.directions_walk),
                  label: const Text('Start Following'),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: _followingGps
                    ? () {
                        location.stopPublishing();
                        setState(() => _followingGps = false);
                        mqtt.sendModeSet(RobotMode.manual);
                      }
                    : null,
                child: const Text('Stop'),
              ),
            ],
          ),
          if (_followingGps) ...[
            const SizedBox(height: 8),
            _FollowStatusCard(robotState: robotState),
          ],
          const SizedBox(height: 24),

          // ── Auto coverage ─────────────────────────────────────────────────
          const _SectionHeader('Auto Coverage'),
          const SizedBox(height: 4),
          const Text(
            'Draw the boundary on the map, then start coverage. '
            'Robot sweeps the area in a lawnmower pattern.',
            style: TextStyle(color: Colors.grey, fontSize: 13),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Text('Row spacing:'),
              Expanded(
                child: Slider(
                  value: _rowOffset,
                  min: 2.0,
                  max: 8.0,
                  divisions: 12,
                  label: '${_rowOffset.toStringAsFixed(1)} m',
                  onChanged: (v) => setState(() => _rowOffset = v),
                ),
              ),
              SizedBox(
                width: 52,
                child: Text(
                  '${_rowOffset.toStringAsFixed(1)} m',
                  textAlign: TextAlign.right,
                ),
              ),
            ],
          ),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: robotState.mode == RobotMode.estop
                      ? null
                      : () {
                          mqtt.sendCoverageConfig(_rowOffset);
                          mqtt.sendModeSet(RobotMode.auto);
                        },
                  icon: const Icon(Icons.route),
                  label: const Text('Start Coverage'),
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: robotState.mode == RobotMode.auto
                    ? () => mqtt.sendModeSet(RobotMode.manual)
                    : null,
                child: const Text('Stop'),
              ),
            ],
          ),
          if (robotState.navActive) ...[
            const SizedBox(height: 8),
            _NavStatusCard(robotState: robotState),
          ],
          const SizedBox(height: 24),

          // ── Stuck info ────────────────────────────────────────────────────
          if (robotState.stuckConfirmed) ...[
            _StuckBanner(
              onClear: () => mqtt.sendModeSet(RobotMode.manual),
            ),
            const SizedBox(height: 24),
          ],
        ],
      ),
      floatingActionButton: const EmergencyStopBtn(),
    );
  }
}

// ── Sub-widgets ───────────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  final String text;
  const _SectionHeader(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context)
          .textTheme
          .titleMedium
          ?.copyWith(fontWeight: FontWeight.bold),
    );
  }
}

class _MqttDot extends StatelessWidget {
  final bool connected;
  const _MqttDot({required this.connected});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8, height: 8,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: connected ? Colors.green : Colors.red,
          ),
        ),
        const SizedBox(width: 4),
        Text(
          connected ? 'Connected' : 'Offline',
          style: TextStyle(
            fontSize: 12,
            color: connected ? Colors.green[700] : Colors.red[700],
          ),
        ),
      ],
    );
  }
}

class _StatusRow extends StatelessWidget {
  final RobotState robotState;
  const _StatusRow({required this.robotState});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _Chip(
          label: robotState.gpsFixed ? 'GPS Fixed' : 'No GPS',
          icon: Icons.gps_fixed,
          ok: robotState.gpsFixed,
        ),
        _Chip(
          label: 'Mode: ${robotState.mode.name.toUpperCase()}',
          icon: Icons.settings_remote,
          ok: robotState.mode != RobotMode.estop,
        ),
        if (robotState.boundaryWarning)
          const _Chip(label: 'Boundary warning', icon: Icons.warning, ok: false),
        if (robotState.boundaryViolation)
          const _Chip(label: 'Boundary violation!', icon: Icons.dangerous, ok: false),
        if (robotState.stuckConfirmed)
          const _Chip(label: 'Robot STUCK', icon: Icons.block, ok: false),
        if (robotState.batteryVoltage > 0) ...[
          if (robotState.batteryCritical)
            _Chip(
              label: 'Battery ${robotState.batteryPercent.toStringAsFixed(0)}%!',
              icon: Icons.battery_alert,
              ok: false,
            )
          else if (robotState.batteryLow)
            _Chip(
              label: 'Low ${robotState.batteryPercent.toStringAsFixed(0)}%',
              icon: Icons.battery_2_bar,
              ok: false,
            )
          else
            _Chip(
              label: 'Battery ${robotState.batteryPercent.toStringAsFixed(0)}%',
              icon: Icons.battery_full,
              ok: true,
            ),
        ],
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  final String   label;
  final IconData icon;
  final bool     ok;
  const _Chip({required this.label, required this.icon, required this.ok});

  @override
  Widget build(BuildContext context) {
    final color = ok ? Colors.green[700]! : Colors.red[700]!;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(20),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(label, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _FollowStatusCard extends StatelessWidget {
  final RobotState robotState;
  const _FollowStatusCard({required this.robotState});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.green[50],
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            const Icon(Icons.directions_walk, color: Colors.green),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Following — ${robotState.followDistM.toStringAsFixed(1)} m away',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                Text(
                  'Heading error: ${robotState.followHeadingErr.toStringAsFixed(0)}°',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _NavStatusCard extends StatelessWidget {
  final RobotState robotState;
  const _NavStatusCard({required this.robotState});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Colors.blue[50],
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            const Icon(Icons.route, color: Colors.blue),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Waypoint ${robotState.navWaypointIdx} / ${robotState.navTotal}',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                Text(
                  '${robotState.navDistToNext.toStringAsFixed(1)} m to next',
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
              ],
            ),
            const Spacer(),
            LinearProgressIndicator(
              value: robotState.navTotal > 0
                  ? robotState.navWaypointIdx / robotState.navTotal
                  : 0,
              minHeight: 6,
              backgroundColor: Colors.blue[100],
            ),
          ],
        ),
      ),
    );
  }
}

class _StuckBanner extends StatelessWidget {
  final VoidCallback onClear;
  const _StuckBanner({required this.onClear});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red[50],
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.red),
      ),
      child: Row(
        children: [
          const Icon(Icons.block, color: Colors.red),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Robot is STUCK',
                  style: TextStyle(fontWeight: FontWeight.bold, color: Colors.red),
                ),
                Text(
                  'Robot is commanded but not moving. Check for obstacles.',
                  style: TextStyle(fontSize: 12),
                ),
              ],
            ),
          ),
          TextButton(
            onPressed: onClear,
            child: const Text('Switch to Manual'),
          ),
        ],
      ),
    );
  }
}
