import socket
import binascii
import CameraController
import time

ip = '10.0.1.31'
port = 5678
buffer_size = 1

camera = CameraController.PTZOptics20x(ip, port)
print camera._tcp_host, camera._tcp_port
camera.init()

#camera.home()

# camera.left(2)
# time.sleep(1)
# camera.stop()
# camera.right(8)
# time.sleep(2)
# camera.stop()
# camera.end()


while 1:
    camera.get_zoom_position()
    camera.get_pan_tilt_position()
    time.sleep(2)
