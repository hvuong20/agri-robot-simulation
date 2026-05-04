import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/mqtt_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _hostCtrl;
  late TextEditingController _portCtrl;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final mqtt = context.read<MqttService>();
    _hostCtrl = TextEditingController(text: mqtt.brokerHost);
    _portCtrl = TextEditingController(text: mqtt.brokerPort.toString());
  }

  @override
  void dispose() {
    _hostCtrl.dispose();
    _portCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final host = _hostCtrl.text.trim();
    final port = int.tryParse(_portCtrl.text.trim()) ?? 1883;
    if (host.isEmpty) return;

    setState(() => _saving = true);

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('mqtt_host', host);
    await prefs.setInt('mqtt_port', port);

    if (!mounted) return;
    final mqtt = context.read<MqttService>();
    mqtt.brokerHost = host;
    mqtt.brokerPort = port;
    mqtt.disconnect();
    await mqtt.connect();

    setState(() => _saving = false);
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text(
            'MQTT Broker',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 8),
          const Text(
            'Enter the address of the Mosquitto broker running on the Pi. '
            'For remote access via Cloudflare Tunnel, use the tunnel subdomain.',
            style: TextStyle(color: Colors.grey, fontSize: 13),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _hostCtrl,
            decoration: const InputDecoration(
              labelText: 'Broker host / IP',
              hintText: '192.168.1.x  or  robot.example.com',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.url,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _portCtrl,
            decoration: const InputDecoration(
              labelText: 'Port',
              hintText: '1883',
              border: OutlineInputBorder(),
            ),
            keyboardType: TextInputType.number,
          ),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Save & Reconnect'),
          ),
          const Divider(height: 40),
          const Text(
            'Tips',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text(
            '• Local WiFi: use the Pi\'s IP address (e.g. 192.168.1.105)\n'
            '• Remote 5G: set up Cloudflare Tunnel on the Pi\n'
            '• Default MQTT port: 1883',
            style: TextStyle(fontSize: 13, height: 1.6),
          ),
        ],
      ),
    );
  }
}
