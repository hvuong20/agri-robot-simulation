from setuptools import setup, find_packages
import os
from glob import glob

package_name = 'agri_robot_hardware'

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
    description='Hardware drivers for agri_robot on Raspberry Pi 3',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'rc_interface_node = agri_robot_hardware.rc_interface_node:main',
            'motor_driver_node = agri_robot_hardware.motor_driver_node:main',
        ],
    },
)
