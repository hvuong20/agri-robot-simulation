from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'agri_robot_control'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.py')),
        (os.path.join('share', package_name, 'config'),
            glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='user',
    maintainer_email='user@example.com',
    description='Navigation, mode management, MQTT bridge for agri_robot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mode_manager_node   = agri_robot_control.mode_manager_node:main',
            'boundary_manager_node = agri_robot_control.boundary_manager_node:main',
            'coverage_planner_node = agri_robot_control.coverage_planner_node:main',
            'gps_navigator_node  = agri_robot_control.gps_navigator_node:main',
            'follow_mode_node    = agri_robot_control.follow_mode_node:main',
            'mqtt_bridge_node    = agri_robot_control.mqtt_bridge_node:main',
            'stuck_detector_node = agri_robot_control.stuck_detector_node:main',
        ],
    },
)
