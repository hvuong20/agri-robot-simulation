import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/robot_state.dart';
import '../services/mqtt_service.dart';

class EmergencyStopBtn extends StatelessWidget {
  const EmergencyStopBtn({super.key});

  @override
  Widget build(BuildContext context) {
    final robotState = context.watch<RobotState>();
    final mqtt       = context.read<MqttService>();
    final isEstop    = robotState.mode == RobotMode.estop;

    return GestureDetector(
      onLongPress: isEstop ? () => _clearEstop(context, mqtt) : null,
      child: FloatingActionButton.extended(
        heroTag: 'estop_fab',
        onPressed: isEstop ? null : () => _triggerEstop(context, mqtt),
        backgroundColor: isEstop ? Colors.orange[700] : Colors.red[700],
        icon: Icon(isEstop ? Icons.lock_open : Icons.stop_circle, size: 28),
        label: Text(
          isEstop ? 'HOLD TO CLEAR' : 'EMERGENCY STOP',
          style: const TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 14,
            letterSpacing: 0.5,
          ),
        ),
      ),
    );
  }

  void _triggerEstop(BuildContext context, MqttService mqtt) {
    mqtt.sendEstop();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('ESTOP sent to robot'),
        backgroundColor: Colors.red,
        duration: Duration(seconds: 2),
      ),
    );
  }

  void _clearEstop(BuildContext context, MqttService mqtt) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Clear ESTOP?'),
        content: const Text(
          'Make sure the robot area is clear before clearing the emergency stop.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
            onPressed: () {
              Navigator.pop(context);
              mqtt.sendEstopClear();
            },
            child: const Text('Clear ESTOP'),
          ),
        ],
      ),
    );
  }
}
